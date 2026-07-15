"""Boundary tests for the CacheManager facade (Candidate 4: Cache Layer Unification).

Boundary-level only: these tests exercise the facade's tier routing, fallback
on missing adapter, invalidation, and stats aggregation. They do NOT test
individual adapter internals. They use the real InMemoryCacheAdapter for the
exact tier (no Redis needed) and a lightweight mock for the semantic tier.
"""

from __future__ import annotations

import asyncio

import pytest

from services.cache.factory import CacheFactory
from services.cache.manager import CacheManager


class _MockSemanticAdapter:
    """Minimal stand-in for SemanticCacheAdapter — returns canned value.

    Mirrors the real adapter API surface the facade calls:
    get(query) -> dict | None, put(...), invalidate_all(), stats (property).
    """

    def __init__(self, canned: dict | None = None) -> None:
        self._canned = canned
        self._store: dict[str, dict] = {}
        self._puts = 0
        self._hits = 0
        self._misses = 0

    def get(self, query: str) -> dict | None:
        if self._canned is not None:
            self._hits += 1
            return self._canned
        self._misses += 1
        return self._store.get(query)

    def put(
        self,
        query: str,
        response: str,
        intent: str,
        citations: list,
        meditation_step: int = 0,
    ) -> None:
        self._puts += 1
        self._store[query] = {
            "response": response,
            "intent": intent,
            "citations": citations,
            "meditation_step": meditation_step,
        }

    def invalidate_all(self) -> None:
        self._store.clear()

    @property
    def stats(self) -> dict:
        return {
            "size": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "puts": self._puts,
        }

    def health_check(self) -> bool:
        return True


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _ExactOnlyFactory:
    """Factory whose semantic cache is unavailable (returns None)."""

    def create_exact_cache(self, override=None):
        from services.cache.memory_adapter import InMemoryCacheAdapter

        return InMemoryCacheAdapter()

    def create_semantic_cache(self, embedding_service=None, override=None):
        return None


class _SemanticFactory:
    """Factory whose semantic cache is a mock returning a canned value."""

    def __init__(self, canned: dict) -> None:
        self._canned = canned
        self.semantic_adapter = _MockSemanticAdapter(canned=canned)

    def create_exact_cache(self, override=None):
        from services.cache.memory_adapter import InMemoryCacheAdapter

        return InMemoryCacheAdapter()

    def create_semantic_cache(self, embedding_service=None, override=None):
        return self.semantic_adapter


class TestCacheManagerBoundary:
    def test_get_set_exact_tier(self) -> None:
        mgr = CacheManager(_ExactOnlyFactory())
        value = {"response": "v", "intent": "QUERY", "citations": []}
        _run(mgr.set("k", value, ttl=60, tier="exact"))
        hit = _run(mgr.get("k", tier="exact"))
        assert hit is not None
        assert hit["response"] == "v"

    def test_get_set_semantic_tier(self) -> None:
        canned = {"response": "sem-v", "intent": "QUERY", "citations": []}
        factory = _SemanticFactory(canned=canned)
        mgr = CacheManager(factory)
        value = {"response": "ignored", "intent": "QUERY", "citations": []}
        _run(mgr.set("k", value, ttl=60, tier="semantic"))
        # Mock semantic adapter returns the canned value on get.
        hit = _run(mgr.get("k", tier="semantic"))
        assert hit is not None
        assert hit["response"] == "sem-v"

    def test_get_set_hot_tier(self) -> None:
        # Hot tier uses the in-process singleton; clear it first to isolate.
        from services.cache.hot_cache_adapter import hot_cache

        hot_cache.clear()
        mgr = CacheManager(_ExactOnlyFactory())
        value = {"response": "hot-v", "citations": ["c1"], "intent": "QUERY"}
        _run(mgr.set("k", value, ttl=60, tier="hot"))
        hit = _run(mgr.get("k", tier="hot"))
        assert hit is not None
        response, citations, intent = hit
        assert response == "hot-v"
        assert citations == ["c1"]
        assert intent == "QUERY"
        hot_cache.clear()

    def test_fallback_when_tier_unavailable(self) -> None:
        # Semantic adapter disabled (factory returns None). get must not crash.
        mgr = CacheManager(_ExactOnlyFactory())
        assert _run(mgr.get("k", tier="semantic")) is None
        # set on an unavailable tier must be a no-op (no raise).
        _run(mgr.set("k", {"response": "v"}, ttl=60, tier="semantic"))

    def test_invalidate(self) -> None:
        from services.cache.hot_cache_adapter import hot_cache

        hot_cache.clear()
        mgr = CacheManager(_ExactOnlyFactory())
        value = {"response": "v", "intent": "QUERY", "citations": []}
        _run(mgr.set("k", value, ttl=60, tier="exact"))
        assert _run(mgr.get("k", tier="exact")) is not None
        # Invalidate with a pattern; exact tier calls invalidate_all().
        _run(mgr.invalidate("k*"))
        assert _run(mgr.get("k", tier="exact")) is None
        hot_cache.clear()

    def test_stats(self) -> None:
        from services.cache.hot_cache_adapter import hot_cache

        hot_cache.clear()
        mgr = CacheManager(_ExactOnlyFactory())
        stats = _run(mgr.stats())
        assert isinstance(stats, dict)
        # All supported tiers must be represented in the stats dict.
        for tier in ("exact", "semantic", "hot", "llm"):
            assert tier in stats, f"stats missing tier {tier!r}"
        # Exact tier is available and reports a dict.
        assert isinstance(stats["exact"], dict)
        # Semantic tier is unavailable -> facade reports available: False.
        assert stats["semantic"] == {"available": False}
        hot_cache.clear()