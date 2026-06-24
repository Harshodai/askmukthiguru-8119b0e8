import asyncio
import time

import pytest
import redis

from app.coalescer import RedisCoalescer, _InMemoryCoalescer, build_coalescer

# Use the Redis container running on localhost for testing
REDIS_TEST_URL = "redis://:mukthiguru_redis_pass@localhost:6379/0"


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

    # Clean any leftover keys
    key = "test_redis_concurrency_key"
    await coalescer._redis.delete(
        f"coalesce:lock:{key}", f"coalesce:result:{key}", f"coalesce:list:{key}"
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

    key = "test_redis_fail_key"
    await coalescer._redis.delete(
        f"coalesce:lock:{key}", f"coalesce:result:{key}", f"coalesce:list:{key}"
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
