"""Regression guard: a memory-personalized answer must never enter the shared cache.

``_build_context_aware_cache_key`` keys on (language, message) only — no user_id,
no tenant_id — and hot/exact/semantic caches are all process- or Redis-wide. So an
answer that ``context_engineer`` personalized with ``memory_context`` (the user's
core facts and recent conversation) would otherwise be replayed verbatim to any
other user asking the same question.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages import CacheUpdateStage
from app.pipeline.stages.context import PipelineContext
from services.hot_cache import hot_cache

PERSONAL_FACT = "USER PROFILE & CORE FACTS:\n- Seeker is recovering from alcoholism"
QUESTION = "how do i find peace"
CACHE_KEY = f"en:{QUESTION}"
ANSWER = "Given your recovery journey, the Beautiful State begins with breath. [Source: Peace]"


def _ctx(memory_context: str) -> PipelineContext:
    container = MagicMock()
    container.exact_cache = MagicMock()
    container.semantic_cache = MagicMock()
    container.semantic_cache.is_available = False
    coordinator = PipelineCoordinator(container)
    coordinator._embed_query = AsyncMock(return_value=None)

    return PipelineContext(
        container=container,
        coordinator=coordinator,
        request=MagicMock(),
        user_msg=QUESTION,
        preferred_lang="en",
        cache_key=CACHE_KEY,
        query_for_embedding=QUESTION,
        user_id="user-alice",
        final_answer=ANSWER,
        intent="QUERY",
        citations=["Peace"],
        state={"memory_context": memory_context},
    )


@pytest.fixture(autouse=True)
def _clear_hot_cache():
    hot_cache.clear()
    yield
    hot_cache.clear()


@pytest.mark.asyncio
async def test_personalized_answer_is_not_written_to_shared_cache():
    """Alice's memory-conditioned answer must not be retrievable by Bob."""
    await CacheUpdateStage().run(_ctx(memory_context=PERSONAL_FACT))

    assert hot_cache.get(CACHE_KEY) is None, (
        "cross-user leak: an answer personalized with Alice's memory_context was "
        "written to the shared hot cache under a user-agnostic key"
    )


@pytest.mark.asyncio
async def test_unpersonalized_answer_is_still_cached():
    """No memory_context → generic answer → shared cache still works (no hit-rate regression)."""
    await CacheUpdateStage().run(_ctx(memory_context=""))

    cached = hot_cache.get(CACHE_KEY)
    assert cached is not None, "generic answers must remain cacheable"
    assert cached[0] == ANSWER
