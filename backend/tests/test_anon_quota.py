"""Tests for the anonymous message-quota domain."""
from __future__ import annotations

import asyncio

import pytest

from services.anon_quota_port import QuotaResult
from services.anon_quota_memory import AnonQuotaMemoryAdapter
from services.anon_quota_service import AnonQuotaService


@pytest.fixture
def memory_adapter():
    return AnonQuotaMemoryAdapter()


@pytest.mark.asyncio
async def test_memory_adapter_allows_under_limit(memory_adapter):
    r = await memory_adapter.check_and_record("anon:a", 3, 60.0, 30.0)
    assert r.allowed is True
    assert r.remaining == 2
    assert r.total_limit == 3


@pytest.mark.asyncio
async def test_memory_adapter_blocks_at_limit(memory_adapter):
    for _ in range(3):
        await memory_adapter.check_and_record("anon:b", 3, 60.0, 30.0)
    blocked = await memory_adapter.check_and_record("anon:b", 3, 60.0, 30.0)
    assert blocked.allowed is False
    assert blocked.remaining == 0


@pytest.mark.asyncio
async def test_memory_adapter_resets_window(memory_adapter):
    await memory_adapter.check_and_record("anon:c", 1, 60.0, 30.0)
    await memory_adapter.reset("anon:c")
    r = await memory_adapter.check_and_record("anon:c", 1, 60.0, 30.0)
    assert r.allowed is True


@pytest.mark.asyncio
async def test_memory_adapter_release_returns_slot(memory_adapter):
    reserved = await memory_adapter.check_and_record("anon:d", 1, 60.0, 30.0)
    assert reserved.allowed is True
    assert reserved.reservation_id is not None
    blocked = await memory_adapter.check_and_record("anon:d", 1, 60.0, 30.0)
    assert blocked.allowed is False
    await memory_adapter.release("anon:d", reserved.reservation_id)
    r = await memory_adapter.check_and_record("anon:d", 1, 60.0, 30.0)
    assert r.allowed is True


@pytest.mark.asyncio
async def test_memory_adapter_release_unknown_id_is_noop(memory_adapter):
    reserved = await memory_adapter.check_and_record("anon:e", 1, 60.0, 30.0)
    await memory_adapter.release("anon:e", "does-not-exist")
    assert (await memory_adapter.inspect("anon:e", 1, 60.0)).remaining == 0
    await memory_adapter.release("anon:e", reserved.reservation_id)
    assert (await memory_adapter.inspect("anon:e", 1, 60.0)).remaining == 1


@pytest.mark.asyncio
async def test_memory_adapter_claim_keeps_slot(memory_adapter):
    reserved = await memory_adapter.check_and_record("anon:f", 1, 60.0, 30.0)
    await memory_adapter.claim("anon:f", reserved.reservation_id)
    assert (await memory_adapter.inspect("anon:f", 1, 60.0)).remaining == 0
    await memory_adapter.claim("anon:f", "does-not-exist")
    assert (await memory_adapter.inspect("anon:f", 1, 60.0)).remaining == 0


@pytest.mark.asyncio
async def test_memory_adapter_unclaimed_reservation_is_reaped(memory_adapter):
    # Simulates a queued job dropped by queue-TTL expiry: the reservation is
    # never claimed and must stop burning its slot after the deadline.
    reserved = await memory_adapter.check_and_record("anon:g", 1, 60.0, 0.05)
    assert reserved.reservation_id is not None
    assert (await memory_adapter.inspect("anon:g", 1, 60.0)).remaining == 0
    await asyncio.sleep(0.06)
    r = await memory_adapter.inspect("anon:g", 1, 60.0)
    assert r.remaining == 1
    assert r.allowed is True


@pytest.mark.asyncio
async def test_memory_adapter_reap_expired_behind_alive_head(memory_adapter):
    # A head-only reap would stop at the alive/committed head and miss an
    # expired unclaimed reservation behind it. The scan must remove the
    # expired member while keeping the alive ones.
    await memory_adapter.check_and_record("anon:h", 3, 60.0, 30.0)
    claimed = await memory_adapter.check_and_record("anon:h", 3, 60.0, 0.05)
    await memory_adapter.claim("anon:h", claimed.reservation_id)
    await memory_adapter.check_and_record("anon:h", 3, 60.0, 0.05)
    await asyncio.sleep(0.06)
    r = await memory_adapter.inspect("anon:h", 3, 60.0)
    assert r.remaining == 1


@pytest.mark.asyncio
async def test_service_authenticated_users_bypass_quota(monkeypatch):
    monkeypatch.setattr(
        "services.anon_quota_service.settings",
        type("S", (), {"anon_quota_enabled": True, "anon_quota_messages": 2, "anon_quota_window_hours": 24.0})(),
    )
    svc = AnonQuotaService()
    auth_user = {"id": "user-123", "is_anonymous": False}
    for _ in range(10):
        r = await svc.check_and_record(auth_user)
        assert r.allowed is True


@pytest.mark.asyncio
async def test_service_enforces_anonymous_quota(monkeypatch):
    monkeypatch.setattr(
        "services.anon_quota_service.settings",
        type("S", (), {"anon_quota_enabled": True, "anon_quota_messages": 3, "anon_quota_window_hours": 24.0})(),
    )
    svc = AnonQuotaService()
    anon = {"id": "anon:abc", "is_anonymous": True}
    for i in range(4):
        r = await svc.check_and_record(anon)
        assert r.allowed == (i < 3), f"iteration {i}: {r}"


@pytest.mark.asyncio
async def test_service_claim_is_noop_for_authenticated_and_missing_token(monkeypatch):
    monkeypatch.setattr(
        "services.anon_quota_service.settings",
        type("S", (), {"anon_quota_enabled": True, "anon_quota_messages": 3, "anon_quota_window_hours": 24.0})(),
    )
    svc = AnonQuotaService()
    auth_user = {"id": "user-123", "is_anonymous": False}
    await svc.claim(auth_user, "res-1")
    await svc.claim({"id": "anon:xyz", "is_anonymous": True}, None)
    assert (await svc.inspect({"id": "anon:xyz", "is_anonymous": True})).remaining == 3


def test_quota_result_properties():
    ok = QuotaResult(allowed=True, remaining=4, total_limit=5)
    assert not ok.quota_exceeded
    bad = QuotaResult(allowed=False, remaining=0, total_limit=5, retry_after_seconds=60)
    assert bad.quota_exceeded


@pytest.mark.asyncio
async def test_memory_adapter_bounded_sessions():
    adapter = AnonQuotaMemoryAdapter(max_sessions=3)
    # Fill 3 sessions
    await adapter.check_and_record("anon:1", 5, 60.0, 30.0)
    await adapter.check_and_record("anon:2", 5, 60.0, 30.0)
    await adapter.check_and_record("anon:3", 5, 60.0, 30.0)
    assert len(adapter._windows) == 3

    # Adding a 4th session must evict the oldest session
    await adapter.check_and_record("anon:4", 5, 60.0, 30.0)
    assert len(adapter._windows) <= 3
    # anon:1 was oldest, should have been evicted
    assert "anon:1" not in adapter._windows
    assert "anon:4" in adapter._windows


@pytest.mark.asyncio
async def test_redis_adapter_degrades_on_redis_error(monkeypatch):
    from unittest.mock import AsyncMock
    from redis.exceptions import RedisError
    from services.anon_quota_redis import AnonQuotaRedisAdapter
    from app.metrics import ANON_QUOTA_DEGRADED_MODE

    mock_redis = AsyncMock()
    mock_redis.eval.side_effect = RedisError("Connection dropped")
    mock_redis.zrange.side_effect = RedisError("Connection dropped")
    mock_redis.zremrangebyscore.side_effect = RedisError("Connection dropped")

    monkeypatch.setattr(
        "services.anon_quota_redis.settings",
        type("S", (), {"anon_quota_degraded_limit": 3})(),
        raising=False,
    )

    adapter = AnonQuotaRedisAdapter(mock_redis, max_sessions=10)
    sid = "anon:outage_test"

    # Should allow up to conservative limit (3), then block on 4th call — NEVER fail open!
    r1 = await adapter.check_and_record(sid, 5, 60.0, 30.0)
    assert r1.allowed is True
    assert r1.remaining == 2
    assert r1.total_limit == 3

    r2 = await adapter.check_and_record(sid, 5, 60.0, 30.0)
    assert r2.allowed is True
    assert r2.remaining == 1

    r3 = await adapter.check_and_record(sid, 5, 60.0, 30.0)
    assert r3.allowed is True
    assert r3.remaining == 0

    # 4th attempt must be BLOCKED (no fail-open)
    r4 = await adapter.check_and_record(sid, 5, 60.0, 30.0)
    assert r4.allowed is False
    assert r4.remaining == 0


@pytest.mark.asyncio
async def test_redis_adapter_inspect_and_reset_degrade_on_redis_error():
    from unittest.mock import AsyncMock
    from redis.exceptions import RedisError
    from services.anon_quota_redis import AnonQuotaRedisAdapter

    mock_redis = AsyncMock()
    mock_redis.eval.side_effect = RedisError("Connection dropped")
    mock_redis.zremrangebyscore.side_effect = RedisError("Connection dropped")
    mock_redis.zrange.side_effect = RedisError("Connection dropped")
    mock_redis.delete.side_effect = RedisError("Connection dropped")

    adapter = AnonQuotaRedisAdapter(mock_redis, max_sessions=10)
    sid = "anon:inspect_test"

    # Record into degraded in-memory store
    await adapter.check_and_record(sid, 5, 60.0, 30.0)
    ins = await adapter.inspect(sid, 5, 60.0)
    assert ins.remaining == 2  # degraded limit (3) - 1 = 2

    # Reset in degraded store
    await adapter.reset(sid)
    ins2 = await adapter.inspect(sid, 5, 60.0)
    assert ins2.remaining == 3


@pytest.mark.asyncio
async def test_memory_adapter_rejects_unenforceable_limit():
    # Limits above the deque capacity cannot be enforced in memory and must be
    # rejected, not silently truncated (which would under-enforce the quota).
    adapter = AnonQuotaMemoryAdapter()
    with pytest.raises(ValueError):
        await adapter.check_and_record("anon:big", 201, 60.0, 30.0)
    with pytest.raises(ValueError):
        await adapter.inspect("anon:big", 500, 60.0)
    # The exact capacity is enforceable.
    ok = await adapter.check_and_record("anon:cap", 200, 60.0, 30.0)
    assert ok.allowed is True and ok.total_limit == 200


@pytest.mark.asyncio
async def test_memory_adapter_applies_max_limit_cap():
    adapter = AnonQuotaMemoryAdapter(max_limit=3)
    r = await adapter.check_and_record("anon:capped", 5, 60.0, 30.0)
    assert r.allowed is True and r.total_limit == 3 and r.remaining == 2
    for _ in range(2):
        await adapter.check_and_record("anon:capped", 5, 60.0, 30.0)
    blocked = await adapter.check_and_record("anon:capped", 5, 60.0, 30.0)
    assert blocked.allowed is False


@pytest.mark.asyncio
async def test_redis_adapter_claim_release_inspect_stay_on_fallback(monkeypatch):
    # Once a session degrades to the in-memory fallback, claim/release/inspect
    # and later checks must keep using the fallback (no split-brain with Redis).
    from unittest.mock import AsyncMock
    from redis.exceptions import RedisError
    from services.anon_quota_redis import AnonQuotaRedisAdapter

    monkeypatch.setattr(
        "services.anon_quota_redis.settings",
        type("S", (), {"anon_quota_degraded_limit": 3})(),
        raising=False,
    )

    mock_redis = AsyncMock()
    mock_redis.eval.side_effect = RedisError("Connection dropped")

    adapter = AnonQuotaRedisAdapter(mock_redis, max_sessions=10)
    sid = "anon:splitbrain"

    # First call degrades and records on the fallback.
    r1 = await adapter.check_and_record(sid, 5, 60.0, 30.0)
    assert r1.allowed is True and r1.reservation_id is not None

    # claim/release must hit the fallback, never Redis.
    await adapter.claim(sid, r1.reservation_id)
    await adapter.release(sid, r1.reservation_id)
    assert mock_redis.eval.call_count == 1  # only the initial degraded attempt
    assert mock_redis.hdel.call_count == 0
    assert mock_redis.zrem.call_count == 0

    # Subsequent checks route to the fallback and enforce the degraded limit.
    # (claim + release of r1 leaves one slot recorded.)
    r2 = await adapter.check_and_record(sid, 5, 60.0, 30.0)
    assert r2.allowed is True and r2.remaining == 2
    r3 = await adapter.check_and_record(sid, 5, 60.0, 30.0)
    assert r3.allowed is True and r3.remaining == 1
    r4 = await adapter.check_and_record(sid, 5, 60.0, 30.0)
    assert r4.allowed is True and r4.remaining == 0
    r5 = await adapter.check_and_record(sid, 5, 60.0, 30.0)
    assert r5.allowed is False
    ins = await adapter.inspect(sid, 5, 60.0)
    assert ins.remaining == 0
    assert mock_redis.eval.call_count == 1


@pytest.mark.asyncio
async def test_service_cold_start_fallback_uses_degraded_limit(monkeypatch):
    # When the initial Redis probe fails, the in-memory adapter must enforce
    # anon_quota_degraded_limit rather than the normal session limit.
    import redis.asyncio as aioredis

    def boom(*args, **kwargs):
        raise ConnectionError("no redis")

    monkeypatch.setattr(aioredis, "from_url", boom)
    monkeypatch.setattr(
        "services.anon_quota_service.settings",
        type(
            "S",
            (),
            {
                "anon_quota_enabled": True,
                "anon_quota_messages": 5,
                "anon_quota_window_hours": 24.0,
                "anon_quota_degraded_limit": 3,
            },
        )(),
    )

    svc = AnonQuotaService(redis_url="redis://localhost:6379/0")
    anon = {"id": "anon:coldstart", "is_anonymous": True}
    for i in range(4):
        r = await svc.check_and_record(anon)
        assert r.allowed == (i < 3), f"iteration {i}: {r}"
    assert (await svc.inspect(anon)).remaining == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
