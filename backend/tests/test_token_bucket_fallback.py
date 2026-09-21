"""TokenBucketMiddleware's in-process fallback bucket.

Regression for: any Redis exception on /api/chat's rate limiter used to fail
fully open (unlimited traffic per replica). `_local_allowed` is the
process-local fallback that now enforces the same capacity/refill instead.
Pure unit test — no Redis, no FastAPI app needed; `redis.from_url` only
builds a client object, it does not connect.
"""

from app.middleware.rate_limit import TokenBucketMiddleware


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


if __name__ == "__main__":
    test_local_fallback_enforces_capacity()
    test_local_fallback_is_per_key()
    test_local_fallback_refills_over_time()
    print("ok")
