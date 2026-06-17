"""Tests for the in-memory HotCache service.

Covers:
- Basic put/get operations
- TTL expiry
- Eviction under max_size
- Stats reporting
"""

from __future__ import annotations

import asyncio
import time

import pytest

from services.hot_cache import HotCache


class TestHotCache:
    def test_basic_put_get(self) -> None:
        cache = HotCache(default_ttl_s=300.0, max_size=10)
        cache.put("What is the Beautiful State?", "The Beautiful State is...", [{"id": "1"}])
        result = cache.get("What is the Beautiful State?")
        assert result is not None
        assert result[0] == "The Beautiful State is..."
        assert result[1] == [{"id": "1"}]

    def test_case_insensitive_lookup(self) -> None:
        cache = HotCache(default_ttl_s=300.0, max_size=10)
        cache.put("What Is The Beautiful State?", "Answer...", [])
        result = cache.get("what is the beautiful state?")
        assert result is not None
        assert result[0] == "Answer..."

    def test_ttl_expiry(self) -> None:
        cache = HotCache(default_ttl_s=0.05, max_size=10)
        cache.put("query", "response", [])
        assert cache.get("query") is not None
        time.sleep(0.1)
        assert cache.get("query") is None

    def test_missing_key(self) -> None:
        cache = HotCache(default_ttl_s=300.0, max_size=10)
        assert cache.get("nonexistent") is None

    def test_eviction(self) -> None:
        cache = HotCache(default_ttl_s=300.0, max_size=4)
        for i in range(5):
            cache.put(f"query-{i}", f"answer-{i}", [])
        # After exceeding max_size by 1, eviction halves the store (2 entries remain)
        assert len(cache._store) <= 2

    def test_stats(self) -> None:
        cache = HotCache(default_ttl_s=300.0, max_size=10)
        assert cache.stats() == {"size": 0, "alive": 0, "max_size": 10}
        cache.put("q1", "a1", [])
        cache.put("q2", "a2", [])
        stats = cache.stats()
        assert stats["size"] == 2
        assert stats["alive"] == 2
        assert stats["max_size"] == 10

    def test_invalidate(self) -> None:
        cache = HotCache(default_ttl_s=300.0, max_size=10)
        cache.put("q", "a", [])
        assert cache.get("q") is not None
        cache.invalidate("q")
        assert cache.get("q") is None

    def test_clear(self) -> None:
        cache = HotCache(default_ttl_s=300.0, max_size=10)
        cache.put("q", "a", [])
        cache.clear()
        assert cache.get("q") is None
        assert cache.stats()["size"] == 0

    def test_put_overwrite(self) -> None:
        cache = HotCache(default_ttl_s=300.0, max_size=10)
        cache.put("q", "old", [])
        cache.put("q", "new", [])
        assert cache.get("q")[0] == "new"

    def test_empty_string_not_stored(self) -> None:
        cache = HotCache(default_ttl_s=300.0, max_size=10)
        # Empty key
        assert cache.get("") is None
        cache.put("q", "", [])
        assert cache.get("q") is not None
