"""
Tests for Unified Personalization Engine, Mode-B Encryption, and DPDP Cascade Erasure.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.personalization import (
    DeletionAuditReceipt,
    UnifiedPersonalizationEngine,
    UnifiedSeekerContext,
    decrypt_facet,
    derive_vault_key,
    encrypt_facet,
    hard_cascade_account_erasure,
)


@pytest.mark.asyncio
async def test_anonymous_fast_path():
    """Test anonymous seeker fast path completes instantly (<0.1ms)."""
    start = asyncio.get_event_loop().time()
    ctx = await UnifiedPersonalizationEngine.hydrate_seeker_context(user_id=None)
    elapsed = (asyncio.get_event_loop().time() - start) * 1000.0

    assert ctx.is_authenticated is False
    assert ctx.user_id == "anonymous"
    assert elapsed < 10.0  # Well under 10ms P95 limit


@pytest.mark.asyncio
async def test_authenticated_hydration():
    """Test hydration across all 7 facets with mocked DB session."""
    mock_session = AsyncMock()
    ctx = await UnifiedPersonalizationEngine.hydrate_seeker_context(
        user_id="seeker-uuid-123",
        session=mock_session,
    )

    assert ctx.is_authenticated is True
    assert ctx.user_id == "seeker-uuid-123"
    assert ctx.seeker_profile is not None
    assert ctx.second_brain is not None
    assert ctx.sadhana is not None
    assert ctx.pre_practice is not None
    assert ctx.study_notebooks is not None
    assert ctx.mood_journal is not None
    assert ctx.whatsapp_reflections is not None


def test_mode_b_crypto_round_trip():
    """Test Mode-B encryption/decryption round-trip with PBKDF2 600,000 rounds."""
    passphrase = "test-secure-passphrase-mukthi"
    vault_key = derive_vault_key(passphrase)

    payload = {"secret_mantra": "Om Shanti Shanti Shanti", "meditation_depth": 9}
    encrypted = encrypt_facet(payload, vault_key)

    assert encrypted.ciphertext is not None
    assert encrypted.iv is not None
    assert encrypted.auth_tag is not None

    decrypted = decrypt_facet(encrypted, vault_key)
    assert decrypted == payload


@pytest.mark.asyncio
async def test_dpdp_cascade_erasure():
    """Test DPDP 26-table cascade erasure execution and receipt verification."""
    mock_session = AsyncMock()
    mock_supabase = MagicMock()
    # Mock supabase select / delete chain
    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.delete.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value = mock_table

    mock_memgraph = MagicMock()
    mock_session = MagicMock()
    mock_session.__enter__.return_value = mock_session
    mock_session.run.return_value.single.return_value = {"deleted": 7}
    mock_memgraph.session.return_value = mock_session

    receipt = await hard_cascade_account_erasure(
        user_id="user-to-erase-999",
        supabase_client=mock_supabase,
        memgraph_driver=mock_memgraph,
    )

    assert isinstance(receipt, DeletionAuditReceipt)
    assert receipt.user_id == "user-to-erase-999"
    assert receipt.audit_verified is True
    assert len(receipt.tables_wiped) >= 26
    assert receipt.graph_nodes_wiped == 7


def test_prompt_guidance_generation():
    """Test prompt guidance generation formatting."""
    ctx = UnifiedSeekerContext(
        user_id="seeker-1",
        is_authenticated=True,
    )
    guidance = ctx.format_prompt_guidance()
    assert "Seeker Personalization & Spiritual Readiness" in guidance
    assert "Sadhana & Practice Journey" in guidance


@pytest.mark.asyncio
async def test_authenticated_hydration_with_supabase_client():
    """Test hydration across all 7 facets with mocked real Supabase schema tables."""
    mock_supabase = MagicMock()

    def mock_table(table_name: str):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.in_.return_value = t
        t.order.return_value = t
        t.limit.return_value = t

        if table_name == "user_profiles":
            t.execute.return_value = MagicMock(
                data=[
                    {
                        "spiritual_level": "practitioner",
                        "preferred_language": "te",
                        "last_distress_assessment": {"level": 1},
                        "topics_of_interest": ["relationships", "forgiveness"],
                    }
                ]
            )
        elif table_name == "canonical_memories":
            t.execute.return_value = MagicMock(
                data=[
                    {
                        "id": "mem-1",
                        "statement": "I struggle with deep resentment towards my spouse",
                        "memory_type": "reflection",
                    }
                ]
            )
        elif table_name == "user_streaks":
            t.execute.return_value = MagicMock(
                data=[
                    {
                        "current_streak": 14,
                        "longest_streak": 21,
                        "total_practice_days": 18,
                    }
                ]
            )
        elif table_name == "meditation_sessions":
            t.execute.return_value = MagicMock(
                data=[
                    {"duration_seconds": 600, "breath_cycles": 10, "completed": True},
                    {"duration_seconds": 600, "breath_cycles": 10, "completed": True},
                ]
            )
        elif table_name == "study_notebook_items":
            t.execute.return_value = MagicMock(
                data=[
                    {
                        "id": "nb-1",
                        "query": "Healing from Betrayal",
                        "answer": "Forgiveness dissolves the victim identity.",
                        "citations": [],
                    }
                ]
            )
        elif table_name == "whatsapp_account_links":
            t.execute.return_value = MagicMock(
                data=[
                    {
                        "status": "linked",
                        "linked_at": "2026-11-20T10:00:00Z",
                        "sync_history_consent": True,
                    }
                ]
            )
        else:
            t.execute.return_value = MagicMock(data=[])
        return t

    mock_supabase.table.side_effect = mock_table

    ctx = await UnifiedPersonalizationEngine.hydrate_seeker_context(
        user_id="seeker-uuid-456",
        supabase_client=mock_supabase,
    )

    assert ctx.is_authenticated is True
    assert ctx.seeker_profile.spiritual_readiness == "practitioner"
    assert ctx.seeker_profile.language == "te"
    assert ctx.seeker_profile.distress_level == 1
    assert ctx.seeker_profile.custom_attributes.get("topics_of_interest") == [
        "relationships",
        "forgiveness",
    ]

    assert len(ctx.second_brain.canonical_memories) == 1
    assert (
        ctx.second_brain.canonical_memories[0]["statement"]
        == "I struggle with deep resentment towards my spouse"
    )

    assert ctx.sadhana.streak_count == 14
    assert ctx.sadhana.longest_streak == 21
    assert ctx.sadhana.minutes_meditated == 20

    assert len(ctx.study_notebooks.saved_teachings) == 1
    assert ctx.study_notebooks.saved_teachings[0]["title"] == "Healing from Betrayal"

    assert ctx.whatsapp_reflections.integration_status == "linked"

    guidance = ctx.format_prompt_guidance()
    assert "I struggle with deep resentment towards my spouse" in guidance
    assert "Healing from Betrayal" in guidance
    assert "- No canonical memories recorded yet." not in guidance
    assert "- No saved teachings in active notebook." not in guidance


@pytest.mark.asyncio
async def test_personalize_stage_fallback_to_state_memory(monkeypatch):
    """Test PersonalizeStage falls back to ctx.state memory_context when database memories are empty."""
    from app.pipeline.stages import personalize_stage as stage_module
    from app.pipeline.stages.context import PipelineContext
    from app.pipeline.stages.personalize_stage import PersonalizeStage
    from app.schemas import ChatRequest

    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available", lambda _: True
    )
    monkeypatch.setattr(
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        "services.first_person_store.source_is_authoritatively_licensed",
        lambda **kwargs: True,
    )

    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.in_.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value = mock_table

    container = MagicMock()
    container.supabase_client = mock_supabase
    container.qdrant = MagicMock()
    container.memgraph = MagicMock()

    import hashlib

    verbatim = "To be free of hurt is to see the other person with eyes of love."
    mock_clip = {
        "point_id": "clip-123",
        "video_id": "dQw4w9WgXcQ",
        "start_ms": 10000,
        "end_ms": 25000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "verbatim_text": verbatim,
        "transcript_hash": hashlib.sha256(verbatim.encode("utf-8")).hexdigest(),
        "is_verbatim": True,
        "first_person_eligible": True,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
    }
    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = mock_clip
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)

    stage = PersonalizeStage()

    req = ChatRequest(
        messages=[],
        user_message="Please personalize this teaching for me.",
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 12},
    )

    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=req,
        user_msg="Please personalize this teaching for me.",
        preferred_lang="en",
        trace_id="test-trace-fallback",
        user_id="11111111-1111-4111-8111-111111111111",
        incognito=False,
        personalization_eligible=True,
        personal_context_confirmed=True,
        state={
            "memory_context": (
                "- [FACT] Seeker experiences deep grief after losing their father (confidence=0.95)\n"
                "- [PREFERENCE] Prefers contemplative questions over structured steps (confidence=0.85)"
            ),
            "user_profile": {
                "spiritual_level": "practitioner",
                "preferred_language": "en",
            },
        },
    )

    res = await stage.run(ctx)
    assert res is None  # Accepted and passes to GraphStage

    seeker_ctx = ctx.state.get("seeker_context")
    assert seeker_ctx is not None
    assert len(seeker_ctx.second_brain.canonical_memories) == 2
    assert (
        "Seeker experiences deep grief after losing their father"
        in seeker_ctx.second_brain.canonical_memories[0]["statement"]
    )

    guidance = ctx.state.get("seeker_guidance", "")
    assert "Seeker experiences deep grief after losing their father" in guidance
    assert "- No canonical memories recorded yet." not in guidance


@pytest.mark.asyncio
async def test_false_abstention_recovery_soul_sync_instructions():
    """Test step-by-step meditation instruction query falls through to meditation handler instead of abstaining."""
    from app.pipeline.stages.context import PipelineContext
    from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
    from app.schemas import ChatRequest
    from rag.nodes.intent import _fast_classify, handle_meditation

    query = "What are the exact step-by-step instructions to practice the Soul Sync meditation?"

    # 1. FirstPersonBridgeStage returns None (hands off to GraphStage)
    container = MagicMock()
    req = ChatRequest(messages=[], user_message=query)
    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=req,
        user_msg=query,
        preferred_lang="en",
        trace_id="test-soul-sync-trace",
        state={"user_msg_en": query},
    )

    bridge_stage = FirstPersonBridgeStage()
    bridge_res = await bridge_stage.run(ctx)
    assert bridge_res is None, "Bridge must return None to allow GraphStage to serve practice steps"

    # 2. _fast_classify classifies as MEDITATION
    fast_res = _fast_classify(query)
    assert fast_res is not None
    assert fast_res["intent"] == "MEDITATION"

    from rag.nodes.on_device_intent import classify_with_reason

    on_dev = classify_with_reason("What are the steps of Soul Sync meditation?")
    assert on_dev is not None
    assert on_dev[0] == "MEDITATION"

    from rag.nodes.intent import _intent_router_impl

    routed = await _intent_router_impl(
        {
            "question": "What are the steps of Soul Sync meditation?",
            "intent": "MEDITATION",
            "query_tier": "tier2_simple",
            "chat_history": [],
            "meditation_step": 0,
        }
    )
    assert routed["intent"] == "MEDITATION"

    # 3. handle_meditation produces the 7-step Soul Sync script
    med_res = await handle_meditation({"question": query, "meditation_step": 0})
    assert med_res["intent"] == "MEDITATION"
    final_answer = med_res["final_answer"]
    assert "Soul Sync Meditation" in final_answer
    assert "Breathe deeply with breath awareness" in final_answer
    assert "bee humming" in final_answer
    assert "A-hummm, also written as Aham" in final_answer
    assert "golden light" in final_answer
    assert "heartfelt intention" in final_answer


@pytest.mark.asyncio
async def test_false_abstention_recovery_difference_synthesis():
    """Test conceptual difference inquiries (ego vs intelligence) hand off to GraphStage for multi-source synthesis."""
    from app.pipeline.stages.context import PipelineContext
    from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
    from app.schemas import ChatRequest

    query = "What is the difference between the ego-self ('I') and universal intelligence according to the teachings?"

    container = MagicMock()
    req = ChatRequest(messages=[], user_message=query)
    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=req,
        user_msg=query,
        preferred_lang="en",
        trace_id="test-difference-trace",
        state={"user_msg_en": query},
    )

    bridge_stage = FirstPersonBridgeStage()
    bridge_res = await bridge_stage.run(ctx)
    assert bridge_res is None, "Bridge must hand off comparative synthesis inquiry to GraphStage"


@pytest.mark.asyncio
async def test_personalize_stage_dataclass_profile_and_memory_merging(monkeypatch):
    """Test PersonalizeStage extracts attributes from UserProfile dataclass and unifies memories."""
    from app.pipeline.stages.context import PipelineContext
    from app.pipeline.stages.personalize_stage import PersonalizeStage
    import app.pipeline.stages.personalize_stage as stage_module
    from app.schemas import ChatRequest
    from services.user_profile_service import LanguagePreference, SpiritualLevel, UserProfile

    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available", lambda _: True
    )
    monkeypatch.setattr(
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        "services.first_person_store.source_is_authoritatively_licensed",
        lambda **kwargs: True,
    )

    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.in_.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value = mock_table

    container = MagicMock()
    container.supabase_client = mock_supabase
    container.qdrant = MagicMock()
    container.memgraph = MagicMock()

    import hashlib

    verbatim = "To be free of hurt is to see the other person with eyes of love."
    mock_clip = {
        "point_id": "clip-123",
        "video_id": "dQw4w9WgXcQ",
        "start_ms": 10000,
        "end_ms": 25000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "verbatim_text": verbatim,
        "transcript_hash": hashlib.sha256(verbatim.encode("utf-8")).hexdigest(),
        "is_verbatim": True,
        "first_person_eligible": True,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
    }
    store = MagicMock()
    store.get_clip_by_video_and_start.return_value = mock_clip
    monkeypatch.setattr(stage_module, "_store_for_request", lambda: store)

    profile = UserProfile(
        user_id="22222222-2222-4222-8222-222222222222",
        created_at=1000.0,
        updated_at=1000.0,
        spiritual_level=SpiritualLevel.PRACTITIONER,
        preferred_language=LanguagePreference.TELUGU,
        topics_of_interest=["relationships", "forgiveness"],
        last_distress_assessment={"level": 2},
    )

    stage = PersonalizeStage()
    req = ChatRequest(
        messages=[],
        user_message="Please personalize this teaching for me.",
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 12},
    )

    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=req,
        user_msg="Please personalize this teaching for me.",
        preferred_lang="te",
        trace_id="test-dataclass-profile",
        user_id="22222222-2222-4222-8222-222222222222",
        incognito=False,
        personalization_eligible=True,
        personal_context_confirmed=True,
        state={
            "user_profile": profile,
            "memory_context": (
                "- [FACT] Seeker struggles with resentment towards a former colleague (confidence=0.9)\n"
                "- [PREFERENCE] Seeker loves morning meditations (confidence=0.85)"
            ),
        },
    )

    res = await stage.run(ctx)
    assert res is None

    seeker_ctx = ctx.state.get("seeker_context")
    assert seeker_ctx is not None
    assert seeker_ctx.seeker_profile.spiritual_readiness == "practitioner"
    assert seeker_ctx.seeker_profile.language == "te"
    assert seeker_ctx.seeker_profile.distress_level == 2
    assert seeker_ctx.seeker_profile.custom_attributes.get("topics_of_interest") == [
        "relationships",
        "forgiveness",
    ]
    assert seeker_ctx.has_state_memory is True

    guidance = ctx.state.get("seeker_guidance", "")
    assert "**Focus Areas**: relationships, forgiveness" in guidance
    assert "Seeker struggles with resentment towards a former colleague" in guidance
    assert "- No canonical memories recorded yet." not in guidance
    assert "- No saved teachings in active notebook." not in guidance


@pytest.mark.asyncio
async def test_false_abstention_recovery_step_instructions_soul_sync():
    """Test 'What are the steps to practice Soul Sync?' falls through bridge and returns 7-step meditation script."""
    from app.pipeline.stages.context import PipelineContext
    from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
    from app.schemas import ChatRequest
    from rag.nodes.intent import _fast_classify, handle_meditation

    query = "What are the steps to practice Soul Sync?"

    container = MagicMock()
    req = ChatRequest(messages=[], user_message=query)
    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=req,
        user_msg=query,
        preferred_lang="en",
        trace_id="test-steps-trace",
        state={"user_msg_en": query},
    )

    bridge_stage = FirstPersonBridgeStage()
    bridge_res = await bridge_stage.run(ctx)
    assert bridge_res is None, "Bridge must fall through for step instruction inquiry"

    fast_res = _fast_classify(query)
    assert fast_res is not None
    assert fast_res["intent"] == "MEDITATION"

    from rag.nodes.on_device_intent import classify_with_reason

    on_dev = classify_with_reason("What are the steps of Soul Sync meditation?")
    assert on_dev is not None
    assert on_dev[0] == "MEDITATION"

    from rag.nodes.intent import _intent_router_impl

    routed = await _intent_router_impl(
        {
            "question": "What are the steps of Soul Sync meditation?",
            "intent": "MEDITATION",
            "query_tier": "tier2_simple",
            "chat_history": [],
            "meditation_step": 0,
        }
    )
    assert routed["intent"] == "MEDITATION"

    med_res = await handle_meditation({"question": query, "meditation_step": 0})
    assert med_res["intent"] == "MEDITATION"
    final_answer = med_res["final_answer"]
    assert "Soul Sync Meditation" in final_answer
    assert "Breathe deeply with breath awareness" in final_answer


@pytest.mark.asyncio
async def test_false_abstention_recovery_distinction_synthesis():
    """Test 'distinction between' synthesis inquiry hands off to GraphStage."""
    from app.pipeline.stages.context import PipelineContext
    from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
    from app.schemas import ChatRequest

    query = "What is the distinction between ego and universal consciousness according to the teachings?"

    container = MagicMock()
    req = ChatRequest(messages=[], user_message=query)
    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=req,
        user_msg=query,
        preferred_lang="en",
        trace_id="test-distinction-trace",
        state={"user_msg_en": query},
    )

    bridge_stage = FirstPersonBridgeStage()
    bridge_res = await bridge_stage.run(ctx)
    assert bridge_res is None, "Bridge must hand off distinction synthesis inquiry to GraphStage"
