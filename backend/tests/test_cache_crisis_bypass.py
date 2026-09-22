"""CacheCheckStage must never serve a cache hit for a crisis-adjacent message.

DistressStage runs AFTER CacheCheckStage in the pipeline order
(kill_switch -> cache_check -> ... -> distress -> ... -> graph). Without a
crisis-keyword bypass at the cache-check stage, a message expressing acute
distress that happens to land within cache-key/semantic-similarity range of a
previously-cached benign doctrinal answer would be served straight from the
cache, and the request would never reach DistressStage at all.

Regression target: CacheCheckStage.run() must return None (forcing a cache
miss and letting the request continue to DistressStage) whenever
has_crisis_keywords() matches ctx.user_msg, even when a matching cache entry
exists for the same cache_key.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage
from app.pipeline.stages.cache_stage import CacheCheckStage, CacheUpdateStage
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.stage_runner import StageRunner
from services.hot_cache import hot_cache


def _container() -> MagicMock:
    container = MagicMock()
    container.semantic_cache = MagicMock()
    container.semantic_cache.is_available = False
    return container


def _coordinator(container) -> PipelineCoordinator:
    return PipelineCoordinator(container)


def _ctx(coordinator, *, user_msg: str, cache_key: str) -> PipelineContext:
    return PipelineContext(
        container=coordinator.container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg=user_msg,
        preferred_lang="en",
        cache_key=cache_key,
        query_for_embedding=user_msg,
        is_indic=False,
    )


@pytest.mark.asyncio
async def test_crisis_message_bypasses_hot_cache_hit():
    """A cached benign entry must NOT be served for a crisis-adjacent message
    sharing its cache key — the request must fall through to DistressStage."""
    cache_key = "en:test-crisis-bypass-key"
    hot_cache.put(cache_key, "Here is a teaching on inner peace.", [{"id": "c1"}])
    try:
        container = _container()
        coord = _coordinator(container)
        ctx = _ctx(
            coord,
            user_msg="I want to end my life, nothing matters anymore",
            cache_key=cache_key,
        )

        result = await CacheCheckStage().run(ctx)

        assert result is None, (
            "crisis-keyword message must bypass the cache and reach DistressStage"
        )
    finally:
        hot_cache.invalidate(cache_key)


@pytest.mark.asyncio
async def test_benign_message_with_same_cache_key_still_hits_cache():
    """Control: without a crisis keyword, the same cache_key IS served from
    the hot cache — isolates the bypass to the crisis-keyword condition."""
    cache_key = "en:test-crisis-bypass-key-control"
    hot_cache.put(cache_key, "Here is a teaching on inner peace.", [{"id": "c1"}])
    try:
        container = _container()
        coord = _coordinator(container)
        ctx = _ctx(coord, user_msg="what is inner peace", cache_key=cache_key)

        result = await CacheCheckStage().run(ctx)

        assert result is not None, "benign message should still hit the hot cache"
        assert result.cache_hit is True
    finally:
        hot_cache.invalidate(cache_key)


def _update_container() -> MagicMock:
    """Mirror of test_cache_stage_faithfulness.py's container fixture."""
    container = MagicMock()
    container.exact_cache = MagicMock()
    container.exact_cache.put = MagicMock()
    container.semantic_cache = MagicMock()
    container.semantic_cache.is_available = True
    container.semantic_cache.put = MagicMock()
    container.translation = AsyncMock()
    return container


def _update_ctx(coordinator, *, intent: str) -> PipelineContext:
    return PipelineContext(
        container=coordinator.container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg="I feel so alone and hopeless lately",
        preferred_lang="en",
        cache_key="en:distress-write-test",
        query_for_embedding="I feel so alone and hopeless lately",
        is_indic=False,
        final_answer="I hear how much pain you're carrying right now...",
        intent=intent,
        citations=[{"id": "c1", "source_url": "u1", "score": 0.9}],
        graph_result={"intent": intent, "citations_verified": True},
    )


@pytest.mark.asyncio
async def test_distress_intent_answer_not_cached_on_write():
    """CacheUpdateStage's existing intent skip list already excludes
    'DISTRESS' — a compassionate answer generated for a non-preempted
    (MODERATE/MILD) distress query, which keeps intent='DISTRESS' through
    generation, must never be written to the shared cache."""
    container = _update_container()
    coord = _coordinator(container)
    ctx = _update_ctx(coord, intent="DISTRESS")

    result = await CacheUpdateStage().run(ctx)

    assert result is None
    container.exact_cache.put.assert_not_called()
    container.semantic_cache.put.assert_not_called()


@pytest.mark.asyncio
async def test_non_distress_answer_still_cached_on_write():
    """Control: an ordinary QUERY-intent answer with the same shape IS
    written — isolates the skip to the DISTRESS intent, not the fixture."""
    container = _update_container()
    coord = _coordinator(container)
    ctx = _update_ctx(coord, intent="QUERY")

    await CacheUpdateStage().run(ctx)

    container.exact_cache.put.assert_called_once()


@pytest.mark.asyncio
async def test_crisis_preemption_short_circuits_before_cache_update_runs():
    """Structural confirmation: StageRunner returns on the FIRST non-None
    stage result, so when a crisis-preemption stage (standing in for
    DistressStage's _crisis_preemption_result) returns a PipelineResult,
    CacheUpdateStage never executes at all for that request — the write
    path is unreachable, not merely intent-filtered."""

    class _FakeCrisisPreemptionStage(Stage):
        name = "fake_crisis_preemption"

        async def run(self, ctx):
            return PipelineResult(final_answer="crisis resources", intent="DISTRESS")

    container = _update_container()
    coord = _coordinator(container)
    ctx = _update_ctx(coord, intent="DISTRESS")

    result = await StageRunner.run([_FakeCrisisPreemptionStage(), CacheUpdateStage()], ctx)

    assert result is not None
    assert result.final_answer == "crisis resources"
    container.exact_cache.put.assert_not_called()
    container.semantic_cache.put.assert_not_called()


if __name__ == "__main__":
    # ponytail: one runnable self-check — run pytest on this module.
    raise SystemExit(pytest.main([__file__, "-v"]))
