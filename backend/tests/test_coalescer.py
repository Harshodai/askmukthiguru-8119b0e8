import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis

from app.coalescer import RedisCoalescer, _InMemoryCoalescer, build_coalescer

# Use the Redis container running on localhost for testing. Env-driven with a
# passwordless localhost fallback — never commit a Redis password.
REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "redis://localhost:6379/0")


def _redis_available() -> bool:
    try:
        client = redis.Redis.from_url(REDIS_TEST_URL, socket_connect_timeout=1, socket_timeout=1)
        return client.ping() is True
    except Exception:
        return False


_redis_up = _redis_available()


@pytest.mark.asyncio
async def test_in_memory_coalescer_concurrency():
    coalescer = _InMemoryCoalescer(ttl=5.0)
    call_count = 0

    async def dummy_task():
        nonlocal call_count
        await asyncio.sleep(0.1)
        call_count += 1
        return {"data": "success"}

    # Run multiple concurrent requests
    results = await asyncio.gather(
        coalescer.get_or_run("test_key", dummy_task),
        coalescer.get_or_run("test_key", dummy_task),
        coalescer.get_or_run("test_key", dummy_task),
    )

    assert len(results) == 3
    assert all(r == {"data": "success"} for r in results)
    assert call_count == 1  # Only run once


@pytest.mark.skipif(not _redis_up, reason="Redis not reachable at test URL")
@pytest.mark.asyncio
async def test_redis_coalescer_concurrency():
    # Attempt to connect to the actual Redis instance on localhost
    coalescer = build_coalescer(REDIS_TEST_URL, ttl=5.0)

    # If build_coalescer falls back to in-memory, we can still test, but let's ensure we test RedisCoalescer if possible
    assert isinstance(coalescer, RedisCoalescer), (
        "RedisCoalescer should be built when Redis is available"
    )

    # Clean any leftover keys using tenant-aware namespace
    from services.tenant_context import TenantContext

    tenant_id = TenantContext.get()
    key = "test_redis_concurrency_key"
    await coalescer._redis.delete(
        f"coalesce:{tenant_id}:lock:{key}",
        f"coalesce:{tenant_id}:result:{key}",
        f"coalesce:{tenant_id}:list:{key}",
    )

    call_count = 0

    async def dummy_task():
        nonlocal call_count
        await asyncio.sleep(0.2)
        call_count += 1
        return {"value": 42}

    start_time = time.monotonic()

    # Run multiple concurrent requests
    results = await asyncio.gather(
        coalescer.get_or_run(key, dummy_task),
        coalescer.get_or_run(key, dummy_task),
        coalescer.get_or_run(key, dummy_task),
    )

    duration = time.monotonic() - start_time

    assert len(results) == 3
    assert all(r == {"value": 42} for r in results)
    assert call_count == 1  # Under coalescer, it should run exactly once

    # The followers should finish almost immediately after the leader finishes (duration ~ 0.2s)
    # 0ms wake-up latency test: check that followers didn't poll with a sleep wait loop but woke up immediately
    assert duration < 0.4, f"Total execution took too long: {duration}s"

    await coalescer.close()


@pytest.mark.skipif(not _redis_up, reason="Redis not reachable at test URL")
@pytest.mark.asyncio
async def test_redis_coalescer_leader_failure_takeover():
    coalescer = build_coalescer(REDIS_TEST_URL, ttl=5.0)
    assert isinstance(coalescer, RedisCoalescer)

    from services.tenant_context import TenantContext

    tenant_id = TenantContext.get()
    key = "test_redis_fail_key"
    await coalescer._redis.delete(
        f"coalesce:{tenant_id}:lock:{key}",
        f"coalesce:{tenant_id}:result:{key}",
        f"coalesce:{tenant_id}:list:{key}",
    )

    # Leader fails by raising an exception
    async def failing_task():
        await asyncio.sleep(0.1)
        raise ValueError("Leader failed")

    async def successful_task():
        return {"data": "recovered"}

    # Run the leader task (which fails)
    with pytest.raises(ValueError, match="Leader failed"):
        await coalescer.get_or_run(key, failing_task)

    # The follower should now be able to run and take over
    result = await coalescer.get_or_run(key, successful_task)
    assert result == {"data": "recovered"}

    await coalescer.close()


@pytest.mark.asyncio
async def test_redis_coalescer_degrades_to_memory_on_lock_acquire_failure():
    """Live chaos-testing discovery (2026-09-05): the lock-acquire SET NX was
    completely unguarded — a Redis outage raised uncaught from here, the
    FIRST thing orchestrate() touches per request, so every chat request
    failed before the pipeline even started. It must instead degrade to the
    in-memory coalescer and still run the actual work."""
    coalescer = RedisCoalescer.__new__(RedisCoalescer)
    coalescer._redis = MagicMock()
    coalescer._redis.set = AsyncMock(side_effect=redis.exceptions.ConnectionError("refused"))
    coalescer._ttl = 5
    coalescer._poll_interval = 0.1
    coalescer._max_wait = 5
    coalescer._memory_fallback = None

    async def task():
        return {"data": "ok"}

    result = await coalescer.get_or_run("degrade_key", task)
    assert result == {"data": "ok"}
    assert isinstance(coalescer._memory_fallback, _InMemoryCoalescer)

    # Once degraded, subsequent calls must go straight to the fallback
    # without touching the dead Redis client again.
    coalescer._redis.set.reset_mock()
    result2 = await coalescer.get_or_run("degrade_key_2", task)
    assert result2 == {"data": "ok"}
    coalescer._redis.set.assert_not_called()


@pytest.mark.asyncio
async def test_redis_coalescer_leader_returns_result_when_publish_fails():
    """Live chaos-testing discovery (2026-09-05): a Redis outage DURING
    result publication (after the real work already succeeded) used to
    propagate out of _leader_work and lose the leader's own already-computed
    good result — publishing for followers is an optimization, never a
    reason to discard the caller's own answer."""
    coalescer = RedisCoalescer.__new__(RedisCoalescer)
    coalescer._redis = MagicMock()
    coalescer._redis.set = AsyncMock(
        side_effect=[True, redis.exceptions.ConnectionError("refused mid-publish")]
    )
    coalescer._redis.rpush = AsyncMock()
    coalescer._redis.expire = AsyncMock()
    coalescer._redis.delete = AsyncMock()
    coalescer._ttl = 5
    coalescer._poll_interval = 0.1
    coalescer._max_wait = 5
    coalescer._memory_fallback = None

    async def task():
        return {"data": "computed-successfully"}

    # First .set() call is the lock acquire (succeeds); second is the result
    # publish (fails) — the leader must still return its own result.
    result = await coalescer.get_or_run("publish_fail_key", task)
    assert result == {"data": "computed-successfully"}
