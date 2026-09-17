"""F-COST-1: anon-session minting must be throttled per IP.

Before this fix, POST /api/auth/anon-session was absent from
_AUTH_LIMIT_PATHS in app/main.py, so one IP could mint unlimited signed
sessions -> anon_quota_messages free LLM turns each, unthrottled
(~200 sessions/min x 5 msgs =~ 1000 free turns/min from one IP).

This locks in that the shared auth rate limiter now covers the endpoint:
after max_requests successes in the window, further requests from the same
IP get 429.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import _AUTH_RATE_LIMITER, app
from app.security_utils import RedisBackedRateLimiter, _rate_limit_key_digest

_IP_KEY = "auth_rl:ip:/api/auth/anon-session:testclient"


def _clear_bucket() -> None:
    """Evict any prior state for this test's rate-limit key so repeated
    local runs (or a Redis-backed limiter, which has no in-memory reset)
    don't leak between runs within the same TTL window."""
    if (
        isinstance(_AUTH_RATE_LIMITER, RedisBackedRateLimiter)
        and _AUTH_RATE_LIMITER._redis is not None
    ):
        digest = _rate_limit_key_digest(_IP_KEY)
        _AUTH_RATE_LIMITER._redis.delete(
            f"rl:{digest}", f"rl:fail:{digest}", f"rl:lastfail:{digest}"
        )
    elif hasattr(_AUTH_RATE_LIMITER, "reset"):
        _AUTH_RATE_LIMITER.reset()


def test_anon_session_minting_is_rate_limited_per_ip():
    _clear_bucket()
    try:
        # Use TestClient as a context manager so all 8 requests share one
        # anyio event loop/portal — a fresh loop per call (the default for
        # a bare TestClient(app).post(...) sequence) breaks the async Redis
        # client the rate limiter holds onto ("Event loop is closed"),
        # which fails open by design (see Redis Degradation invariant) and
        # would hide the very throttle this test exists to prove.
        with TestClient(app) as client:
            statuses = [client.post("/api/auth/anon-session").status_code for _ in range(8)]
    finally:
        _clear_bucket()

    assert 429 in statuses, f"expected a 429 among repeated anon-session mints, got {statuses}"
    # first request must still succeed — this is a throttle, not an outage
    assert statuses[0] == 200


if __name__ == "__main__":
    test_anon_session_minting_is_rate_limited_per_ip()
    print("OK")
