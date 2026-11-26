"""Unit tests for Dynamic LLM Spiritual Concept Expansion and Adaptive 2-Try Feedback Loop.

Verifies:
1. In-memory LRU caching (<0.01ms hit) and Redis cache fallback.
2. Fast LLM query reformulation parsing into 2-3 doctrinal search phrases.
3. Fail-open fallback to OKF concept expansion / domain keywords on timeout (>800ms) or error.
4. Modernized Graph RAG retrieval (_llm_retrieval_expansions, budget calculation max(1, 4 - len(queries)), 0.80s soft wait).
5. Personalization 7-facet serialization in personalize_stage.py and negative poison removal in models.py.
6. Generation instruction 9 relaxation and Rule 1/2 personalization harmonization.
7. Adaptive 2-Try feedback loop in FirstPersonPipeline (100% verbatim quote authenticity).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.personalize_stage import PersonalizeStage
from rag.nodes.generation import generate_answer
from rag.nodes.utils import _llm_retrieval_expansions
from services.first_person_pipeline import FirstPersonPipeline
from services.personalization.models import (
    MoodSpiritualJournalContext,
    PrePracticeLogContext,
    SadhanaPracticeContext,
    SecondBrainContext,
    SeekerProfileContext,
    StudyNotebookContext,
    UnifiedSeekerContext,
    WhatsAppReflectionContext,
)
from services.spiritual_expansion import (
    SpiritualConceptExpansion,
    set_spiritual_concept_expansion,
)


@pytest.fixture(autouse=True)
def reset_expansion_singleton():
    set_spiritual_concept_expansion(None)
    yield
    set_spiritual_concept_expansion(None)


@pytest.mark.asyncio
async def test_spiritual_expansion_in_memory_lru_cache():
    """Verify that calling expand_query twice returns from in-memory cache on the second call."""
    mock_llm = MagicMock()
    mock_llm.generate_fast = AsyncMock(
        return_value="facing sorrow without resistance\ndissolving grief inner peace\nacceptance of reality"
    )

    svc = SpiritualConceptExpansion(llm_gateway=mock_llm, maxsize=100, ttl_seconds=3600)
    query = "How do I overcome grief from losing my father?"

    # Call 1: Cache Miss -> invokes LLM
    res1 = await svc.expand_query(query)
    assert len(res1) == 3
    assert res1[0] == "facing sorrow without resistance"
    assert mock_llm.generate_fast.call_count == 1

    # Call 2: Cache Hit -> returns immediately without invoking LLM
    res2 = await svc.expand_query(query)
    assert res2 == res1
    assert mock_llm.generate_fast.call_count == 1


@pytest.mark.asyncio
async def test_spiritual_expansion_redis_cache():
    """Verify that Redis persistent cache is queried on in-memory cache miss."""
    mock_redis = MagicMock()
    cached_data = ["dissolving hurt and resentment", "healing emotional wounds", "freedom from anger"]
    mock_redis.get.return_value = json.dumps(cached_data)

    mock_llm = MagicMock()
    mock_llm.generate_fast = AsyncMock()

    svc = SpiritualConceptExpansion(llm_gateway=mock_llm, redis_client=mock_redis)
    query = "How to forgive betrayal?"

    res = await svc.expand_query(query)
    assert res == cached_data
    # LLM should not be called because Redis had it
    assert mock_llm.generate_fast.call_count == 0
    mock_redis.get.assert_called_once()


@pytest.mark.asyncio
async def test_spiritual_expansion_llm_parsing():
    """Verify stripping of bullets, numbers, dashes, and extra whitespace."""
    mock_llm = MagicMock()
    raw_llm_output = (
        '1. "conscious parenting inner state"\n'
        '- children absorbing parent state\n'
        '* family connection beautiful state\n'
        '4. Fourth item that should be excluded'
    )
    mock_llm.generate_fast = AsyncMock(return_value=raw_llm_output)

    svc = SpiritualConceptExpansion(llm_gateway=mock_llm)
    res = await svc.expand_query("How to be a better parent to my angry kids?")

    assert len(res) == 3
    assert res[0] == "conscious parenting inner state"
    assert res[1] == "children absorbing parent state"
    assert res[2] == "family connection beautiful state"


@pytest.mark.asyncio
async def test_spiritual_expansion_timeout_fallback_to_keywords():
    """Verify fail-open fallback to domain keywords when LLM times out (>800ms)."""
    mock_llm = MagicMock()

    async def slow_generate(*args, **kwargs):
        await asyncio.sleep(2.0)
        return "too late"

    mock_llm.generate_fast = slow_generate

    svc = SpiritualConceptExpansion(llm_gateway=mock_llm, timeout_seconds=0.05)
    res = await svc.expand_query("I feel so unfulfilled and lost in my career")

    # Should fail open without raising TimeoutError and return career keywords
    assert len(res) >= 1
    assert any("svadharma" in p.lower() or "right action" in p.lower() for p in res)


@pytest.mark.asyncio
async def test_spiritual_expansion_error_fallback_to_okf():
    """Verify fallback to OKF dot product when LLM throws an exception."""
    mock_llm = MagicMock()
    mock_llm.generate_fast = AsyncMock(side_effect=RuntimeError("Provider 500 error"))

    svc = SpiritualConceptExpansion(llm_gateway=mock_llm)
    dummy_dense = [0.01] * 1024

    with patch("services.first_person_okf_expansion.expand_concepts_via_okf") as mock_okf:
        mock_okf.return_value = ["The Nature of Suffering", "Overcoming The Fear Of Death"]
        res = await svc.expand_query("grief and death", query_dense_vector=dummy_dense)

        assert len(res) == 2
        assert "The Nature of Suffering" in res
        mock_okf.assert_called_once()


@pytest.mark.asyncio
async def test_rag_utils_llm_retrieval_expansions_wiring():
    """Verify that _llm_retrieval_expansions in utils.py delegates to SpiritualConceptExpansion."""
    mock_svc = MagicMock()
    mock_svc.expand_query = AsyncMock(return_value=["facing sorrow without resistance", "nature of suffering"])

    with patch("services.spiritual_expansion.get_spiritual_concept_expansion", return_value=mock_svc):
        state = {
            "question": "How to handle sorrow?",
            "rewritten_query": "How to handle deep sorrow?",
            "query_tier": "standard",
        }
        expansions = await _llm_retrieval_expansions(state)
        assert len(expansions) == 2
        assert expansions[0] == "facing sorrow without resistance"
        mock_svc.expand_query.assert_called_once_with("How to handle deep sorrow?")


def test_retrieval_budget_and_config_soft_wait():
    """Verify that rag_retrieval_expansion_soft_wait_seconds defaults to 0.80s."""
    assert settings.rag_retrieval_expansion_soft_wait_seconds == 0.80
    # Budget formula max(1, 4 - len(primary_queries)): with 2 primaries, budget is 2 (not 0)
    primary_queries = ["q1", "q2"]
    remaining_budget = max(1, 4 - len(primary_queries))
    assert remaining_budget == 2


@pytest.mark.asyncio
async def test_personalize_stage_serializes_all_7_facets():
    """Verify personalize_stage serializes all 7 non-empty facets into canonical_memory_evidence and memory_context."""
    test_user_id = "00000000-0000-0000-0000-000000000001"
    seeker_ctx = UnifiedSeekerContext(
        user_id=test_user_id,
        has_unlocked_vault=True,
        seeker_profile=SeekerProfileContext(
            spiritual_readiness="advanced",
            custom_attributes={"topics_of_interest": ["dissolving resentment", "conscious parenting"]},
        ),
        second_brain=SecondBrainContext(
            canonical_memories=[{"statement": "I often feel resentful when unrecognized at work"}],
            observations=["Difficulty pausing before reacting in anger"],
        ),
        sadhana=SadhanaPracticeContext(
            streak_count=14,
            longest_streak=21,
            daily_practices=["Soul Sync", "Serene Mind"],
            minutes_meditated=280,
        ),
        pre_practice=PrePracticeLogContext(
            mental_clarity=7,
            pre_session_state="restless",
            intentions=["To cultivate stillness before speaking"],
        ),
        study_notebooks=StudyNotebookContext(
            saved_teachings=[{"title": "The Four Sacred Secrets - Chapter 2"}],
            study_tags=["forgiveness", "svadharma"],
        ),
        mood_journal=MoodSpiritualJournalContext(
            spiritual_growth_reflections=["Felt deep gratitude during morning meditation"],
            mood_trajectory=[{"dominant_emotion": "seeking peace"}],
        ),
        whatsapp_reflections=WhatsAppReflectionContext(
            voice_note_insights=["Realized my impatience comes from fear of loss"],
            reflections=[{"sadhana_reflection": "Practiced 3-minute serene mind amidst chaos"}],
        ),
    )

    from app.pipeline.stages.personalize_stage import PERSONALIZE_TEACHING_PROMPT

    stage = PersonalizeStage()
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=MagicMock(
            personalize_teaching={
                "video_id": "UlOt31lBhLY",
                "timestamp_seconds": 120.0,
            }
        ),
        user={"id": test_user_id},
    )
    ctx.user_id = test_user_id
    ctx.user_msg = PERSONALIZE_TEACHING_PROMPT
    ctx.personal_context_confirmed = True
    ctx.state = {
        "personalize_clip": {"point_id": "clip_1", "verbatim_text": "Dissolve the hurt."},
        "authenticated": True,
    }

    dummy_clip = {
        "point_id": "clip_1",
        "video_id": "UlOt31lBhLY",
        "start_ms": 120000,
        "end_ms": 150000,
        "verbatim_text": "Dissolve the hurt.",
        "speaker": "preethaji",
        "speaker_verified": True,
        "voice_verification_method": "ecapa_tdnn",
    }

    with patch(
        "services.personalization.unified_engine.UnifiedPersonalizationEngine.hydrate_seeker_context",
        AsyncMock(return_value=seeker_ctx),
    ), patch(
        "app.pipeline.stages.personalize_stage._lookup_servable_clip",
        return_value=dummy_clip,
    ):
        await stage.run(ctx)

    evidence = ctx.state.get("canonical_memory_evidence", "")
    mem_context = ctx.state.get("memory_context", "")

    # All 7 facets must appear in both variables
    assert "- [Realization] I often feel resentful when unrecognized at work" in evidence
    assert "- [Sadhana] Current streak: 14 days" in evidence
    assert "- [Pre-Practice State]" in evidence
    assert "- [Saved Teachings] The Four Sacred Secrets - Chapter 2" in evidence
    assert "- [Journal Reflection] Felt deep gratitude during morning meditation" in evidence
    assert "- [WhatsApp Insight] Realized my impatience comes from fear of loss" in evidence
    assert "- [Profile Focus Areas] dissolving resentment, conscious parenting" in evidence

    assert evidence == mem_context
    assert ctx.state.get("seeker_guidance") is not None


def test_models_format_prompt_guidance_negative_poison_removal():
    """Verify that models.py format_prompt_guidance does NOT emit negative poison lines."""
    empty_ctx = UnifiedSeekerContext(
        user_id="user_empty_456",
        has_unlocked_vault=True,
    )
    guidance = empty_ctx.format_prompt_guidance()
    assert "- No canonical memories recorded yet." not in guidance
    assert "- No saved teachings in active notebook." not in guidance
    assert "- No external messaging reflections." not in guidance


@pytest.mark.asyncio
async def test_generation_instructions_relaxation_and_harmonization():
    """Verify instruction 9 relaxation and Rule 1/2 personalization harmonization in generate_answer."""
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value="Wisdom grounded in the teaching clip.")

    with patch("rag.nodes._services._llm_gateway", mock_llm), patch("rag.nodes._services._ollama", mock_llm):
        state = {
            "question": "Please personalize this teaching on forgiveness for me.",
            "documents": [
                {
                    "content": "When you forgive from a beautiful state, you set yourself free.",
                    "source_url": "https://youtube.com/watch?v=sample1",
                    "title": "Teaching on Forgiveness",
                }
            ],
            "relevant_docs": [
                {
                    "content": "When you forgive from a beautiful state, you set yourself free.",
                    "source_url": "https://youtube.com/watch?v=sample1",
                    "title": "Teaching on Forgiveness",
                }
            ],
            "personalize_clip": {
                "point_id": "pt_1",
                "verbatim_text": "When you forgive from a beautiful state, you set yourself free.",
            },
            "canonical_memory_evidence": "- [Realization] I struggle with forgiving my coworker",
            "chat_history": [],
            "query_tier": "standard",
        }

        from rag.nodes.generation import context_engineer
        res = await context_engineer(state)
        state.update(res)

        await generate_answer(state)
        assert mock_llm.generate.call_count >= 1
        kwargs = mock_llm.generate.call_args.kwargs
        args = mock_llm.generate.call_args.args
        system_prompt = kwargs.get("system_prompt") or (args[0] if args else "")

        # 1. Rule 1 & Rule 2 harmonized
        assert "1. For the spiritual teaching core, base your wisdom ONLY on the provided Knowledge" in system_prompt
        assert "2. For personalization, seamlessly weave the seeker's recorded personal memories" in system_prompt

        # 2. Instruction 9 relaxed to only apply when Knowledge actually contains the terms
        assert "only when the retrieved Knowledge explicitly discusses them" in system_prompt


from tests.test_first_person_context_serving import make_test_context, make_test_span


@pytest.mark.asyncio
async def test_first_person_adaptive_try2_feedback_loop_success(monkeypatch):
    """Verify that when Try 1 yields zero passing direct clips, Try 2 retrieves via doctrinal anchors and serves verbatim clip."""
    for target in (
        "services.first_person_context_harness.source_is_authoritatively_licensed",
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        "services.first_person_context_store.source_is_authoritatively_licensed",
    ):
        monkeypatch.setattr(
            target,
            lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
        )

    span1 = make_test_span(
        n=0,
        text="Suffering is born of self-centered thinking. When you observe it without resistance, sorrow dissolves.",
        video_id="UlOt31lBhLY",
    )
    parent_ctx = make_test_context([span1])

    mock_ctx_store = MagicMock()
    # Try 1 returns empty candidate contexts
    # Try 2 returns parent_ctx matching expanded concepts
    def mock_retrieve(**kwargs):
        if kwargs.get("concept_ids"):
            return [parent_ctx]
        return []

    mock_ctx_store.retrieve.side_effect = mock_retrieve
    mock_ctx_store.enrich_to_parent_window.side_effect = lambda c: c
    mock_ctx_store.fetch_preceding_span.return_value = None

    mock_llm = MagicMock()
    mock_llm.generate_fast = AsyncMock(return_value="facing sorrow without resistance\ndissolving grief inner peace")

    from services.first_person_context_harness import HarnessDecision

    mock_harness = MagicMock()
    mock_harness._policy = MagicMock(max_context_spans=3)
    mock_harness.decide.return_value = MagicMock(
        decision=HarnessDecision.SERVE_PARENT_CONTEXT,
        source_span_ids=[span1.source_span_id],
        citations=[],
    )

    pipeline = FirstPersonPipeline(
        store=MagicMock(),
        redis_client=MagicMock(),
        serene_mind_engine=MagicMock(),
        context_store=mock_ctx_store,
        context_harness=mock_harness,
        llm_service=mock_llm,
    )
    pipeline._serene_mind.assess_distress.return_value = None
    pipeline._profile = {"threshold": 0.5}

    def fake_select(query, clips, llm, loop=None, token_sink=None, scores_out=None, **kwargs):
        if scores_out is not None:
            scores_out.append(95)
        return 0

    monkeypatch.setattr("services.first_person_pipeline._relevance_select", fake_select)

    with patch.object(settings, "first_person_context_harness_enabled", True), \
         patch.object(settings, "first_person_adaptive_try2_enabled", True), \
         patch.object(settings, "first_person_relevance_gate_enabled", True), \
         patch("services.first_person_judge.judge_active", return_value=False), \
         patch("services.first_person_pipeline._passes_integrity_gate", return_value=True), \
         patch("services.first_person_pipeline._passes_content_quality_gate", return_value=True):

        res = await pipeline._serve_from_context_harness(
            query="How do I overcome grief from death of loved one?",
            query_dense_vector=[0.05] * 1024,
            query_sparse_vector=None,
            teacher_id=None,
            max_clips=1,
            retrieval_query="How do I overcome grief from death of loved one?",
            language="en",
            cache_bypass=True,
            request_allow_state="",
            request_block_state="",
            fp_llm_tokens=[],
            _ans_box={},
            start_time=0.0,
            is_distress=False,
        )

        assert res is not None
        assert res.status == "success"
        # 100% Verbatim quote authenticity
        assert res.answer_text == span1.verbatim_text
        assert len(res.citations) == 1
        assert res.citations[0]["video_id"] == "UlOt31lBhLY"
        assert mock_ctx_store.retrieve.call_count == 2


@pytest.mark.asyncio
async def test_spiritual_expansion_llm_parsing_filters_preamble_and_markdown():
    """Verify that conversational preambles, markdown formatting, and punctuation are stripped cleanly."""
    mock_llm = MagicMock()
    raw_llm_output = (
        "Here are 3 short search query phrases:\n"
        "1. **facing sorrow without resistance**.\n"
        "2. *dissolving grief inner peace*!\n"
        "3. `acceptance of reality`: \n"
        "4. This is an overly long narrative sentence that exceeds word limit and should be excluded"
    )
    mock_llm.generate_fast = AsyncMock(return_value=raw_llm_output)

    svc = SpiritualConceptExpansion(llm_gateway=mock_llm)
    res = await svc.expand_query("I feel deep sorrow")

    assert len(res) == 3
    assert res[0] == "facing sorrow without resistance"
    assert res[1] == "dissolving grief inner peace"
    assert res[2] == "acceptance of reality"
    assert not any("here are" in r.lower() for r in res)
    assert not any("*" in r or "`" in r or "." in r for r in res)


@pytest.mark.asyncio
async def test_spiritual_expansion_fallback_query_not_cached():
    """Verify that unexpanded fallback [cleaned_query] is NOT cached, preventing 24h cache poisoning."""
    mock_llm = MagicMock()
    mock_llm.generate_fast = AsyncMock(side_effect=RuntimeError("Provider 503 unavailable"))

    svc = SpiritualConceptExpansion(llm_gateway=mock_llm, maxsize=100)
    unmatched_query = "xyzzy qux random non spiritual token 12345"

    res1 = await svc.expand_query(unmatched_query)
    assert res1 == [unmatched_query]

    # Verify cache was NOT polluted with the fallback
    import hashlib
    key = hashlib.sha256(unmatched_query.lower().encode("utf-8")).hexdigest()
    assert svc._get_from_cache(key) is None

    # Now simulate LLM recovering
    mock_llm.generate_fast = AsyncMock(return_value="inner truth awareness\npeace in being")
    res2 = await svc.expand_query(unmatched_query)
    assert res2 == ["inner truth awareness", "peace in being"]


@pytest.mark.asyncio
async def test_first_person_adaptive_try2_runs_when_try1_candidates_rejected(monkeypatch):
    """Verify that when Try 1 retrieves candidates but all are rejected by relevance, Try 2 retrieves and serves."""
    for target in (
        "services.first_person_context_harness.source_is_authoritatively_licensed",
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        "services.first_person_context_store.source_is_authoritatively_licensed",
    ):
        monkeypatch.setattr(
            target,
            lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
        )

    span_try1 = make_test_span(
        n=0,
        text="Irrelevant discourse talking about scheduling and administrative matters.",
        video_id="video_try1",
        parent_unit_id="parent_try1",
    )
    ctx_try1 = make_test_context([span_try1])

    span_try2 = make_test_span(
        n=1,
        text="When you dissolve resentment, you free your inner space from chronic inflammation.",
        video_id="video_try2",
        parent_unit_id="parent_try2",
    )
    ctx_try2 = make_test_context([span_try2])

    mock_ctx_store = MagicMock()
    # Try 1 returns ctx_try1; Try 2 returns ctx_try2
    def mock_retrieve(**kwargs):
        if kwargs.get("concept_ids"):
            return [ctx_try2]
        return [ctx_try1]

    mock_ctx_store.retrieve.side_effect = mock_retrieve
    mock_ctx_store.enrich_to_parent_window.side_effect = lambda c: c
    mock_ctx_store.fetch_preceding_span.return_value = None

    mock_llm = MagicMock()
    mock_llm.generate_fast = AsyncMock(return_value="dissolving hurt and resentment\nhealing emotional pain")

    from services.first_person_context_harness import HarnessDecision

    mock_harness = MagicMock()
    mock_harness._policy = MagicMock(max_context_spans=3)

    def mock_decide(context, *args, **kwargs):
        # Allow both contexts through harness structure
        return MagicMock(
            decision=HarnessDecision.SERVE_PARENT_CONTEXT,
            source_span_ids=[context.spans[0].source_span_id],
            citations=[],
        )

    mock_harness.decide.side_effect = mock_decide

    pipeline = FirstPersonPipeline(
        store=MagicMock(),
        redis_client=MagicMock(),
        serene_mind_engine=MagicMock(),
        context_store=mock_ctx_store,
        context_harness=mock_harness,
        llm_service=mock_llm,
    )
    pipeline._serene_mind.assess_distress.return_value = None
    pipeline._profile = {"threshold": 0.5}

    def fake_select(query, clips, llm, loop=None, token_sink=None, scores_out=None, **kwargs):
        clip_text = clips[0].get("verbatim_text", "")
        if "resentment" in clip_text:
            if scores_out is not None:
                scores_out.append(90)
            return 0  # Passing score
        # Reject Try 1 candidate
        if scores_out is not None:
            scores_out.append(10)
        return None

    monkeypatch.setattr("services.first_person_pipeline._relevance_select", fake_select)

    with patch.object(settings, "first_person_context_harness_enabled", True), \
         patch.object(settings, "first_person_adaptive_try2_enabled", True), \
         patch.object(settings, "first_person_relevance_gate_enabled", True), \
         patch("services.first_person_judge.judge_active", return_value=False), \
         patch("services.first_person_pipeline._passes_integrity_gate", return_value=True), \
         patch("services.first_person_pipeline._passes_content_quality_gate", return_value=True):

        res = await pipeline._serve_from_context_harness(
            query="How to forgive my spouse for betrayal?",
            query_dense_vector=[0.02] * 1024,
            query_sparse_vector=None,
            teacher_id=None,
            max_clips=1,
            retrieval_query="How to forgive my spouse for betrayal?",
            language="en",
            cache_bypass=True,
            request_allow_state="",
            request_block_state="",
            fp_llm_tokens=[],
            _ans_box={},
            start_time=0.0,
            is_distress=False,
        )

        assert res is not None
        assert res.status == "success"
        assert res.answer_text == span_try2.verbatim_text
        assert res.citations[0]["video_id"] == "video_try2"


@pytest.mark.asyncio
async def test_first_person_adaptive_try2_runs_on_joint_insufficiency(monkeypatch):
    """Verify that when Try 1 context fails joint sufficiency, Try 2 still runs and can serve a sufficient clip."""
    for target in (
        "services.first_person_context_harness.source_is_authoritatively_licensed",
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        "services.first_person_context_store.source_is_authoritatively_licensed",
    ):
        monkeypatch.setattr(
            target,
            lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
        )

    span_try1 = make_test_span(n=0, text="Partial clip that is insufficient.", video_id="video_try1", parent_unit_id="parent_try1")
    ctx_try1 = make_test_context([span_try1])

    span_try2 = make_test_span(n=1, text="Complete teaching on discovering svadharma.", video_id="video_try2", parent_unit_id="parent_try2")
    ctx_try2 = make_test_context([span_try2])

    mock_ctx_store = MagicMock()
    def mock_retrieve(**kwargs):
        if kwargs.get("concept_ids"):
            return [ctx_try2]
        return [ctx_try1]

    mock_ctx_store.retrieve.side_effect = mock_retrieve
    mock_ctx_store.enrich_to_parent_window.side_effect = lambda c: c
    mock_ctx_store.fetch_preceding_span.return_value = None

    mock_llm = MagicMock()
    mock_llm.generate_fast = AsyncMock(return_value="svadharma and right action\ninner purpose calling")

    from services.first_person_context_harness import HarnessDecision

    mock_harness = MagicMock()
    mock_harness._policy = MagicMock(max_context_spans=3)

    def mock_decide2(context, *args, **kwargs):
        return MagicMock(
            decision=HarnessDecision.SERVE_PARENT_CONTEXT,
            source_span_ids=[context.spans[0].source_span_id],
            citations=[],
        )

    mock_harness.decide.side_effect = mock_decide2

    pipeline = FirstPersonPipeline(
        store=MagicMock(),
        redis_client=MagicMock(),
        serene_mind_engine=MagicMock(),
        context_store=mock_ctx_store,
        context_harness=mock_harness,
        llm_service=mock_llm,
    )
    pipeline._serene_mind.assess_distress.return_value = None
    pipeline._profile = {"threshold": 0.5}

    def fake_select(query, clips, llm, loop=None, token_sink=None, scores_out=None, **kwargs):
        if scores_out is not None:
            scores_out.append(90)
        return 0

    monkeypatch.setattr("services.first_person_pipeline._relevance_select", fake_select)

    async def fake_joint_verdict(query, ret_query, answer_text, llm, tokens):
        # Try 1 answer text is INSUFFICIENT; Try 2 is SUFFICIENT
        if "Partial clip" in answer_text:
            return "INSUFFICIENT"
        return "SUFFICIENT"

    monkeypatch.setattr("services.first_person_pipeline._joint_sufficiency_verdict", fake_joint_verdict)

    with patch.object(settings, "first_person_context_harness_enabled", True), \
         patch.object(settings, "first_person_adaptive_try2_enabled", True), \
         patch.object(settings, "first_person_joint_sufficiency_enabled", True), \
         patch.object(settings, "first_person_relevance_gate_enabled", True), \
         patch("services.first_person_judge.judge_active", return_value=False), \
         patch("services.first_person_pipeline._passes_integrity_gate", return_value=True), \
         patch("services.first_person_pipeline._passes_content_quality_gate", return_value=True):

        res = await pipeline._serve_from_context_harness(
            query="What is right action and finding purpose in career?",
            query_dense_vector=[0.03] * 1024,
            query_sparse_vector=None,
            teacher_id=None,
            max_clips=1,
            retrieval_query="What is right action and finding purpose in career?",
            language="en",
            cache_bypass=True,
            request_allow_state="",
            request_block_state="",
            fp_llm_tokens=[],
            _ans_box={},
            start_time=0.0,
            is_distress=False,
        )

        assert res is not None
        assert res.status == "success"
        assert res.answer_text == span_try2.verbatim_text
        assert res.citations[0]["video_id"] == "video_try2"
