"""P1-SEC-9: admin user cache is bounded (memory-growth fix).

The admin-role lookup cache (``SupabaseAuthStrategy._admin_cache``) was an
unbounded per-user dict: every distinct ``user_id`` hit on
``_check_admin_role`` inserted a new key that lived forever. This module
locks in the fix:

  - the cache is capped at ``_CACHE_MAXSIZE`` (256) entries,
  - the oldest entry is evicted on overflow (FIFO by insertion order),
  - TTL/hit semantics are unchanged: a fresh cache hit short-circuits
    before any Supabase/network call.
"""
from __future__ import annotations

import inspect
import time
import uuid

import pytest

from services.auth_service import (
    SupabaseAuthStrategy,
    _cache_admin_lookup,
)


def _new_user_id() -> str:
    return str(uuid.uuid4())


def _fresh_cache() -> dict[str, tuple]:
    cache: dict[str, tuple] = {}
    return cache


class TestSec9AdminCacheBounded:
    """P1-SEC-9: the admin lookup cache must never grow without bound."""

    def test_sec9_cache_caps_size_at_maxsize(self):
        cache = _fresh_cache()
        for _ in range(300):
            _cache_admin_lookup(cache, _new_user_id(), False, time.time(), 256)
        assert len(cache) <= 256

    def test_sec9_cache_evicts_oldest_entry_on_overflow(self):
        cache = _fresh_cache()
        for i in range(256):
            _cache_admin_lookup(cache, f"user-{i:03d}", False, time.time(), 256)
        _cache_admin_lookup(cache, "overflow-user", True, time.time(), 256)
        assert len(cache) == 256
        assert "user-000" not in cache, "oldest entry must be evicted first"
        assert cache["overflow-user"][0] is True, "newest entry must be retained"

    def test_sec9_below_maxsize_no_eviction(self):
        cache = _fresh_cache()
        for i in range(10):
            _cache_admin_lookup(cache, f"user-{i:03d}", False, time.time(), 256)
        assert len(cache) == 10
        assert "user-000" in cache

    def test_sec9_class_wiring_uses_bounded_helper_and_maxsize(self):
        """The class must route writes through the bounded helper + cap."""
        src = inspect.getsource(SupabaseAuthStrategy)
        assert "_CACHE_MAXSIZE" in src, "class must declare a cache size cap"
        assert "_cache_admin_lookup" in src, "class must write via bounded helper"

    @pytest.mark.asyncio
    async def test_sec9_cache_hit_short_circuits_before_network(self):
        """A fresh cache entry returns immediately (no Supabase call)."""
        strategy = SupabaseAuthStrategy()
        uid = _new_user_id()
        strategy._admin_cache[uid] = (True, time.time())
        try:
            result = await strategy._check_admin_role(uid)
        finally:
            strategy._admin_cache.pop(uid, None)
        assert result is True

    @pytest.mark.asyncio
    async def test_sec9_class_level_cache_stays_bounded_under_churn(self):
        """300+ distinct lookups through the shared class dict stay <= 256."""
        cache = SupabaseAuthStrategy._admin_cache
        cache.clear()
        try:
            strategy = SupabaseAuthStrategy()
            for _ in range(300):
                uid = _new_user_id()
                _cache_admin_lookup(
                    cache, uid, False, time.time(), SupabaseAuthStrategy._CACHE_MAXSIZE
                )
            assert len(cache) <= SupabaseAuthStrategy._CACHE_MAXSIZE
            # The instance path reads the same bounded dict.
            assert strategy._admin_cache is cache
        finally:
            cache.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
