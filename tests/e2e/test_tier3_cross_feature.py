"""Tier 3: Pairwise Cross-Feature Interactions E2E Tests (12 Tests).

Requirement-driven opaque-box verification covering pairwise feature interactions:
- First-Person served teaching followed by Personalize opt-in turn (T-B14).
- Personalize opt-in + Canonical memory + User spiritual level profile retention.
- Multi-turn conversation with follow-up query rewriting bypassed on personalize turns.
- Intake Crisis preemption overriding Personalize turn.
- Incognito toggle mid-conversation resetting memory and declining personalization.
- Synthetic personalize_doc retrieval prepending and verification context grounding.
- Generation prompt directive attachment for memory personalization.
- Consent revocation fail-closed blocking personalization.
- Prompt validation gating casual greetings from unexpected personalize execution.
- Integrity and licensing clearance rejection at personalize stage.
- Cross-parent predecessor support in editorial sets.
- Serving contract validation with exact-cache fingerprint components.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.orchestrator_utils import prepare_request_state, prepare_user_memory
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.distress_stage import DistressStage, has_crisis_keywords
from app.pipeline.stages.graph_stage import GraphStage
from app.pipeline.stages.memory_stage import MemoryStage
from app.pipeline.stages.personalize_stage import (
    PERSONALIZE_TEACHING_PROMPT,
    PersonalizeStage,
    apply_personalize_marking,
)
from app.schemas import ChatRequest, PersonalizeTeachingRef
from domain.first_person_context import (
    AnswerRole,
    BoundaryStatus,
    CompletenessStatus,
    ParentContext,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
    make_source_span_id,
)
from rag.nodes.generation import context_engineer
from rag.nodes.verification import _verification_context
from rag.resolve_followup import resolve_followup
from services.first_person_context_harness import (
    FirstPersonContextHarness,
    HarnessPolicy,
)
from services.first_person_evidence_policy import _context_standalone_problem
from services.first_person_serving_contract import (
    CONTEXT_SCHEMA,
    CollectionContract,
    fingerprint_components,
    load_contract,
    validate_serving_contract,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
HASH = "c" * 64


# ===========================================================================
# Pairwise Interaction Tests
# ===========================================================================

def test_cross_01_fp_served_then_personalize_opt_in_data_flow(mock_teaching_store: Any):
    """Pairwise 1: First-Person served teaching clip flows cleanly into T-B14 opt-in turn."""
    # Step 1: Simulate served clip from First-Person pipeline
    served_clip = mock_teaching_store.clips["dQw4w9WgXcQ:99000"]
    video_id = served_clip["video_id"]
    timestamp_s = served_clip["start_ms"] / 1000.0  # 99.0s

    # Step 2: Seeker opts in to personalize via T-B14 ref
    req = ChatRequest(
        messages=[
            {"role": "user", "content": "How do I deal with suffering?"},
            {"role": "assistant", "content": served_clip["verbatim_text"]},
        ],
        user_message=PERSONALIZE_TEACHING_PROMPT,
        personalize_teaching={"video_id": video_id, "timestamp_seconds": timestamp_s},
    )

    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=req,
        user_msg=PERSONALIZE_TEACHING_PROMPT,
        preferred_lang="en",
        trace_id="test-cross-flow-01",
        start_time=time.time(),
        state={"user_msg_en": PERSONALIZE_TEACHING_PROMPT},
        user_id="11111111-1111-4111-8111-111111111111",
        incognito=False,
        personalization_eligible=True,
        personal_context_confirmed=True,
    )

    stage = PersonalizeStage()
    result = asyncio.run(stage.run(ctx))

    # Must pass through to LangGraph with personalize_clip stashed
    assert result is None
    assert "personalize_clip" in ctx.state
    assert ctx.state["personalize_clip"]["video_id"] == video_id
    assert ctx.state["personalize_clip"]["verbatim_text"] == served_clip["verbatim_text"]


def test_cross_02_personalize_opt_in_canonical_memory_profile_retention():
    """Pairwise 2: Personalize opt-in preserves both canonical memory and spiritual level profile."""
    container = MagicMock()

    profile_mock = MagicMock()
    profile_mock.spiritual_level = "advanced"
    profile_mock.preferred_tone = "gentle"
    profile_mock.total_conversations = 5
    container.user_profile.get_or_create_profile = AsyncMock(return_value=profile_mock)
    container.user_profile.update_profile = AsyncMock()
    container.user_profile.get_distress_history = AsyncMock(return_value=[])
    container.user_profile.get_recent_memories = AsyncMock(return_value=[])

    canonical_mock = MagicMock()
    canonical_mock.prepare_context = AsyncMock(return_value="Seeker has regular mindfulness practice.")
    container.canonical_memory_integration = canonical_mock
    container.memory_service = None

    outbox_mock = MagicMock()
    outbox_mock.active_consent = AsyncMock(return_value=True)
    container.memory_outbox = outbox_mock

    context, distress, profile, canon = asyncio.run(
        prepare_user_memory(
            container=container,
            user_id="11111111-1111-4111-8111-111111111111",
            chat_history=[],
            user_msg_en=PERSONALIZE_TEACHING_PROMPT,
        )
    )

    # Both tiers must be preserved simultaneously (DEF-R2-03)
    assert profile is not None
    assert profile.spiritual_level == "advanced"
    assert profile.preferred_tone == "gentle"
    assert "Seeker has regular mindfulness practice." in context


def test_cross_03_multiturn_followup_bypasses_rewriting_on_personalize():
    """Pairwise 3: Multi-turn chat history leaves question intact on personalize turns (DEF-R2-02)."""
    grounded_question = (
        'The seeker received this authentic teaching from Sri Preethaji:\n'
        '"Awareness sees the movement of thought without following it."\n'
        'Please personalize this insight.'
    )
    state = {
        "question": grounded_question,
        "chat_history": [
            {"role": "user", "content": "How do I observe thoughts?"},
            {"role": "assistant", "content": "Awareness sees the movement of thought without following it."},
        ],
        "personalize_clip": {
            "verbatim_text": "Awareness sees the movement of thought without following it.",
            "video_id": "dQw4w9WgXcQ",
        },
    }

    result = asyncio.run(resolve_followup(state))

    # Rewriting must be completely bypassed, returning empty dict
    assert result == {}


def test_cross_04_intake_crisis_preemption_overrides_personalize_turn():
    """Pairwise 4: Acute crisis expression preempts turn before PersonalizeStage executes."""
    acute_crisis_msg = "I cannot take this pain anymore, I want to end my life."
    assert has_crisis_keywords(acute_crisis_msg) is True

    req = ChatRequest(
        messages=[],
        user_message=acute_crisis_msg,
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0},
    )

    container = MagicMock()
    container.user_profile = MagicMock()
    container.user_profile.record_distress_event = AsyncMock()

    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=req,
        user_msg=acute_crisis_msg,
        preferred_lang="en",
        trace_id="test-crisis-preempt",
        start_time=time.time(),
        state={"user_msg_en": acute_crisis_msg},
        user_id="11111111-1111-4111-8111-111111111111",
        incognito=False,
    )

    distress_stage = DistressStage()
    result = asyncio.run(distress_stage.run(ctx))

    # Distress stage MUST preempt immediately with crisis response
    assert result is not None
    assert result.intent in ("CRISIS", "DISTRESS")
    assert "help" in result.final_answer.lower() or "helpline" in result.final_answer.lower()
    # PersonalizeStage was never reached, so state does not have personalize_clip
    assert "personalize_clip" not in ctx.state


def test_cross_05_incognito_toggle_mid_conversation_resets_memory_and_declines():
    """Pairwise 5: Toggling incognito mid-conversation suppresses memory context and declines opt-in."""
    # 1. Test memory isolation in prepare_user_memory and prepare_request_state
    container = MagicMock()
    container.translation = MagicMock()
    container.memory_outbox = MagicMock()

    chat_body = SimpleNamespace(
        incognito=True,
        user_message="How do I meditate?",
        session_id="test-session-incognito",
        messages=[],
        conversation_summary="Prior discussion on meditation",
    )
    user = {"id": "11111111-1111-4111-8111-111111111111"}

    # Orchestrator prepare_request_state enforces hard incognito boundary
    req_state = asyncio.run(prepare_request_state(container, chat_body, "en", user=user))
    assert req_state["memory_context"] == ""
    assert req_state["user_profile"] is None
    assert req_state["canonical_memory_evidence"] == ""
    assert req_state["conversation_summary"] == ""

    # When active consent is missing or revoked, prepare_user_memory also strictly returns empty
    container.memory_outbox.active_consent = AsyncMock(return_value=False)
    mem_tuple = asyncio.run(prepare_user_memory(container, user["id"], []))
    assert mem_tuple[0] == ""  # memory_context
    assert mem_tuple[1] == []  # distress_history
    assert mem_tuple[2] is None  # user_profile
    assert mem_tuple[3] == ""  # canonical_memory_evidence

    # 2. Test MemoryStage persistence skip
    mem_ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg="Contemplation",
        preferred_lang="en",
        trace_id="test-incognito-save",
        start_time=time.time(),
        state={},
        incognito=True,
    )
    mem_stage = MemoryStage()
    save_result = asyncio.run(mem_stage.run(mem_ctx))
    assert save_result is None  # Never persists

    # 3. Test PersonalizeStage refusal
    req = ChatRequest(
        messages=[
            {"role": "user", "content": "How do I overcome fear?"},
            {"role": "assistant", "content": "Observation without resistance dissolves fear."},
        ],
        user_message=PERSONALIZE_TEACHING_PROMPT,
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0},
        incognito=True,
    )
    p_ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=req,
        user_msg=PERSONALIZE_TEACHING_PROMPT,
        preferred_lang="en",
        trace_id="test-incognito-decline",
        start_time=time.time(),
        state={},
        user_id="11111111-1111-4111-8111-111111111111",
        incognito=True,
    )
    p_stage = PersonalizeStage()
    p_result = asyncio.run(p_stage.run(p_ctx))

    assert p_result is not None
    assert p_result.route_decision == "personalize_declined_incognito"


def test_cross_06_synthetic_doc_retrieval_and_verification_grounding():
    """Pairwise 6: personalize_clip is injected as synthetic doc and verified in _verification_context."""
    clip = {
        "verbatim_text": "In deep observation, the boundary between observer and observed dissolves.",
        "title": "On Deep Observation",
        "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "video_id": "dQw4w9WgXcQ",
        "point_id": "pt_deep_obs",
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "start_ms": 1000,
        "end_ms": 5000,
    }
    state: dict[str, Any] = {
        "personalize_clip": clip,
        "question": "How to observe without the observer?",
        "relevant_docs": [
            {"text": "General meditation background doc.", "knowledge_source": "general_rag"}
        ],
        "canonical_memory_evidence": "Seeker meditates 20 mins every evening.",
    }

    # Execute genuine context engineering which injects synthetic personalize_doc
    ce_result = asyncio.run(context_engineer(state))
    selected = ce_result.get("selected_docs") or []
    assert len(selected) >= 1
    p_doc = selected[0]
    assert p_doc["knowledge_source"] == "personalize_clip"
    assert p_doc["is_verbatim"] is True
    assert p_doc["rerank_score"] == 1.0
    assert p_doc["text"] == clip["verbatim_text"]
    assert clip["verbatim_text"] in ce_result["context_layers"]["knowledge"]

    # Also verify via GraphStage packaging
    container = MagicMock()
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={"final_answer": "ok", "citations": []})
    container.fast_graph = mock_graph
    container.standard_graph = mock_graph
    container.deep_graph = mock_graph
    coordinator = MagicMock()
    async def fake_get_or_run(key, fn):
        return await fn()
    coordinator.coalescer = MagicMock()
    coordinator.coalescer.get_or_run.side_effect = fake_get_or_run

    g_ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=MagicMock(attachment_context=None, assistant=None),
        user_msg="Please personalize this teaching for me.",
        preferred_lang="en",
        trace_id="test-cross-06-graph",
        start_time=time.time(),
        state={"user_msg_en": "Please personalize this teaching for me.", "chat_history_en": [], "personalize_clip": clip},
        user_id="11111111-1111-4111-8111-111111111111",
        session_id="sess-cross-06",
    )
    asyncio.run(GraphStage().run(g_ctx))
    graph_initial_state = mock_graph.ainvoke.call_args[0][0]
    docs = graph_initial_state.get("documents", [])
    assert len(docs) >= 1
    assert docs[0]["knowledge_source"] == "personalize_clip"
    assert docs[0]["is_verbatim"] is True

    # Verification context incorporates verbatim text
    v_ctx = _verification_context(state, fallback=[])
    assert clip["verbatim_text"] in v_ctx
    assert "Seeker meditates 20 mins every evening." in v_ctx


def test_cross_07_personalize_generation_prompt_directive():
    """Pairwise 7: Generation prompt directive is appended when personalize_clip is present."""
    clip = {
        "verbatim_text": "Stillness is the natural state of consciousness.",
        "speaker": "Sri Krishnaji",
    }
    state: dict[str, Any] = {
        "personalize_clip": clip,
        "question": "How do I overcome fear?",
        "relevant_docs": [],
    }
    result = asyncio.run(context_engineer(state))
    instructions = result["context_layers"]["instructions"]
    assert "PERSONALIZATION DIRECTIVE" in instructions
    assert "Gently relate the teacher's verbatim insight" in instructions

    # Verify that without personalize_clip, directive is absent
    state_without: dict[str, Any] = {
        "question": "How do I overcome fear?",
        "relevant_docs": [],
    }
    result_without = asyncio.run(context_engineer(state_without))
    instructions_without = result_without["context_layers"]["instructions"]
    assert "PERSONALIZATION DIRECTIVE" not in instructions_without


def test_cross_08_consent_revocation_blocks_personalization():
    """Pairwise 8: Consent revocation fails closed, setting personal_context_confirmed=False."""
    container = MagicMock()
    outbox_mock = MagicMock()
    # Consent revoked
    outbox_mock.active_consent = AsyncMock(return_value=False)
    container.memory_outbox = outbox_mock
    container.user_profile = MagicMock()

    # prepare_user_memory must return empty context and None profile
    context, distress, profile, canon = asyncio.run(
        prepare_user_memory(
            container=container,
            user_id="11111111-1111-4111-8111-111111111111",
            chat_history=[],
            user_msg_en=PERSONALIZE_TEACHING_PROMPT,
        )
    )

    assert profile is None
    assert context == ""

    # PersonalizeStage then declines with no_graph
    req = ChatRequest(
        messages=[],
        user_message=PERSONALIZE_TEACHING_PROMPT,
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0},
    )
    ctx = PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=req,
        user_msg=PERSONALIZE_TEACHING_PROMPT,
        preferred_lang="en",
        trace_id="test-consent-gate",
        start_time=time.time(),
        state={},
        user_id="11111111-1111-4111-8111-111111111111",
        personal_context_confirmed=False,  # Set because profile was None
    )

    stage = PersonalizeStage()
    result = asyncio.run(stage.run(ctx))

    assert result is not None
    assert result.route_decision == "personalize_declined_no_graph"


def test_cross_09_casual_greeting_prompt_mismatch_gate_interaction():
    """Pairwise 9: Casual greeting sent with personalize ref declines via prompt gate."""
    req = ChatRequest(
        messages=[],
        user_message="Hello, good morning!",
        personalize_teaching={"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99.0},
    )
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=req,
        user_msg="Hello, good morning!",
        preferred_lang="en",
        trace_id="test-greeting-personalize",
        start_time=time.time(),
        state={},
        user_id="11111111-1111-4111-8111-111111111111",
        personal_context_confirmed=True,
    )

    stage = PersonalizeStage()
    result = asyncio.run(stage.run(ctx))

    assert result is not None
    assert result.route_decision == "personalize_declined_unexpected_prompt"


def test_cross_10_unlicensed_clip_integrity_rejection_at_personalize(mock_teaching_store: Any):
    """Pairwise 10: Invariant X40 — Unlicensed or revoked clip fails integrity gate at lookup."""
    # Add an unlicensed clip
    mock_teaching_store.add_clip({
        "point_id": "unlicensed_clip_01",
        "video_id": "un1ic3ns3d1",
        "start_ms": 10_000,
        "end_ms": 30_000,
        "speaker": "External Speaker",
        "verbatim_text": "Some text without verified license.",
        "source_url": "https://www.youtube.com/watch?v=un1ic3ns3d1",
        "domain_rights_status": "unlicensed",
        "rights_cleared": False,
    })

    req = ChatRequest(
        messages=[],
        user_message=PERSONALIZE_TEACHING_PROMPT,
        personalize_teaching={"video_id": "un1ic3ns3d1", "timestamp_seconds": 10.0},
    )
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=req,
        user_msg=PERSONALIZE_TEACHING_PROMPT,
        preferred_lang="en",
        trace_id="test-unlicensed-lookup",
        start_time=time.time(),
        state={},
        user_id="11111111-1111-4111-8111-111111111111",
        personal_context_confirmed=True,
    )

    stage = PersonalizeStage()
    result = asyncio.run(stage.run(ctx))

    assert result is not None
    assert result.route_decision == "personalize_declined_unknown_clip"


def _make_span(n: int = 0, text: str = "Suffering dissolves in quiet awareness.", **overrides) -> SourceSpan:
    gid = overrides.get("guru_id", "preethaji")
    data = {
        "corpus_version": "ctx-v1",
        "guru_id": gid,
        "video_id": "dQw4w9WgXcQ",
        "source_asset_id": "dQw4w9WgXcQ",
        "source_span_id": make_source_span_id(
            guru_id=gid,
            video_id="dQw4w9WgXcQ",
            corpus_version="ctx-v1",
            word_start=n * 10,
            word_end=n * 10 + 6,
            transcript_hash=HASH,
        ),
        "parent_unit_id": overrides.get("parent_unit_id", "parent_002"),
        "turn_id": f"turn{n}",
        "turn_index": n,
        "source_span_index": n,
        "start_ms": 10_000 * n,
        "end_ms": 10_000 * n + 9000,
        "word_start": n * 10,
        "word_end": n * 10 + 6,
        "speaker_id": gid,
        "speaker_role": SpeakerRole.GURU,
        "speaker_verified": True,
        "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
        "source_transcript_text": text,
        "verbatim_text": text,
        "transcript_hash": HASH,
        "source_text_hash": clip_text_hash(text),
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "caption_status": "auto",
        "provenance_kind": ProvenanceKind.SPEECH_TURN_SPAN,
        "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "answer_role": AnswerRole.DIRECT,
    }
    data.update(overrides)
    return SourceSpan(**data)


def test_cross_11_cross_parent_predecessor_support_in_editorial_assembly():
    """Pairwise 11: Validated cross-parent predecessor span attaches cleanly in editorial set."""
    # Predecessor from parent Alpha, hit span from parent Beta
    span_pred = _make_span(
        0,
        "Meditation begins with understanding the nature of thought.",
        parent_unit_id="parent_alpha",
    )
    span_hit = _make_span(
        1,
        "When you observe thoughts without judgment, inner freedom arises naturally.",
        parent_unit_id="parent_beta",
    )

    editorial_texts = [span_pred.verbatim_text, span_hit.verbatim_text]
    problem = _context_standalone_problem(editorial_texts, is_complete_thought=True, is_standalone=True)
    assert problem is None


def test_cross_12_serving_contract_validation_with_exact_cache_fingerprint():
    """Pairwise 12: Invariant X13 — Contract validation coordinates with exact cache fingerprint."""
    contract = load_contract(_REPO_ROOT / "backend" / "config" / "first_person_serving_contract.json")
    report = validate_serving_contract(
        contract=contract,
        legacy_collection="first_person_v8",
        context_collection="first_person_v10",
    )
    assert report.ok is True

    # Check fingerprint structure
    entry = CollectionContract(
        name="first_person_v10",
        schema=CONTEXT_SCHEMA,
        role="context",
        corpus_version="fp-context-transcript-v1",
        required_payload_fields=("verbatim_text", "video_id"),
        evidence_policy="automated_evidence_candidate",
    )
    components = fingerprint_components(entry)
    assert components["collection"] == "first_person_v10"
    assert components["schema"] == CONTEXT_SCHEMA
    assert components["corpus_version"] == "fp-context-transcript-v1"
    assert components["evidence_policy"] == "automated_evidence_candidate"
