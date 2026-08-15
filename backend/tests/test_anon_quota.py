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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
