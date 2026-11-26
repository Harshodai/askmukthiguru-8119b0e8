"""Seeker comprehension signals and seen-clip reads are consent-gated (audit finding 13)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import settings
from services import first_person_seen_store as seen_store
from services.personalization import cascade_erasure
from services.seeker import consent
from services.tenant_context import TenantContext

USER = "11111111-1111-1111-1111-111111111111"
ROOT = Path(__file__).resolve().parents[2]
CITES = [{"id": "c1", "videoId": "v1", "text": "A verbatim span."}]


class _Outbox:
    def __init__(self, receipt):
        self.receipt = receipt

    async def active_consent(self, *, user_id, tenant_id, **_):
        return self.receipt


def _ctx(**kw):
    base = {"user_id": USER, "incognito": False, "is_benchmark": False, "user_msg": "I am confused"}
    return SimpleNamespace(**{**base, **kw})


def _container(receipt):
    return SimpleNamespace(
        memory_outbox=_Outbox(receipt), supabase_client=MagicMock(), redis_client=None
    )


@pytest.fixture(autouse=True)
def _tenant():
    TenantContext.set("oneness")
    yield
    TenantContext.reset()


def _run(coro):
    return asyncio.run(coro)


def _inserts(container):
    return container.supabase_client.table.return_value.insert.call_args_list


def test_flag_off_writes_nothing(monkeypatch):
    monkeypatch.setattr(settings, "seeker_comprehension_recovery_enabled", False)
    c = _container({"id": "r1"})
    assert _run(consent.record_comprehension_signal(_ctx(), c, CITES)) is False
    assert not _inserts(c)


def test_flag_on_without_consent_writes_nothing(monkeypatch):
    monkeypatch.setattr(settings, "seeker_comprehension_recovery_enabled", True)
    c = _container(None)
    assert _run(consent.record_comprehension_signal(_ctx(), c, CITES)) is False
    assert not _inserts(c)


def test_flag_on_with_consent_records_scoped_signal(monkeypatch):
    monkeypatch.setattr(settings, "seeker_comprehension_recovery_enabled", True)
    c = _container({"id": "receipt-1"})
    assert _run(consent.record_comprehension_signal(_ctx(), c, CITES)) is True
    row = _inserts(c)[0].args[0]
    assert row["consent_receipt_id"] == "receipt-1"
    assert row["user_id"] == USER
    assert row["tenant_id"] == "oneness"
    assert "I am confused" not in str(row)  # no raw question text


@pytest.mark.parametrize(
    "ctx_kw",
    [
        {"user_id": "anonymous"},
        {"user_id": "anon:abc"},
        {"incognito": True},
        {"is_benchmark": True},
    ],
)
def test_anonymous_incognito_benchmark_never_consented(monkeypatch, ctx_kw):
    monkeypatch.setattr(settings, "seeker_comprehension_recovery_enabled", True)
    c = _container({"id": "r1"})
    assert _run(consent.active_consent_receipt_id(_ctx(**ctx_kw), c)) is None
    assert _run(consent.record_comprehension_signal(_ctx(**ctx_kw), c, CITES)) is False
    assert not _inserts(c)


def test_revoked_consent_blocks_writes_and_seen_clips(monkeypatch):
    # active_consent returns None for a latest-revoked receipt (memory_outbox contract).
    monkeypatch.setattr(settings, "seeker_comprehension_recovery_enabled", True)
    c = _container(None)
    assert _run(consent.active_consent_receipt_id(_ctx(), c)) is None
    assert not _inserts(c)


def test_consent_lookup_error_fails_closed():
    class Boom:
        async def active_consent(self, **_):
            raise ConnectionError("db down")

    c = SimpleNamespace(memory_outbox=Boom())
    assert _run(consent.active_consent_receipt_id(_ctx(), c)) is None


def test_erasure_deletes_signals_and_seen_clips():
    seen_store.record_seen_clip(user_id="u1", tenant_id="oneness", clip_id="c1", video_id="v1")
    c = _container({"id": "r"})
    _run(consent.erase_seeker_signals(c, "u1", "oneness"))
    c.supabase_client.table.assert_called_with("seeker_comprehension_signals")
    assert seen_store.get_seen_clips(user_id="u1", tenant_id="oneness") == (set(), set())


def test_erasure_tables_and_sql_cascade():
    assert "seeker_comprehension_signals" in cascade_erasure.CASCADE_DELETION_ORDER
    assert "seeker_comprehension_signals" in cascade_erasure.EXTENDED_USER_TABLES
    base = (
        ROOT / "supabase/migrations/20261126000000_teaching_editorial_intelligence.sql"
    ).read_text()
    assert "user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE" in base
    new = (
        ROOT / "supabase/migrations/20261126000100_seeker_comprehension_consent_binding.sql"
    ).read_text()
    assert "REFERENCES public.memory_consent_receipts(id) ON DELETE CASCADE" in new
    assert "has_active_memory_consent(user_id, tenant_id)" in new


def test_revoke_endpoint_calls_erasure_and_bridge_gates_seen_clips():
    memory_src = (ROOT / "backend/app/api/memory.py").read_text()
    assert 'erase_seeker_signals(container, user["id"], tenant_id)' in memory_src
    bridge = (ROOT / "backend/app/pipeline/stages/first_person_bridge.py").read_text()
    assert bridge.count("active_consent_receipt_id(ctx, container)") >= 2
