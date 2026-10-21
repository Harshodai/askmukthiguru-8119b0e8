"""Tests for worldly-query recognition and general-knowledge routing.

Covers known non-doctrinal families, spiritual-domain exclusions, fail-open
behavior, general-route markers, stage order, and cache isolation so a worldly
query is never served an unrelated cached teaching. No live LLM calls.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.pipeline.stages import CacheCheckStage
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.doctrine_cache_stage import DoctrineCacheStage
from app.pipeline.stages.off_topic_stage import (
    OffTopicStage,
    build_off_topic_response,
    is_off_topic,
    is_spiritual_domain_query,
    off_topic_handler_enabled,
)
from app.pipeline.stages.pipeline_builder import build_default_pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_ctx(question: str) -> PipelineContext:
    return PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg=question,
        preferred_lang="en",
        session_id="sess-off-topic",
        trace_id="trace-off-topic",
        start_time=time.time(),
        state={"user_msg_en": question},
    )


# ---------------------------------------------------------------------------
# 1. Off-topic queries trigger
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        # --- original ad-hoc cases (kept) ---
        "What is the capital of France?",
        "what is the CAPITAL of france",
        "Give me stock tips for next week",
        "Which stocks should I invest in?",
        "Can you diagnose my chest pain?",
        "What disease do I have based on these symptoms?",
        "Should I buy bitcoin or mutual funds?",
        "Who will win the election?",
        "What is the cricket score?",
        "Write me Python code to debug my API error",
        "Give me legal advice for my property dispute",
        "Share a chicken biryani recipe",
        # --- W4 gold extension: geography/civics family ---
        "What is the population of France?",
        "Which country has the longest river?",
        "Who is the president of France?",
        "What is the tallest mountain in the world?",
        # --- W4 gold extension: stock/money family ---
        "Should I buy Nifty intraday calls?",
        "How do I file taxes on my mutual fund gains?",
        "What are the best stocks to invest in?",
        # --- W4 gold extension: medical family ---
        "What dosage of antibiotics should I take?",
        "Is chemotherapy right for my tumour?",
        "Can you diagnose my diabetes symptoms?",
        # --- W4 gold extension: crypto family ---
        "Will bitcoin reach a new high this year?",
        "Give me crypto trading tips",
        # --- W4 gold extension: politics family ---
        "Who will win the election, BJP or Congress?",
        "What did Trump say in parliament today?",
        # --- W4 gold extension: sports family ---
        "Who won the IPL match yesterday?",
        "When is the football world cup?",
        "Who will win the cricket world cup match?",
        # --- W4 gold extension: coding family ---
        "Solve this leetcode problem with an SQL query",
        "Write me code to fix my javascript error",
        # --- W4 gold extension: legal family ---
        "Can I sue my neighbour over a property dispute?",
        "How do I get a divorce? I need legal advice",
        # --- W4 gold extension: recipes/travel family ---
        "How do I cook chicken biryani at home?",
        "I need a hotel booking for tonight",
    ],
)
def test_off_topic_triggers(question: str) -> None:
    assert is_off_topic(question) is True


# ---------------------------------------------------------------------------
# 2. On-topic queries never trigger
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        # --- original ad-hoc cases (kept) ---
        "What is meditation?",
        "What is the Beautiful State?",
        "What is deeksha?",
        "What is the relationship between suffering and consciousness?",
        "How does Soul Sync breath bring calm?",
        "Tell me about Ekam and oneness",
        "How do I deal with anxiety and stress?",
        "What do the teachings say about forgiveness?",
        "hello",  # unrecognized -> fail-open, legacy path owns it
        "",  # empty -> fail-open
        # --- W4 gold extension: one anchor per doctrine family ---
        "How can meditation help me sleep better?",  # meditation
        "How do I experience the Beautiful State?",  # Beautiful State
        "What happens during deeksha?",  # deeksha
        "Why do we suffer even when life is good?",  # suffering
        "What is Ekam?",  # Ekam
        "What is Soul Sync?",  # Soul Sync
    ],
)
def test_on_topic_or_unrecognized_queries_do_not_match_worldly_regex(question: str) -> None:
    # This legacy keyword predicate is not the whole router: domain classification
    # treats unknown queries as general, while this predicate stays narrow.
    assert is_off_topic(question) is False


def test_explicit_teaching_requests_beat_incidental_worldly_terms() -> None:
    # Explicit intent to discuss the teaching remains in the teaching route.
    assert is_off_topic("What does Sri Krishnaji teach about meditation and the stock market?") is False
    assert is_off_topic("What is the difference between meditation and contemplation?") is False


@pytest.mark.parametrize(
    "question",
    [
        "Should I invest in stocks to fund my Ekam visit?",
        "Tell me about deeksha and the stock market crash",
        "How does meditation help when I stress about the stock market?",
    ],
)
def test_general_task_cues_override_incidental_teaching_keywords(question: str) -> None:
    assert is_off_topic(question) is True
    assert is_spiritual_domain_query(question) is False


# ---------------------------------------------------------------------------
# 3. Refusal copy: honest, brief, on-brand, no fabricated teachings
# ---------------------------------------------------------------------------


def test_refusal_copy_honest_and_redirects() -> None:
    copy = build_off_topic_response()
    assert "have not spoken about this" in copy
    assert "will not guess" in copy
    assert "Beautiful State" in copy and "deeksha" in copy
    assert len(copy) <= 800
    # No fabricated teachings: never quotes the teachers or states doctrine.
    for forbidden in ("Krishnaji says", "Preethaji says", "\u201c", "\u201d", '"'):
        assert forbidden not in copy


# ---------------------------------------------------------------------------
# 4. Flag default ON (W4 enablement) + live-pipeline wiring order
# ---------------------------------------------------------------------------


def test_flag_defaults_on() -> None:
    # W4 (2026-10-11): gold gates passed, default flipped False -> True.
    # Kill switch remains env OFF_TOPIC_HANDLER_ENABLED=false.
    from app.config import settings

    assert settings.off_topic_handler_enabled is True
    assert off_topic_handler_enabled() is True


def test_live_pipeline_wires_general_routing_after_distress() -> None:
    names = [stage.name for stage in build_default_pipeline()]
    assert "off_topic_short_circuit" in names
    # Load-bearing order: distress preempts before worldly classification;
    # general routing happens before retrieval (including the FP bridge).
    assert names.index("distress_detection") < names.index("off_topic_short_circuit")
    assert names.index("off_topic_short_circuit") < names.index("bounded_comparison_short_circuit")
    assert names.index("off_topic_short_circuit") < names.index("langgraph")


def test_off_topic_stage_exported_from_stages_package() -> None:
    from app.pipeline.stages import OffTopicStage as Exported
    from app.pipeline.stages.off_topic_stage import OffTopicStage as Direct

    assert Exported is Direct


@pytest.mark.asyncio
async def test_stage_passes_through_everything_when_flag_explicitly_off(
    monkeypatch,
) -> None:
    import app.pipeline.stages.off_topic_stage as mod

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: False)
    stage = OffTopicStage()
    for question in (
        "What is the capital of France?",
        "Give me stock tips",
        "What is meditation?",
    ):
        assert await stage.run(_build_ctx(question)) is None


# ---------------------------------------------------------------------------
# 5. Flag-on: short-circuit shape (monkeypatched flag, still no LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage_routes_worldly_question_to_general_answering(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    ctx = _build_ctx("What is the capital of France?")
    result = await OffTopicStage().run(ctx)
    assert result is None
    assert ctx.state["general_knowledge_mode"] is True
    assert ctx.route_metadata["selected_variant"] == "general_knowledge"


@pytest.mark.asyncio
async def test_ambiguous_spiritual_keyword_uses_jev_general_decision(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", True)
    mock_router = MagicMock()
    mock_router.classify = AsyncMock(return_value={
        "intent": "FACTUAL",
        "domain_route": "general",
        "general_knowledge_mode": True,
        "needs_web_search": False,
        "query_tier": "tier2_simple",
        "confidence": 0.91,
        "latency_ms": 84.0,
    })
    monkeypatch.setattr(
        "services.jev_router_service.JevRouterService",
        lambda **kwargs: mock_router,
    )

    ctx = _build_ctx("Can meditation help with anxiety?")
    await OffTopicStage().run(ctx)

    assert ctx.state["general_knowledge_mode"] is True
    assert ctx.state["domain_route"] == "general"
    assert ctx.preclassified_intent == "FACTUAL"
    assert ctx.preclassified_tier == "tier2_simple"
    assert ctx.route_metadata["decision_method"] == "jev_ambiguous_domain"
    mock_router.classify.assert_awaited_once_with("Can meditation help with anxiety?")


@pytest.mark.asyncio
async def test_ambiguous_spiritual_keyword_uses_jev_teaching_decision(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", True)
    mock_router = MagicMock()
    mock_router.classify = AsyncMock(return_value={
        "intent": "FACTUAL",
        "domain_route": "teaching",
        "general_knowledge_mode": False,
        "needs_web_search": False,
        "query_tier": "tier3_complex",
        "confidence": 0.89,
        "latency_ms": 91.0,
    })
    monkeypatch.setattr(
        "services.jev_router_service.JevRouterService",
        lambda **kwargs: mock_router,
    )

    ctx = _build_ctx("Can meditation help with anxiety?")
    await OffTopicStage().run(ctx)

    assert ctx.state["general_knowledge_mode"] is False
    assert ctx.state["domain_route"] == "teaching"
    assert ctx.route_metadata["selected_variant"] == "first_person"
    mock_router.classify.assert_awaited_once()


@pytest.mark.asyncio
async def test_ambiguous_domain_router_failure_does_not_invent_teacher_attribution(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", True)
    mock_router = MagicMock()
    mock_router.classify = AsyncMock(side_effect=TimeoutError())
    monkeypatch.setattr(
        "services.jev_router_service.JevRouterService",
        lambda **kwargs: mock_router,
    )

    ctx = _build_ctx("What is anxiety?")
    await OffTopicStage().run(ctx)

    assert ctx.state["general_knowledge_mode"] is True
    assert ctx.state["domain_route"] == "general"
    assert ctx.preclassified_reason == "ambiguous_domain_safe_fallback"


@pytest.mark.asyncio
async def test_explicit_teaching_request_skips_jev_ambiguity_call(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", True)
    mock_router = MagicMock()
    mock_router.classify = AsyncMock()
    monkeypatch.setattr(
        "services.jev_router_service.JevRouterService",
        lambda **kwargs: mock_router,
    )

    ctx = _build_ctx("What does Sri Krishnaji teach about anxiety?")
    await OffTopicStage().run(ctx)

    assert "general_knowledge_mode" not in ctx.state
    assert ctx.route_metadata["domain_route"] == "teaching"
    mock_router.classify.assert_not_awaited()


@pytest.mark.asyncio
async def test_guided_practice_is_not_routed_as_generic_ambiguous_question(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", True)
    mock_router = MagicMock()
    mock_router.classify = AsyncMock()
    monkeypatch.setattr(
        "services.jev_router_service.JevRouterService",
        lambda **kwargs: mock_router,
    )

    ctx = _build_ctx("Please guide me through a meditation for anxiety.")
    await OffTopicStage().run(ctx)

    assert ctx.route_metadata["domain_route"] == "guided_practice"
    assert "general_knowledge_mode" not in ctx.state
    mock_router.classify.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_domain_router_is_bounded_and_uses_configured_timeout(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_timeout_s", 0.12)
    mock_router = MagicMock()
    async def slow_classify(question):
        await asyncio.sleep(1)
    mock_router.classify = slow_classify
    captured = {}
    def make_router(**kwargs):
        captured.update(kwargs)
        return mock_router
    monkeypatch.setattr("services.jev_router_service.JevRouterService", make_router)

    ctx = _build_ctx("Can meditation help with anxiety?")
    await OffTopicStage().run(ctx)

    assert captured["timeout_s"] == pytest.approx(0.12)
    assert ctx.state["general_knowledge_mode"] is True
    assert ctx.preclassified_reason == "ambiguous_domain_safe_fallback"


@pytest.mark.asyncio
async def test_stage_passes_on_topic_through_when_flag_on(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    # These examples test the deterministic non-ambiguous pass-through only;
    # semantic Jev decisions are mocked in their own tests below.
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", False)
    for question in (
        "What is meditation?",
        "What is the Beautiful State?",
        "What is deeksha?",
    ):
        assert await OffTopicStage().run(_build_ctx(question)) is None


# ---------------------------------------------------------------------------
# 6. Cache bypasses: CacheCheck + DoctrineCache skip worldly Qs (flag-gated).
#     Crisis path untouched — these tests never send crisis keywords.
# ---------------------------------------------------------------------------


def _cache_ctx(question: str) -> PipelineContext:
    container = MagicMock()
    container.exact_cache.get.return_value = None
    container.semantic_cache.is_available = False
    return PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg=question,
        preferred_lang="en",
        session_id="sess-off-topic-cache",
        trace_id="trace-off-topic-cache",
        start_time=time.time(),
        cache_key=f"ck:en:{question}",
        query_for_embedding=question,
        state={"user_msg_en": question},
    )


@pytest.mark.asyncio
async def test_cache_check_bypasses_off_topic_when_flag_on(monkeypatch) -> None:
    """Flag on: CacheCheckStage must not consult any cache tier for a worldly
    question (a hit would preempt the honest decline)."""
    import app.pipeline.stages.off_topic_stage as mod
    import services.hot_cache as hc

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    hc.hot_cache._store.clear()
    ctx = _cache_ctx("What is the capital of France?")

    result = await CacheCheckStage().run(ctx)

    assert result is None
    ctx.container.exact_cache.get.assert_not_called()


@pytest.mark.asyncio
async def test_cache_check_bypasses_general_questions_even_when_legacy_flag_off(monkeypatch) -> None:
    """Cache isolation is a safety/correctness boundary, not a feature-flagged refusal."""
    import app.pipeline.stages.off_topic_stage as mod
    import services.hot_cache as hc

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: False)
    hc.hot_cache._store.clear()
    ctx = _cache_ctx("What is the capital of France?")

    result = await CacheCheckStage().run(ctx)

    assert result is None
    ctx.container.exact_cache.get.assert_not_called()


@pytest.mark.asyncio
async def test_doctrine_cache_bypasses_off_topic_when_flag_on(monkeypatch) -> None:
    """Flag on: DoctrineCacheStage must not serve a doctrine hit for a worldly
    question even when lookup() fuzzy-matches."""
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "doctrine_cache_enabled", True)
    ctx = _cache_ctx("What is the capital of France?")
    hit = MagicMock()
    hit.answer = "Doctrine answer."
    hit.citations = [{"id": "c1"}]
    ctx.container.doctrine_cache.lookup.return_value = hit

    result = await DoctrineCacheStage().run(ctx)

    assert result is None
    ctx.container.doctrine_cache.lookup.assert_not_called()


@pytest.mark.asyncio
async def test_doctrine_cache_never_serves_general_question_even_when_legacy_flag_off(monkeypatch) -> None:
    """A broad feature kill-switch must not re-enable cross-domain cache leakage."""
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: False)
    monkeypatch.setattr(settings, "doctrine_cache_enabled", True)
    ctx = _cache_ctx("What is the capital of France?")
    hit = MagicMock()
    hit.answer = "Doctrine answer."
    hit.citations = [{"id": "c1"}]
    ctx.container.doctrine_cache.lookup.return_value = hit

    result = await DoctrineCacheStage().run(ctx)

    assert result is None
    ctx.container.doctrine_cache.lookup.assert_not_called()


# ---------------------------------------------------------------------------
# 7. General questions are routed by domain, not forced into the teaching corpus
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "How do I debug a Python traceback?",
        "What is the capital of France?",
        "Can you explain how a mortgage works?",
        "How do I change line spacing in a Word document?",
        "Explain the neuroscience of fear.",
        "Explain the psychology of meditation.",
        "Can you explain CBT for anxiety?",
        "What are common side effects of this medication?",
        "Can you summarize a clinical trial about mindfulness?",
        "Write an email about gratitude.",
    ],
)
def test_general_questions_have_no_spiritual_domain_claim(question: str) -> None:
    from app.pipeline.stages.off_topic_stage import is_spiritual_domain_query

    assert is_spiritual_domain_query(question) is False


@pytest.mark.parametrize(
    "question",
    [
        "What does Sri Krishnaji teach about stillness?",
        "How can I find inner peace?",
        "What is the Beautiful State?",
        "What does Sri Krishnaji teach about CBT?",
        "What do Sri Preethaji's recorded teachings say about the neuroscience of fear?",
    ],
)
def test_teaching_domain_questions_keep_first_person_eligibility(question: str) -> None:
    from app.pipeline.stages.off_topic_stage import is_spiritual_domain_query

    assert is_spiritual_domain_query(question) is True


def test_first_person_router_yields_for_general_knowledge_queries() -> None:
    from rag.pipeline_registry import _first_person_claims

    assert not _first_person_claims(
        {"question": "How do I debug a Python traceback?", "general_knowledge_mode": False}
    )
    assert not _first_person_claims(
        {"question": "What is meditation?", "general_knowledge_mode": True}
    )
    assert _first_person_claims(
        {"question": "What does Sri Krishnaji teach about stillness?"}
    )


# ---------------------------------------------------------------------------
# 8. Memory recall is relevance-gated, not removed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "What is the capital of France?",
        "How do I debug this Python traceback?",
        "Explain SQL window functions.",
        "What is the latest version of Kubernetes?",
    ],
)
def test_plain_general_questions_skip_long_term_memory(question: str) -> None:
    from app.pipeline.stages.off_topic_stage import should_skip_long_term_memory

    assert should_skip_long_term_memory(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "What do you remember about my goals?",
        "Based on my preferences, recommend a career path for me.",
        "What about that?",
        "I feel overwhelmed and want to find inner peace.",
        "What does Sri Krishnaji teach about stillness?",
    ],
)
def test_personal_spiritual_and_followup_questions_keep_memory(question: str) -> None:
    from app.pipeline.stages.off_topic_stage import should_skip_long_term_memory

    assert should_skip_long_term_memory(question) is False


def test_teacher_alias_routing_uses_configured_registry(monkeypatch) -> None:
    """New teacher aliases work through the registry, not route-level hardcoding."""
    import services.guru_registry as registry
    from app.pipeline.stages.off_topic_stage import (
        has_explicit_teaching_intent,
        is_spiritual_domain_query,
    )

    monkeypatch.setattr(
        registry,
        "requested_gurus",
        lambda query: ["future_teacher"] if "Amma" in query else [],
    )
    assert has_explicit_teaching_intent("Quote Amma on compassion")
    assert is_spiritual_domain_query("Quote Amma on compassion")
    # A teacher's name or a figurative use of "teach" alone is not a request
    # for recorded teacher discourse.
    assert not is_spiritual_domain_query("Write a report about Sri Preethaji's event.")
    assert not is_spiritual_domain_query("What does climate change teach us?")
