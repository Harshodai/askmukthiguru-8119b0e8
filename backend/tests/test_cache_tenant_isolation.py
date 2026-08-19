"""CRIT-4 — cross-tenant / cross-user cache isolation regression guards.

Three layers of the fix, each tested:

1. Read-side ``memory_context`` guard in ``CacheCheckStage``: a query personalized
   with the current user's memory must never be served a generic cached answer,
   even when that generic answer is present in the shared cache (written by a
   different, non-personalized user).
2. Tenant prefix in ``_build_context_aware_cache_key``: keys for the same
   ``(language, message)`` differ across tenants, so one tenant's generic answers
   are never replayed to another tenant.
3. Same-tenant sharing still works: a non-personalized answer cached by one user
   is served to another user in the same tenant (no hit-rate regression).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages import CacheCheckStage, CacheUpdateStage
from app.pipeline.stages.context import PipelineContext
from services.hot_cache import hot_cache
from services.tenant_context import TenantContext

QUESTION = "how do i find peace"
CACHE_KEY = f"en:{QUESTION}"
ANSWER = "Peace begins with the stilling of the breath. [Source: Peace]"


def _make_coordinator() -> PipelineCoordinator:
    container = MagicMock()
    container.exact_cache = MagicMock()
    container.semantic_cache = MagicMock()
    container.semantic_cache.is_available = False
    coordinator = PipelineCoordinator(container)
    coordinator._embed_query = AsyncMock(return_value=None)
    return coordinator


def _ctx(memory_context: str, user_id: str = "user-alice") -> PipelineContext:
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
        user_id=user_id,
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


@pytest.fixture(autouse=True)
def _reset_tenant():
    yield
    TenantContext.set("default")


@pytest.mark.asyncio
async def test_personalized_answer_not_served_from_generic_cache():
    """User A (no memory) writes a generic answer to the shared cache; user B
    (with memory_context) asking the same question must get a cache MISS, not
    A's generic cached answer."""
    await CacheUpdateStage().run(_ctx(memory_context=""))

    assert hot_cache.get(CACHE_KEY) is not None, (
        "precondition: generic answer must be in the hot cache"
    )

    personalized_ctx = _ctx(
        memory_context="USER PROFILE & CORE FACTS:\n- Seeker is recovering from alcoholism"
    )
    result = await CacheCheckStage().run(personalized_ctx)

    assert result is None, (
        "personalized query was served a generic cached answer written by another user"
    )


@pytest.mark.asyncio
async def test_tenant_prefix_isolates_caches():
    """The same query under different tenants must produce different cache keys,
    both carrying the tenant prefix."""
    container = MagicMock()
    coordinator = PipelineCoordinator(container)

    TenantContext.set("tenant-x", email="x@example.com", user_id="user-x")
    key_x = coordinator._build_context_aware_cache_key(QUESTION, "en")

    TenantContext.set("tenant-y", email="y@example.com", user_id="user-y")
    key_y = coordinator._build_context_aware_cache_key(QUESTION, "en")

    assert "tenant:tenant-x:" in key_x
    assert "tenant:tenant-y:" in key_y
    assert key_x != key_y, "cache keys must differ across tenants for the same query"
    assert key_x.endswith(CACHE_KEY), (
        "tenant prefix must wrap, not replace, the (language, message) key"
    )


@pytest.mark.asyncio
async def test_non_personalized_answer_cached_across_users_in_same_tenant():
    """User A (no memory) writes a generic answer; user B in the same tenant,
    also with no memory, asking the same question gets a cache HIT."""
    await CacheUpdateStage().run(_ctx(memory_context=""))

    result = await CacheCheckStage().run(_ctx(memory_context=""))

    assert result is not None, "same-tenant generic answers must still hit the shared cache"
    assert result.cache_hit is True
    assert result.final_answer == ANSWER


@pytest.mark.asyncio
async def test_personalized_answer_purges_stale_shared_entry():
    """User A (no memory) writes a generic answer to the shared cache; user B
    (with memory) then gets a personalized answer for the same query. The stale
    shared entry must be purged so a later lookup can never serve A's generic
    answer in place of B's personalization."""
    # User A: generic write
    await CacheUpdateStage().run(_ctx(memory_context="", user_id="user-alice"))

    assert hot_cache.get(CACHE_KEY) is not None, (
        "precondition: generic answer must be in the hot cache"
    )

    # User B: personalized write — must invalidate A's stale shared entry
    await CacheUpdateStage().run(
        _ctx(
            memory_context="USER PROFILE & CORE FACTS:\n- Seeker is recovering from alcoholism",
            user_id="user-bob",
        )
    )

    assert hot_cache.get(CACHE_KEY) is None, (
        "stale shared entry survived: a memory-personalized answer must purge the "
        "previously cached generic answer for the same key"
    )


@pytest.mark.asyncio
async def test_response_preferences_scope_shared_cache_keys():
    container = MagicMock()
    coordinator = PipelineCoordinator(container)
    TenantContext.set("tenant-x", email="x@example.com", user_id="user-x")
    base = {"mode": "balanced_guidance", "include_practice": True}
    concise = {"mode": "concise", "include_practice": False}
    key_a = coordinator._build_context_aware_cache_key(QUESTION, "en", response_preferences=base)
    key_b = coordinator._build_context_aware_cache_key(QUESTION, "en", response_preferences=concise)
    assert key_a != key_b
    assert ":pref:" in key_a
    assert ":pref:" in key_b
