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
    assert (
        is_off_topic("What does Sri Krishnaji teach about meditation and the stock market?")
        is False
    )
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


@pytest.mark.parametrize(
    "question",
    [
        "how do I calm my mind before a cricket match",
        "I'm nervous before my exam, how do I stay calm?",
    ],
)
def test_inner_help_with_soft_secular_context_stays_teaching(question: str) -> None:
    assert is_off_topic(question) is False


@pytest.mark.parametrize(
    "question",
    ["write python code for a meditation timer", "Who won the cricket match?"],
)
def test_general_tasks_and_secular_questions_unchanged(question: str) -> None:
    assert is_off_topic(question) is True


# ---------------------------------------------------------------------------
# 3. Refusal copy: honest, brief, on-brand, no fabricated teachings
# ---------------------------------------------------------------------------


def test_refusal_copy_honest_and_redirects() -> None:
    copy = build_off_topic_response()
    assert "outside what I can speak to" in copy
    assert "will not attribute a guess" in copy
    assert "\n\n" in copy
    assert r"\n\n" not in copy
    assert len(copy) <= 800
    # No fabricated teacher attribution or hard-coded doctrine examples.
    for forbidden in ("Krishnaji says", "Preethaji says", "“", "”", '"'):
        assert forbidden not in copy


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
async def test_stage_routes_worldly_question_to_domain_boundary(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    ctx = _build_ctx("What is the capital of France?")
    result = await OffTopicStage().run(ctx)
    assert result is not None
    assert result.route_decision == "off_topic_domain_boundary"
    assert result.final_answer == build_off_topic_response()
    assert result.citations == []

    # With domain boundary disabled, falls back to legacy general_knowledge_mode
    monkeypatch.setattr(mod, "off_topic_domain_boundary_enabled", lambda: False)
    ctx_legacy = _build_ctx("What is the capital of France?")
    result_legacy = await OffTopicStage().run(ctx_legacy)
    assert result_legacy is None
    assert ctx_legacy.state["general_knowledge_mode"] is True
    assert ctx_legacy.route_metadata["selected_variant"] == "general_knowledge"


@pytest.mark.asyncio
async def test_medical_question_refusal_points_to_qualified_help(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    result = await OffTopicStage().run(_build_ctx("Diagnose my chest pain"))
    assert result is not None
    assert "qualified healthcare professional" in result.final_answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "My wife and I fight every day, what do I do?",
        "I feel lost and empty, what should I do?",
        "Why do I keep failing in life?",
        "My son does not talk to me anymore",
        "I am so lonely",
        "how do I calm my mind before a cricket match",
        "I'm nervous before my exam, how do I stay calm?",
        "मेरी पत्नी और मैं रोज़ लड़ते हैं, क्या करूँ?",
    ],
)
async def test_unknown_life_questions_default_to_teaching(monkeypatch, question) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", False)
    ctx = _build_ctx(question)
    assert await OffTopicStage().run(ctx) is None
    assert not ctx.state.get("general_knowledge_mode")
    assert ctx.state["domain_route"] == "teaching"


@pytest.mark.asyncio
async def test_inner_help_exempts_domain_boundary_when_task_cue_present(monkeypatch) -> None:
    """An emotional-help cue is not refused by the domain boundary despite a task cue."""
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", False)
    ctx = _build_ctx("Help me write a report on staying nervous before an exam")
    # No static domain-boundary refusal: the inner-help cue keeps the general lane.
    assert await OffTopicStage().run(ctx) is None
    assert ctx.state.get("domain_route") == "general"


@pytest.mark.asyncio
async def test_jev_general_on_ambiguous_spiritual_question_stays_teaching(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    class _Router:
        def __init__(self, *a, **k) -> None: ...

        async def classify(self, q):
            return {"domain_route": "general", "confidence": 0.95}

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", True)
    monkeypatch.setattr("services.jev_router_service.JevRouterService", _Router)
    q = next(
        c
        for c in ("What does karma mean?", "What is dharma?", "What is meditation?")
        if mod.is_spiritual_domain_query(c) and mod._AMBIGUOUS_DOMAIN_RE.search(c)
    )
    ctx = _build_ctx(q)
    await OffTopicStage().run(ctx)
    assert not ctx.state.get("general_knowledge_mode")


@pytest.mark.asyncio
async def test_live_info_question_returns_canned_reply_without_llm(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from services.voice.register import LIVE_INFO_UNAVAILABLE

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    result = await OffTopicStage().run(_build_ctx("What's happening today?"))
    assert result is not None
    assert result.final_answer == LIVE_INFO_UNAVAILABLE
    assert result.model_used is None
    assert result.route_decision == "live_info_unavailable"


@pytest.mark.asyncio
async def test_unmatched_general_question_defaults_to_teaching(
    monkeypatch,
) -> None:
    import app.pipeline.stages.off_topic_stage as mod

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    ctx = _build_ctx("Why do leaves change color in autumn?")
    result = await OffTopicStage().run(ctx)
    # No secular match: defaults to teaching (L-ROUTING-FALLTHROUGH-2).
    assert result is None
    assert not ctx.state.get("general_knowledge_mode")
    assert ctx.route_metadata["domain_route"] == "teaching"


@pytest.mark.asyncio
async def test_ambiguous_spiritual_keyword_ignores_jev_general_decision(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", True)
    mock_router = MagicMock()
    mock_router.classify = AsyncMock(
        return_value={
            "intent": "FACTUAL",
            "domain_route": "general",
            "general_knowledge_mode": True,
            "needs_web_search": False,
            "query_tier": "tier2_simple",
            "confidence": 0.91,
            "latency_ms": 84.0,
        }
    )
    monkeypatch.setattr(
        "services.jev_router_service.JevRouterService",
        lambda **kwargs: mock_router,
    )

    ctx = _build_ctx("Can meditation help with anxiety?")
    await OffTopicStage().run(ctx)

    # Jev "general" on a spiritual-candidate question is not enough.
    assert not ctx.state.get("general_knowledge_mode")
    assert ctx.state["domain_route"] == "teaching"
    mock_router.classify.assert_awaited_once_with("Can meditation help with anxiety?")


@pytest.mark.asyncio
async def test_ambiguous_spiritual_keyword_uses_jev_teaching_decision(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", True)
    mock_router = MagicMock()
    mock_router.classify = AsyncMock(
        return_value={
            "intent": "FACTUAL",
            "domain_route": "teaching",
            "general_knowledge_mode": False,
            "needs_web_search": False,
            "query_tier": "tier3_complex",
            "confidence": 0.89,
            "latency_ms": 91.0,
        }
    )
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


@pytest.mark.parametrize("confidence", [0.69, float("nan"), float("inf"), -0.1, 1.1, True, None])
@pytest.mark.asyncio
async def test_invalid_or_low_jev_confidence_cannot_authorize_teaching_route(
    monkeypatch, confidence
) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", True)
    mock_router = MagicMock()
    mock_router.classify = AsyncMock(
        return_value={
            "intent": "FACTUAL",
            "domain_route": "teaching",
            "general_knowledge_mode": False,
            "needs_web_search": False,
            "query_tier": "tier3_complex",
            "confidence": confidence,
            "latency_ms": 91.0,
        }
    )
    monkeypatch.setattr(
        "services.jev_router_service.JevRouterService",
        lambda **kwargs: mock_router,
    )

    ctx = _build_ctx("Can meditation help with anxiety?")
    await OffTopicStage().run(ctx)

    assert ctx.state["general_knowledge_mode"] is False
    assert ctx.state["domain_route"] == "teaching"
    assert ctx.route_metadata["decision_method"] == "ambiguous_domain_teaching_default"
    assert ctx.route_metadata["selected_variant"] == "first_person"


@pytest.mark.asyncio
async def test_ambiguous_domain_router_failure_does_not_invent_teacher_attribution(
    monkeypatch,
) -> None:
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

    assert ctx.state["general_knowledge_mode"] is False
    assert ctx.state["domain_route"] == "teaching"
    assert ctx.route_metadata["decision_method"] == "ambiguous_domain_teaching_default"


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
    assert ctx.state["general_knowledge_mode"] is False
    assert ctx.route_metadata["decision_method"] == "ambiguous_domain_teaching_default"


@pytest.mark.parametrize(
    "question",
    ["Why do I feel so anxious all the time?", "मैं हमेशा चिंतित क्यों रहता हूँ?"],
)
@pytest.mark.asyncio
async def test_unmatched_or_non_english_emotional_text_defaults_to_teaching(
    monkeypatch, question
) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", True)
    mock_router = MagicMock()
    mock_router.classify = AsyncMock(side_effect=TimeoutError())
    monkeypatch.setattr("services.jev_router_service.JevRouterService", lambda **kw: mock_router)

    ctx = _build_ctx(question)
    await OffTopicStage().run(ctx)

    assert ctx.state.get("general_knowledge_mode") is not True
    assert ctx.state["domain_route"] == "teaching"


@pytest.mark.asyncio
async def test_indic_unrelated_query_routes_to_general_answering(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(mod, "off_topic_domain_boundary_enabled", lambda: False)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", False)

    # Worldly question in Hindi: "What is the capital of France?" (no spiritual cue)
    ctx = _build_ctx("फ्रांस की राजधानी क्या है?")
    ctx.state["user_msg_en"] = "What is the capital of France?"
    await OffTopicStage().run(ctx)

    assert ctx.state.get("general_knowledge_mode") is True
    assert ctx.state.get("domain_route") == "general"


@pytest.mark.asyncio
async def test_hindi_share_emotion_is_not_worldly_off_topic(monkeypatch) -> None:
    """Bare "शेयर" means "share"; only the stock-market phrase is worldly."""
    import app.pipeline.stages.off_topic_stage as mod

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    ctx = _build_ctx("मैं अपना दुख शेयर करना चाहता हूँ")
    result = await OffTopicStage().run(ctx)
    assert result is None
    assert not ctx.state.get("general_knowledge_mode")
    assert ctx.route_metadata["domain_route"] == "teaching"
    assert not mod.is_off_topic("मैं अपना दुख शेयर करना चाहता हूँ")
    assert bool(mod._INDIC_WORLDLY_RE.search("आज शेयर बाज़ार कैसा है?"))


@pytest.mark.asyncio
async def test_meditation_for_peace_is_guided_practice(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    ctx = _build_ctx("Give me a meditation for peace.")
    await OffTopicStage().run(ctx)
    assert ctx.route_metadata["domain_route"] == "guided_practice"
    assert "general_knowledge_mode" not in ctx.state


@pytest.mark.asyncio
async def test_meditation_phrase_without_cue_does_not_trigger_guided_practice(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from app.config import settings

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", False)
    ctx = _build_ctx("a meditation for anxiety")
    await OffTopicStage().run(ctx)
    assert ctx.route_metadata.get("domain_route") != "guided_practice"


def test_guided_practice_re_narrowed_descriptors() -> None:
    from app.pipeline.stages.off_topic_stage import _GUIDED_PRACTICE_RE

    assert not _GUIDED_PRACTICE_RE.search("give me the history of meditation")
    assert not _GUIDED_PRACTICE_RE.search("give me some info on meditation")
    assert bool(_GUIDED_PRACTICE_RE.search("give me a meditation"))
    assert bool(_GUIDED_PRACTICE_RE.search("give me a short meditation"))
    assert bool(_GUIDED_PRACTICE_RE.search("give me a 10-minute meditation"))
    assert bool(_GUIDED_PRACTICE_RE.search("give me a calming practice"))


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
async def test_cache_check_bypasses_general_questions_even_when_legacy_flag_off(
    monkeypatch,
) -> None:
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
async def test_doctrine_cache_never_serves_general_question_even_when_legacy_flag_off(
    monkeypatch,
) -> None:
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
    assert _first_person_claims({"question": "What does Sri Krishnaji teach about stillness?"})


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


def test_teacher_identity_question_stays_in_teaching_domain() -> None:
    """A bare configured teacher name is a teaching-domain request.

    The `krishnaji|preethaji` alternation was dropped from `_ON_TOPIC_RE` when
    teacher identity moved to the registry, which sent "Who is Sri Krishnaji?"
    to the neutral general-assistant lane.
    """
    from app.pipeline.stages.off_topic_stage import (
        is_off_topic,
        is_spiritual_domain_query,
    )

    for question in ("Who is Sri Krishnaji?", "Who is Sri Preethaji?"):
        assert is_spiritual_domain_query(question) is True
        assert is_off_topic(question) is False

    # The general-task gate still wins: a teacher's name does not turn an
    # explicit worldly action request into a teaching request.
    assert is_spiritual_domain_query("Write a report about Sri Preethaji's event.") is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        # English personal questions containing temporal words: these must not
        # receive the canned "live information unavailable" reply.
        "I feel hopeless today",
        "I have been crying all day today",
        "My anxiety is worse right now",
        "I am sad currently and cannot sleep",
        "What is happening in my life today?",
        "Why is my marriage falling apart this week?",
        # Hindi personal question (already translated by the time the stage
        # classifies, so the English cue is what would have matched).
        "मैं आज बहुत दुखी हूँ",
        "आज मेरा मन बहुत भारी है",
    ],
)
async def test_personal_question_with_temporal_word_is_not_live_info(monkeypatch, question) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from services.voice.register import LIVE_INFO_UNAVAILABLE

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    result = await OffTopicStage().run(_build_ctx(question))
    assert result is None or result.final_answer != LIVE_INFO_UNAVAILABLE


@pytest.mark.asyncio
async def test_hindi_personal_question_translated_to_english_is_not_live_info(monkeypatch) -> None:
    """The stage classifies the English translation; a translated time word is still personal."""
    import app.pipeline.stages.off_topic_stage as mod
    from services.voice.register import LIVE_INFO_UNAVAILABLE

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    ctx = _build_ctx("मैं आज बहुत दुखी हूँ")
    ctx.state["user_msg_en"] = "I am very sad today"
    result = await OffTopicStage().run(ctx)
    assert result is None or result.final_answer != LIVE_INFO_UNAVAILABLE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "What's happening today?",
        "What is the latest news?",
        "What's the weather right now?",
        "Which stocks are rising today?",
    ],
)
async def test_genuine_live_info_question_still_returns_canned_reply(monkeypatch, question) -> None:
    import app.pipeline.stages.off_topic_stage as mod
    from services.voice.register import LIVE_INFO_UNAVAILABLE

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    result = await OffTopicStage().run(_build_ctx(question))
    assert result is not None
    assert result.final_answer == LIVE_INFO_UNAVAILABLE
