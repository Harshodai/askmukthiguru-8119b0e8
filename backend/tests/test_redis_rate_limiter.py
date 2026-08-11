"""Tests for RedisBackedRateLimiter: Lua atomic decision, key digesting, Redis-down fallback.

Concurrency and Lua-script tests need a reachable Redis. The codebase runs
local Redis via docker compose (``docker compose up -d redis``); when it is
not reachable those tests are skipped with a clear reason. Fallback and
digest-pure tests never touch Redis.

The connection string is env-driven: ``REDIS_URL`` must be set to reach a
locally authenticated instance (e.g. the docker compose Redis, whose
credential is not committed here); the default is passwordless localhost.
"""

import os
import threading

import pytest

from app.security_utils import RedisBackedRateLimiter, _rate_limit_key_digest

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _redis_available() -> bool:
    try:
        import redis

        r = redis.Redis.from_url(
            REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5
        )
        return bool(r.ping())
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(),
    reason="local Redis not reachable at localhost:6379 — start via 'docker compose up -d redis', or set REDIS_URL for an authenticated instance",
)


class TestRateLimitKeyDigest:
    def test_deterministic_32_hex(self):
        raw = "auth_rl:acct:user@example.com"
        d1 = _rate_limit_key_digest(raw)
        d2 = _rate_limit_key_digest(raw)
        assert d1 == d2
        assert len(d1) == 32
        assert all(c in "0123456789abcdef" for c in d1)

    def test_does_not_leak_raw_identifier(self):
        raw = "auth_rl:acct:user@example.com"
        d = _rate_limit_key_digest(raw)
        assert d != raw
        assert "user@example.com" not in d
        assert "auth_rl" not in d


@requires_redis
class TestRedisLuaDecision:
    @pytest.fixture(autouse=True)
    def _cleanup_redis_keys(self):
        import redis

        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        yield
        for k in r.scan_iter("rl:*"):
            r.delete(k)

    def _make_limiter(self, **overrides):
        opts = dict(
            redis_url=REDIS_URL,
            ttl=60.0,
            max_requests=3,
            backoff_base=2.0,
            backoff_multiplier=2.0,
        )
        opts.update(overrides)
        return RedisBackedRateLimiter(**opts)

    def test_returns_one_zero_when_allowed(self):
        limiter = self._make_limiter()
        key = "auth_rl:ip:/api/auth/login:203.0.113.1"
        assert limiter.is_allowed(key, now=1000.0) == (True, 0.0)

    def test_returns_zero_retry_when_at_limit(self):
        limiter = self._make_limiter(max_requests=3)
        key = "auth_rl:ip:/api/auth/login:203.0.113.2"
        for _ in range(3):
            assert limiter.is_allowed(key, now=1000.0) == (True, 0.0)
        allowed, retry_after = limiter.is_allowed(key, now=1000.0)
        assert allowed is False
        assert retry_after == pytest.approx(60.0)

    def test_window_expiry_frees_slot(self):
        limiter = self._make_limiter(ttl=30.0, max_requests=1)
        key = "auth_rl:ip:/api/auth/login:203.0.113.3"
        assert limiter.is_allowed(key, now=1000.0) == (True, 0.0)
        assert limiter.is_allowed(key, now=1010.0) == (False, pytest.approx(20.0))
        assert limiter.is_allowed(key, now=1031.0) == (True, 0.0)

    def test_backoff_blocks_failed_attempts(self):
        limiter = self._make_limiter(max_requests=5)
        key = "auth_rl:ip:/api/auth/login:203.0.113.4"
        assert limiter.is_allowed(key, now=1000.0) == (True, 0.0)
        limiter.record_attempt(key, success=False, now=1000.0)
        allowed, retry_after = limiter.is_allowed(key, now=1001.0)
        assert allowed is False
        assert retry_after == pytest.approx(1.0)
        assert limiter.is_allowed(key, now=1002.0) == (True, 0.0)

    def test_success_clears_failure_backoff(self):
        limiter = self._make_limiter(max_requests=5)
        key = "auth_rl:ip:/api/auth/login:203.0.113.5"
        limiter.record_attempt(key, success=False, now=1000.0)
        limiter.record_attempt(key, success=True, now=1001.0)
        assert limiter.is_allowed(key, now=1001.0) == (True, 0.0)

    def test_lua_retry_after_preserves_fraction(self):
        # Failure penalty branch only: fresh zset (count=0), fail counter=1,
        # last fail 0.5s ago with backoff_base=2.0 → remaining wait 1.5s.
        # Pre-fix, Redis truncated the Lua number to an integer (1.0).
        import redis

        limiter = self._make_limiter(backoff_base=2.0, max_requests=5)
        key = "auth_rl:ip:/api/auth/login:203.0.113.8"
        now = 2000.0
        digest = _rate_limit_key_digest(key)
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        r.set(f"rl:fail:{digest}", "1")
        r.set(f"rl:lastfail:{digest}", str(now - (limiter.backoff_base * 0.25)))
        allowed, retry_after = limiter._redis_is_allowed(key, now)
        assert allowed is False
        assert 0.0 < retry_after < 2.0
        assert retry_after == pytest.approx(1.5)

    def test_redis_key_names_are_digested(self):
        import redis

        limiter = self._make_limiter()
        key = "auth_rl:ip:/api/auth/login:203.0.113.7"
        limiter.is_allowed(key, now=1000.0)
        limiter.record_attempt(key, success=False, now=1000.0)
        digest = _rate_limit_key_digest(key)
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        keys = set(r.scan_iter("rl:*"))
        assert f"rl:{digest}" in keys
        assert f"rl:fail:{digest}" in keys
        assert f"rl:lastfail:{digest}" in keys
        assert "rl:auth_rl:ip:/api/auth/login:203.0.113.7" not in keys

    def test_concurrent_calls_never_exceed_max_requests(self):
        max_requests = 5
        limiter = self._make_limiter(max_requests=max_requests)
        key = "auth_rl:ip:/api/auth/login:198.51.100.23"
        n_threads = 25
        barrier = threading.Barrier(n_threads)
        results: list = [None] * n_threads

        def worker(idx: int) -> None:
            barrier.wait()
            results[idx] = limiter.is_allowed(key)

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = sum(1 for allowed, _ in results if allowed)
        assert (
            successes == max_requests
        ), f"expected exactly {max_requests} successes (atomic Lua), got {successes}"


class TestRedisDownFallback:
    def _make_unavailable(self, **overrides):
        opts = dict(
            redis_url="redis://127.0.0.1:1/0",
            ttl=60.0,
            max_requests=2,
            backoff_base=2.0,
            backoff_multiplier=2.0,
        )
        opts.update(overrides)
        return RedisBackedRateLimiter(**opts)

    def test_fallback_active_and_returns_tuple(self):
        limiter = self._make_unavailable()
        assert limiter._fallback_active is True
        result = limiter.is_allowed("auth_rl:ip:/api/auth/login:1.1.1.1", now=1000.0)
        assert isinstance(result, tuple)
        assert result == (True, 0.0)

    def test_fallback_blocks_at_max_requests_with_retry_time(self):
        limiter = self._make_unavailable()
        key = "auth_rl:ip:/api/auth/login:1.1.1.2"
        assert limiter.is_allowed(key, now=1000.0) == (True, 0.0)
        assert limiter.is_allowed(key, now=1000.0) == (True, 0.0)
        allowed, retry_after = limiter.is_allowed(key, now=1000.0)
        assert allowed is False
        assert retry_after == pytest.approx(60.0)

    def test_fallback_window_counts_allowed_events(self):
        # is_allowed must record allowed events on the fallback path —
        # mirrors the Lua ZADD-on-allow. Pre-fix, this returned (True, 0.0)
        # forever, disabling the window for callers that never record.
        limiter = self._make_unavailable(max_requests=1, ttl=60.0)
        key = "auth_rl:ip:/api/auth/login:1.1.1.4"
        assert limiter.is_allowed(key, now=100.0) == (True, 0.0)
        allowed, retry_after = limiter.is_allowed(key, now=100.5)
        assert allowed is False
        assert retry_after == pytest.approx(59.5)

    def test_fallback_tracks_failures_for_backoff(self):
        limiter = self._make_unavailable()
        key = "auth_rl:ip:/api/auth/login:1.1.1.3"
        limiter.record_attempt(key, success=False, now=1000.0)
        allowed, retry_after = limiter.is_allowed(key, now=1001.0)
        assert allowed is False
        assert retry_after == pytest.approx(1.0)
        assert limiter.is_allowed(key, now=1002.0) == (True, 0.0)