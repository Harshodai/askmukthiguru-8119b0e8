"""TokenBucketMiddleware's in-process fallback bucket and key derivation tests.

Regression for: any Redis exception on /api/chat's rate limiter used to fail
fully open (unlimited traffic per replica). `_local_allowed` is the
process-local fallback that now enforces the same capacity/refill instead.
Pure unit test — no Redis, no FastAPI app needed; `redis.from_url` only
builds a client object, it does not connect.
"""

from __future__ import annotations

import pytest
from fastapi import Request

from app.middleware.rate_limit import TokenBucketMiddleware, _chat_bucket_key
from services.tenant_context import TenantContext


def _make_middleware(capacity=3, refill_per_sec=0.0) -> TokenBucketMiddleware:
    # A dummy ASGI app is enough — dispatch() is never exercised here.
    async def _dummy_app(scope, receive, send):
        raise NotImplementedError

    return TokenBucketMiddleware(
        _dummy_app,
        redis_url="redis://localhost:6379/0",
        capacity=capacity,
        refill_per_sec=refill_per_sec,
    )


def _request_with_peer(peer: str, user_id: str = "") -> Request:
    headers = []
    if user_id:
        headers.append((b"x-user-id", user_id.encode()))
    client_tuple = (peer, 12345) if peer else None
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/chat",
            "raw_path": b"/api/chat",
            "query_string": b"",
            "headers": headers,
            "client": client_tuple,
            "server": ("testserver", 80),
        }
    )


def test_local_fallback_enforces_capacity():
    mw = _make_middleware(capacity=3, refill_per_sec=0.0)
    key = "rl:chat:test-tenant:test-user"
    results = [mw._local_allowed(key)[0] for _ in range(5)]
    assert results == [True, True, True, False, False]


def test_local_fallback_is_per_key():
    mw = _make_middleware(capacity=1, refill_per_sec=0.0)
    allowed_a, _ = mw._local_allowed("rl:chat:t:a")
    allowed_b, _ = mw._local_allowed("rl:chat:t:b")
    assert allowed_a is True
    assert allowed_b is True  # separate bucket, not starved by "a"


def test_local_fallback_refills_over_time():
    mw = _make_middleware(capacity=1, refill_per_sec=1000.0)  # fast refill for the test
    key = "rl:chat:test-tenant:refill"
    first, _ = mw._local_allowed(key)
    assert first is True
    # Manually age the bucket's timestamp to simulate elapsed time.
    tokens, ts = mw._local_buckets[key]
    mw._local_buckets[key] = (tokens, ts - 1.0)
    second, _ = mw._local_allowed(key)
    assert second is True


def test_client_supplied_user_id_does_not_change_chat_bucket_key():
    with TenantContext.scope("tenant-a", user_id="server-user"):
        first = _chat_bucket_key(_request_with_peer("192.0.2.10", "victim-a"))
        second = _chat_bucket_key(_request_with_peer("192.0.2.10", "victim-b"))

    assert first == second
    assert first == "rl:chat:tenant-a:192.0.2.10"


def test_server_observed_peer_ip_scopes_chat_bucket_key():
    with TenantContext.scope("tenant-a", user_id="server-user"):
        first = _chat_bucket_key(_request_with_peer("192.0.2.10", "same"))
        second = _chat_bucket_key(_request_with_peer("192.0.2.11", "same"))

    assert first != second


def test_ipv6_peer_address_is_compressed_and_normalized():
    with TenantContext.scope("tenant-a", user_id="server-user"):
        key = _chat_bucket_key(_request_with_peer("2001:0db8:0000:0000:0000:ff00:0042:8329"))
    assert key == "rl:chat:tenant-a:2001:db8::ff00:42:8329"


def test_invalid_peer_ip_falls_back_to_unknown_safely():
    with TenantContext.scope("tenant-a"):
        key_invalid = _chat_bucket_key(_request_with_peer("invalid-ip-string"))
        key_empty = _chat_bucket_key(_request_with_peer(""))
    assert key_invalid == "rl:chat:tenant-a:unknown"
    assert key_empty == "rl:chat:tenant-a:unknown"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
