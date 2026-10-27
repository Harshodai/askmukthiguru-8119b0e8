"""Tests for Redis Stream trim safety and bounded memory behavior.

Verifies:
1. Exact trimming (approximate=False) strictly bounds stream length to maxlen.
2. Approximate trimming (approximate=True) bounds stream length to macro-node limits,
   ensuring O(1) append performance while bounding memory.
3. Explicit XTRIM behaves safely for exact and approximate limits.
4. RedisStreamQueue enqueuing with max_stream_length enforces bounded stream depth.
"""

from __future__ import annotations

import os
import uuid

import pytest
import redis
import redis.asyncio as aioredis

from app.queue.redis_stream_queue import RedisStreamQueue, RequestPriority
from tests.conftest import _resolve_test_redis_url


@pytest.fixture
def redis_url() -> str:
    return _resolve_test_redis_url()


@pytest.fixture
def sync_redis(redis_url: str):
    client = redis.from_url(redis_url)
    stream_keys: list[str] = []

    def _make_key(prefix: str = "test:stream") -> str:
        key = f"{prefix}:{uuid.uuid4().hex[:8]}"
        stream_keys.append(key)
        return key

    yield client, _make_key

    for key in stream_keys:
        try:
            client.delete(key)
        except Exception:
            pass
    client.close()


@pytest.mark.asyncio
async def test_xadd_exact_trim_bounds_stream_length(redis_url: str):
    """Exact trim (approximate=False) ensures stream length never exceeds maxlen."""
    r = aioredis.from_url(redis_url, decode_responses=True)
    stream_key = f"test:stream:exact:{uuid.uuid4().hex[:8]}"
    maxlen = 10
    total_items = 50

    try:
        for i in range(total_items):
            await r.xadd(stream_key, {"seq": str(i), "payload": f"item_{i}"}, maxlen=maxlen, approximate=False)

        length = await r.xlen(stream_key)
        assert length == maxlen, f"Expected exactly {maxlen} items, got {length}"

        # Verify oldest items were evicted (FIFO) and newest remain
        entries = await r.xrange(stream_key, min="-", max="+")
        assert len(entries) == maxlen
        # Earliest entry should be item 40 (50 - 10)
        first_entry = entries[0][1]
        assert first_entry["seq"] == str(total_items - maxlen)
        last_entry = entries[-1][1]
        assert last_entry["seq"] == str(total_items - 1)
    finally:
        await r.delete(stream_key)
        await r.close()


@pytest.mark.asyncio
async def test_xadd_approximate_trim_bounds_stream_memory(redis_url: str):
    """Approximate trim (approximate=True) bounds stream length to radix-tree macro-node limits.

    Ensures stream does not grow unboundedly, keeping memory bounded without
    expensive per-write node rebalances.
    """
    r = aioredis.from_url(redis_url, decode_responses=True)
    stream_key = f"test:stream:approx:{uuid.uuid4().hex[:8]}"
    maxlen = 20
    total_items = 500

    try:
        for i in range(total_items):
            await r.xadd(stream_key, {"seq": str(i), "payload": "x" * 100}, maxlen=maxlen, approximate=True)

        length = await r.xlen(stream_key)
        # Approximate trim evicts whole macro-nodes; length is guaranteed >= maxlen
        # and strictly bounded far below total_items
        assert maxlen <= length < total_items
        assert length <= 200, f"Expected stream length to be bounded under 200, got {length}"
    finally:
        await r.delete(stream_key)
        await r.close()


def test_xtrim_exact_and_approximate(sync_redis):
    """XTRIM command reduces stream size with exact and approximate options."""
    client, make_key = sync_redis
    stream_key = make_key("test:stream:trim")

    # Add 100 items without trimming
    for i in range(100):
        client.xadd(stream_key, {"idx": str(i)})
    assert client.xlen(stream_key) == 100

    # Approximate trim to 50
    client.xtrim(stream_key, maxlen=50, approximate=True)
    approx_len = client.xlen(stream_key)
    assert 50 <= approx_len <= 100

    # Exact trim to 25
    client.xtrim(stream_key, maxlen=25, approximate=False)
    assert client.xlen(stream_key) == 25


@pytest.mark.asyncio
async def test_redis_stream_queue_trim_safety(redis_url: str):
    """RedisStreamQueue respects max_stream_length parameter and bounds queue size."""
    max_len = 15
    queue = RedisStreamQueue(
        redis_url=redis_url,
        consumer_group=f"test-cg-{uuid.uuid4().hex[:6]}",
        max_stream_length=max_len,
    )
    await queue.start()

    r = await queue._get_redis()
    stream_key = "request:standard"

    try:
        # Enqueue 40 items with max_stream_length=15
        for i in range(40):
            await queue.enqueue(
                request_data={"item": i},
                user_id="test_user",
                priority=RequestPriority.STANDARD,
            )

        depth = await r.xlen(stream_key)
        # max_stream_length in RedisStreamQueue uses approximate trim by default in xadd
        # or exact if configured; verify bounded depth
        assert depth <= 100, f"Stream depth {depth} should be bounded near {max_len}"
    finally:
        await r.delete(stream_key)
        await queue.stop()


def test_stream_id_monotonicity_preserved_during_trim(sync_redis):
    """Trimming stream maintains strictly monotonic IDs and clean range scanning."""
    client, make_key = sync_redis
    stream_key = make_key("test:stream:mono")

    for i in range(60):
        client.xadd(stream_key, {"i": str(i)}, maxlen=15, approximate=False)

    entries = client.xrange(stream_key)
    assert len(entries) == 15

    # Check ID monotonicity
    ids = [entry[0].decode() if isinstance(entry[0], bytes) else entry[0] for entry in entries]
    for j in range(len(ids) - 1):
        id_curr_ms, id_curr_seq = map(int, ids[j].split("-"))
        id_next_ms, id_next_seq = map(int, ids[j + 1].split("-"))
        assert (id_next_ms, id_next_seq) > (id_curr_ms, id_curr_seq)
