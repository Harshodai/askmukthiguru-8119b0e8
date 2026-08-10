"""P1-BE-3 — CacheUpdateStage must never cache known-unfaithful answers.

Regression: a hallucinated (low-faithfulness) answer was cached and served to
every seeker with the same query. The faithfulness verdict lives on
``ctx.graph_result`` (the LangGraph generation node's output — see
rag/nodes/generation.py "verification" lane), NOT on ``ctx.state``, which
GraphStage populates only with pre-graph inputs.

Gates (mirror of P1-AI-2 acceptance semantics in generation.py):
  * is_faithful is False         -> never cache
  * faithfulness_score < floor   -> never cache (CoVe compulsory threshold)
  * is_faithful is None AND citations_verified is False -> never cache
    (verification was skipped with no grounding evidence)
  * is_faithful is None AND citations_verified is True  -> cache allowed
    (fast tier legitimately skips the verdict; citations are grounded)
  * is_faithful is True          -> cache allowed
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages import CacheUpdateStage
from app.pipeline.stages.context import PipelineContext


def _container() -> MagicMock:
    container = MagicMock()
    # The stage writes through asyncio.to_thread(...) — plain callables, NOT
    # AsyncMock (a coroutine returned into the worker thread is never awaited).
    container.exact_cache = MagicMock()
    container.exact_cache.put = MagicMock()
    container.semantic_cache = MagicMock()
    container.semantic_cache.is_available = True
    container.semantic_cache.put = MagicMock()
    container.translation = AsyncMock()
    return container


def _coordinator(container) -> PipelineCoordinator:
    coord = PipelineCoordinator(container)

    class _DirectCoalescer:
        async def get_or_run(self, key, callback):
            return await callback()

    coord.coalescer = _DirectCoalescer()
    return coord


def _ctx(coordinator, *, graph_result: dict | None = None) -> PipelineContext:
    return PipelineContext(
        container=coordinator.container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg="what is karma",
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-1",
        user={"id": "user-1"},
        is_benchmark=False,
        stream_queue=None,
        trace_id="trace-1",
        start_time=0.0,
        cache_key="ck:en:what is karma",
        query_for_embedding="what is karma",
        is_indic=False,
        user_id="user-1",
        stable_session_id="sess-1",
        chat_body_messages=[],
        state={"user_msg_en": "what is karma", "chat_history_en": [], "memory_context": ""},
        final_answer="Karma is the law of cause and effect.",
        intent="QUERY",
        med_step=0,
        citations=[{"id": "c1", "source_url": "u1", "score": 0.9}],
        graph_result=graph_result,
    )


def _run(ctx):
    settings.hybrid_search_enabled = False
    try:
        return ctx.coordinator.container, ctx
    finally:
        settings.hybrid_search_enabled = True


def _assert_not_cached(container):
    container.exact_cache.put.assert_not_called()
    container.semantic_cache.put.assert_not_called()


def _assert_cached(container):
    container.exact_cache.put.assert_called_once()
    container.semantic_cache.put.assert_called_once()


@pytest.mark.asyncio
async def test_unfaithful_answer_not_cached():
    """is_faithful=False must skip the write on every cache tier."""
    container = _container()
    coord = _coordinator(container)
    _, ctx = _run(_ctx(coord, graph_result={"is_faithful": False, "faithfulness_score": 0.2}))

    result = await CacheUpdateStage().run(ctx)

    assert result is None
    _assert_not_cached(container)


@pytest.mark.asyncio
async def test_low_faithfulness_score_not_cached():
    """Score below the CoVe compulsory threshold must skip the write."""
    container = _container()
    coord = _coordinator(container)
    _, ctx = _run(_ctx(coord, graph_result={"is_faithful": True, "faithfulness_score": 0.3}))

    await CacheUpdateStage().run(ctx)

    _assert_not_cached(container)


@pytest.mark.asyncio
async def test_unverified_without_citations_not_cached():
    """is_faithful=None (verifier skipped) with citations_verified=False is
    not cacheable — no grounding evidence to replay."""
    container = _container()
    coord = _coordinator(container)
    _, ctx = _run(
        _ctx(coord, graph_result={"is_faithful": None, "citations_verified": False})
    )

    await CacheUpdateStage().run(ctx)

    _assert_not_cached(container)


@pytest.mark.asyncio
async def test_unverified_but_citations_verified_cached():
    """is_faithful=None with citations_verified=True (fast tier, legitimately
    skipped verdict) remains cacheable — mirrors P1-AI-2 acceptance."""
    container = _container()
    coord = _coordinator(container)
    _, ctx = _run(
        _ctx(coord, graph_result={"is_faithful": None, "citations_verified": True})
    )

    await CacheUpdateStage().run(ctx)

    _assert_cached(container)


@pytest.mark.asyncio
async def test_faithful_answer_cached():
    """is_faithful=True with a passing score must still be cached."""
    container = _container()
    coord = _coordinator(container)
    _, ctx = _run(
        _ctx(coord, graph_result={"is_faithful": True, "faithfulness_score": 0.95})
    )

    await CacheUpdateStage().run(ctx)

    _assert_cached(container)


@pytest.mark.asyncio
async def test_missing_verdict_defaults_to_cache_allowed():
    """No verdict at all in graph_result (non-RAG / no-context / fallback
    paths that never run the verification lane) must not regress legacy
    behavior — those answers were cacheable before and stay cacheable.
    Mirrors test_cache_personalization_leak.py's contract."""
    container = _container()
    coord = _coordinator(container)
    _, ctx = _run(_ctx(coord, graph_result={"intent": "QUERY"}))

    await CacheUpdateStage().run(ctx)

    _assert_cached(container)


if __name__ == "__main__":
    # ponytail: one runnable self-check — run pytest on this module.
    raise SystemExit(pytest.main([__file__, "-v"]))
