"""Unit tests for the Stage ABC pipeline (Phase 0 — Stage ABC Refactor).

Per-stage isolation: each stage is run against a PipelineContext with a mocked
ServiceContainer. Asserts:
  * CacheCheckStage short-circuits with a PipelineResult on a cache hit.
  * CacheCheckStage passes through (returns None) on a cache miss.
  * Non-short-circuit stages (Distress, Memory, Translation, OutputGuardrail,
    CacheUpdate, RequestState) return None and do not short-circuit.
  * Full StageRunner chain assembles a PipelineResult end-to-end with a
    mocked graph (regression guard for orchestrator.py / stream_orchestrator.py).

Reuses conftest.py fixtures (sys.path / env setup).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.result import PipelineResult
from app.pipeline.stages import (
    CacheCheckStage,
    CacheUpdateStage,
    DistressStage,
    GraphStage,
    InputGuardrailStage,
    MemoryStage,
    OutputGuardrailStage,
    RequestStateStage,
    StageRunner,
    TranslationStage,
    build_default_pipeline,
)
from app.pipeline.stages.context import PipelineContext


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _mock_container(*, cache_hit: dict | None = None, graph_result: dict | None = None) -> MagicMock:
    """Build a MagicMock ServiceContainer sufficient for the stage chain.

    cache_hit: if provided, exact_cache.get returns this dict (semantic-cache shape).
    graph_result: if provided, the selected graph.ainvoke returns this dict.
    """
    container = MagicMock()

    # Guardrails (async)
    container.guardrails = AsyncMock()
    container.guardrails.check_input.return_value = {"blocked": False, "reason": None}
    container.guardrails.check_output.return_value = {"blocked": False, "reason": None}

    # Translation (async, pass-through)
    async def _translate(*, text: str, source_lang: str, target_lang: str, **kw):
        return f"translated_{text}"

    container.translation = AsyncMock()
    container.translation.translate_text = _translate

    # Caches
    container.exact_cache = MagicMock()
    container.exact_cache.get.return_value = cache_hit
    container.semantic_cache = MagicMock()
    container.semantic_cache.is_available = True
    container.semantic_cache.get.return_value = None

    # Serene mind / user profile (async, no-op)
    container.serene_mind = None
    container.user_profile = None
    container.memory_service = None

    # Graph facade — every variant returns the same mocked graph
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = graph_result or {
        "final_answer": "Beautiful State is calm awareness.",
        "meditation_step": 0,
        "citations": [{"id": "c1", "source_url": "u1", "score": 0.9}],
        "intent": "QUERY",
    }
    container.rag_graph = mock_graph
    container.standard_graph = mock_graph
    container.fast_graph = mock_graph
    container.deep_graph = mock_graph

    # Circuit breaker (closed = healthy)
    container.ollama = MagicMock()
    container.ollama._circuit = MagicMock()
    container.ollama._circuit.can_execute.return_value = True

    return container


def _build_ctx(container: MagicMock, coordinator: PipelineCoordinator, **overrides) -> PipelineContext:
    """Build a PipelineContext pre-populated the way execute() does."""
    state = {
        "user_msg_en": "what is the beautiful state",
        "chat_history_en": [],
        "memory_context": "",
        "lang_detection": None,
        "query_tier": "standard",
    }
    defaults = dict(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg="what is the beautiful state",
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-1",
        user={"id": "user-1"},
        is_benchmark=False,
        stream_queue=None,
        trace_id="trace-1",
        start_time=0.0,
        cache_key="ck:en:what is the beautiful state",
        query_for_embedding="what is the beautiful state",
        is_indic=False,
        user_id="user-1",
        stable_session_id="sess-1",
        chat_body_messages=[],
        state=state,
    )
    defaults.update(overrides)
    return PipelineContext(**defaults)


@pytest.fixture
def coordinator():
    """A PipelineCoordinator whose coalescer runs the callback directly (no Redis)."""
    container = _mock_container()

    class _DirectCoalescer:
        async def get_or_run(self, key, callback):
            return await callback()

    coord = PipelineCoordinator(container)
    coord.coalescer = _DirectCoalescer()
    return coord


# ---------------------------------------------------------------------------
# CacheCheckStage — the only short-circuit stage on cache hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_check_stage_short_circuits_on_hit(coordinator):
    """CacheCheckStage returns a PipelineResult (short-circuit) when the cache has a hit."""
    cached = {
        "response": "Cached answer.",
        "intent": "QUERY",
        "meditation_step": 0,
        "citations": [],
    }
    coordinator.container = _mock_container(cache_hit=cached)
    # hot_cache / vector cache must miss so the exact/semantic path is exercised
    import services.hot_cache as hc

    hc.hot_cache._store.clear()  # ponytail: clear in-memory hot cache to force exact path
    coordinator._vector_cache = None  # force _ensure_vector_cache to build empty

    ctx = _build_ctx(coordinator.container, coordinator)
    # Disable hybrid search so vector cache path is skipped entirely
    settings.hybrid_search_enabled = False
    try:
        result = await CacheCheckStage().run(ctx)
    finally:
        settings.hybrid_search_enabled = True

    assert result is not None, "CacheCheckStage must short-circuit on a cache hit"
    assert isinstance(result, PipelineResult)
    assert result.cache_hit is True
    assert result.final_answer == "Cached answer."
    assert result.route_decision == "semantic_cache"


@pytest.mark.asyncio
async def test_cache_check_stage_passes_through_on_miss(coordinator):
    """CacheCheckStage returns None (continue) on a cache miss."""
    coordinator.container = _mock_container(cache_hit=None)
    import services.hot_cache as hc

    hc.hot_cache._store.clear()
    coordinator._vector_cache = None

    ctx = _build_ctx(coordinator.container, coordinator)
    settings.hybrid_search_enabled = False
    try:
        result = await CacheCheckStage().run(ctx)
    finally:
        settings.hybrid_search_enabled = True

    assert result is None, "CacheCheckStage must pass through (None) on a cache miss"


# ---------------------------------------------------------------------------
# Non-short-circuit stages — must always return None
# ---------------------------------------------------------------------------


_NON_SHORT_CIRCUIT_STAGES = [
    RequestStateStage,
    InputGuardrailStage,
    DistressStage,
    GraphStage,
    TranslationStage,
    MemoryStage,
    OutputGuardrailStage,
    CacheUpdateStage,
]


@pytest.mark.parametrize("stage_cls", _NON_SHORT_CIRCUIT_STAGES, ids=lambda c: c.__name__)
@pytest.mark.asyncio
async def test_non_short_circuit_stage_returns_none(coordinator, stage_cls):
    """Each non-cache stage returns None (does not short-circuit) under normal inputs."""
    coordinator.container = _mock_container()
    # DistressStage needs the distress-keyword pre-screen to be False to skip the LLM path;
    # our user_msg has no distress keywords.
    ctx = _build_ctx(coordinator.container, coordinator)
    # RequestStateStage expects prepare_request_state to populate ctx.state — stub it
    if stage_cls is RequestStateStage:
        # Patch the reference bound in glue_stages (imported at module load).
        import app.pipeline.stages.glue_stages as glue

        async def _stub_prepare(*a, **kw):
            return {
                "user_msg_en": ctx.user_msg,
                "chat_history_en": [],
                "memory_context": "",
                "lang_detection": None,
                "query_tier": "standard",
            }

        orig = glue.prepare_request_state
        glue.prepare_request_state = _stub_prepare
        try:
            result = await stage_cls().run(ctx)
        finally:
            glue.prepare_request_state = orig
    else:
        result = await stage_cls().run(ctx)
    assert result is None, f"{stage_cls.__name__} must not short-circuit"


# ---------------------------------------------------------------------------
# StageRunner — end-to-end chain produces a PipelineResult
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage_runner_assembles_result(coordinator):
    """Full default pipeline runs and returns a PipelineResult from the terminal stage."""
    coordinator.container = _mock_container(
        graph_result={
            "final_answer": "Beautiful State is calm awareness.",
            "meditation_step": 0,
            "citations": [{"id": "c1", "source_url": "u1", "score": 0.9}],
            "intent": "QUERY",
            "is_faithful": True,
            "faithfulness_score": 0.95,
            "confidence_score": 0.95,
        }
    )
    import services.hot_cache as hc

    hc.hot_cache._store.clear()
    coordinator._vector_cache = None

    ctx = _build_ctx(coordinator.container, coordinator)
    settings.hybrid_search_enabled = False

    # Stub prepare_request_state so RequestStateStage gets a clean string state
    # (the real helper would call into the MagicMock container and yield non-strings).
    # Patch the reference bound in glue_stages (imported at module load).
    import app.pipeline.stages.glue_stages as glue

    async def _stub_prepare(container, chat_body, preferred_lang, user=None):
        return {
            "user_msg_en": ctx.user_msg,
            "chat_history_en": [],
            "memory_context": "",
            "lang_detection": None,
            "query_tier": "standard",
        }

    orig_prepare = glue.prepare_request_state
    glue.prepare_request_state = _stub_prepare
    try:
        result = await StageRunner.run(build_default_pipeline(), ctx, coordinator=coordinator)
    finally:
        settings.hybrid_search_enabled = True
        glue.prepare_request_state = orig_prepare

    assert result is not None
    assert isinstance(result, PipelineResult)
    assert result.final_answer == "Beautiful State is calm awareness."
    assert result.intent == "QUERY"
    assert result.cache_hit is False


# ---------------------------------------------------------------------------
# Self-check: pipeline builder returns all 12 stages in the expected order
# ---------------------------------------------------------------------------


def test_build_default_pipeline_order():
    stages = build_default_pipeline()
    names = [s.name for s in stages]
    assert names == [
        "cache_check",
        "circuit_breaker",
        "request_state",
        "input_guardrails",
        "casual_short_circuit",
        "distress_detection",
        "langgraph",
        "translation",
        "memory_save",
        "output_guardrails",
        "cache_update",
        "result_assembly",
    ]


if __name__ == "__main__":
    # ponytail: one runnable self-check — run pytest on this module.
    raise SystemExit(pytest.main([__file__, "-v"]))