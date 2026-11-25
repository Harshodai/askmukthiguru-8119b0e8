"""Unit tests for cache read/write guards against first-person abstains and unverified clips."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.pipeline.stages.cache_stage import CacheCheckStage, CacheUpdateStage
from app.pipeline.stages.context import PipelineContext


def _ctx(
    *,
    route_decision: str = "first_person_abstain",
    cache_entry: dict | None = None,
) -> PipelineContext:
    container = MagicMock()
    container.guardrails.check_output = AsyncMock(
        return_value={"blocked": False, "reason": "", "moderated_response": ""}
    )
    container.hot_cache = None
    container.vector_cache = None
    container.exact_cache = MagicMock()
    container.exact_cache.get = MagicMock(return_value=None)
    container.exact_cache.set = MagicMock()
    container.semantic_cache = MagicMock()
    container.semantic_cache.is_available = True
    container.semantic_cache.get = MagicMock(return_value=cache_entry)
    container.semantic_cache.put = MagicMock()
    container.embedding = MagicMock()
    container.embedding.encode_single = MagicMock(return_value=[0.1] * 8)
    coordinator = MagicMock()
    coordinator._check_vector_cache = AsyncMock(return_value=None)

    ctx = PipelineContext(
        container=container,
        coordinator=coordinator,
        request=SimpleNamespace(),
        user_msg="What is consciousness?",
        preferred_lang="en",
        is_indic=False,
        trace_id="test-cache-guard",
        start_time=0.0,
        state={"user_msg_en": "What is consciousness?"},
    )
    ctx.route_decision = route_decision
    ctx.final_answer = "No verified direct clip found."
    return ctx


@pytest.mark.asyncio
async def test_cache_update_skips_writing_first_person_abstain():
    ctx = _ctx(route_decision="first_person_abstain")
    ctx.intent = "TEACHING"
    ctx.verification = {"passed": True}

    await CacheUpdateStage().run(ctx)

    ctx.container.exact_cache.set.assert_not_called()
    ctx.container.semantic_cache.put.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cached_payload",
    [
        {
            "response": "Abstained cached text",
            "intent": "TEACHING",
            "grounding_state": "abstained",
            "route_metadata": {"decision": "first_person_abstain"},
        },
        {
            "response": "Unverified speaker quote",
            "intent": "TEACHING",
            "citations": [{"speaker_verified": False, "video_id": "abc"}],
        },
    ],
)
async def test_cache_check_discards_abstained_and_unverified_semantic_hits(cached_payload):
    ctx = _ctx(cache_entry=cached_payload)
    ctx.route_decision = ""

    res = await CacheCheckStage().run(ctx)

    assert res is None
    assert not getattr(ctx, "cache_hit", False)
