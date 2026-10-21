"""Regression coverage for user-scoped exact-cache behavior in memory mode."""

from services.cache.memory_adapter import InMemoryCacheAdapter


def test_memory_cache_isolates_users_and_privacy_invalidation_fails_safe(monkeypatch):
    from services.tenant_context import TenantContext

    TenantContext.set("default")
    try:
        cache = InMemoryCacheAdapter()
        query = "what about my goals"
        cache.put(
            query=query,
            response="Alice's goals",
            intent="FACTUAL",
            citations=[],
            user_id="user-alice",
        )
        cache.put(
            query=query,
            response="Bob's goals",
            intent="FACTUAL",
            citations=[],
            user_id="user-bob",
        )

        assert cache.get(query, user_id="user-alice")["response"] == "Alice's goals"
        assert cache.get(query, user_id="user-bob")["response"] == "Bob's goals"
        assert cache.get(query) is None

        # The in-process cache cannot prove legacy, unindexed keys were not
        # personalized, so privacy invalidation deliberately clears all entries.
        assert cache.invalidate_user("user-alice") == 2
        assert cache.get(query, user_id="user-alice") is None
        assert cache.get(query, user_id="user-bob") is None
    finally:
        TenantContext.reset()


def test_memory_cache_privacy_invalidation_clears_legacy_keys_across_tenants():
    from services.tenant_context import TenantContext

    cache = InMemoryCacheAdapter()
    query = "what do you remember about me"
    with TenantContext.scope("tenant-a"):
        cache.put(query, "tenant A", "FACTUAL", [], user_id="user-1")
    with TenantContext.scope("tenant-b"):
        cache.put(query, "tenant B", "FACTUAL", [], user_id="user-1")

    with TenantContext.scope("tenant-a"):
        assert cache.get(query, user_id="user-1")["response"] == "tenant A"
        assert cache.invalidate_user("user-1") == 2
        assert cache.get(query, user_id="user-1") is None
    with TenantContext.scope("tenant-b"):
        assert cache.get(query, user_id="user-1") is None

def test_memory_cache_isolates_shared_queries_across_tenants():
    from services.tenant_context import TenantContext

    cache = InMemoryCacheAdapter()
    query = "what is surrender?"
    with TenantContext.scope("tenant-a"):
        cache.put(query, "answer from tenant A", "FACTUAL", [])
        assert cache.get(query)["response"] == "answer from tenant A"
    with TenantContext.scope("tenant-b"):
        assert cache.get(query) is None
        cache.put(query, "answer from tenant B", "FACTUAL", [])
        assert cache.get(query)["response"] == "answer from tenant B"
    with TenantContext.scope("tenant-a"):
        assert cache.get(query)["response"] == "answer from tenant A"

def test_redis_privacy_invalidation_removes_unindexed_legacy_keys_only_for_tenant():
    import fnmatch

    from services.cache.redis_adapter import RedisCacheAdapter
    from services.tenant_context import TenantContext

    class Pipeline:
        def __init__(self, redis):
            self.redis = redis
            self.pending = []

        def delete(self, key):
            self.pending.append(key)
            return self

        def execute(self):
            for key in self.pending:
                self.redis.keys.discard(key)
            self.pending.clear()
            return []

    class FakeRedis:
        def __init__(self):
            self.keys = {
                "mukthiguru:cache:tenant-a:legacy-shared-key",
                "mukthiguru:cache:tenant-a:alice-personal-key",
                # Pre-tenant cache key from rolling deployments.
                "mukthiguru:cache:old-query-only-hash",
                "mukthiguru:user_cache_index:tenant-a:alice-index",
                "mukthiguru:user_cache_index:tenant-a:bob-index",
                "mukthiguru:cache:tenant-b:other-tenant-key",
                "mukthiguru:user_cache_index:tenant-b:other-tenant-index",
                "mukthiguru:session:tenant-a:preserve-this-namespace",
            }

        def pipeline(self):
            return Pipeline(self)

        def scan_iter(self, match, count=500):
            return [key for key in list(self.keys) if fnmatch.fnmatch(key, match)]

    adapter = RedisCacheAdapter.__new__(RedisCacheAdapter)
    fake = FakeRedis()
    adapter._redis = fake
    with TenantContext.scope("tenant-a"):
        adapter.invalidate_user("alice")
    assert "mukthiguru:cache:tenant-a:legacy-shared-key" not in fake.keys
    assert "mukthiguru:cache:tenant-a:alice-personal-key" not in fake.keys
    # Legacy keys cannot be attributed to a tenant, so privacy invalidation
    # must remove them regardless of the currently selected tenant.
    assert "mukthiguru:cache:old-query-only-hash" not in fake.keys
    assert not any(key.startswith("mukthiguru:user_cache_index:tenant-a:") for key in fake.keys)
    assert "mukthiguru:cache:tenant-b:other-tenant-key" in fake.keys
    assert "mukthiguru:user_cache_index:tenant-b:other-tenant-index" in fake.keys
    assert "mukthiguru:session:tenant-a:preserve-this-namespace" in fake.keys
