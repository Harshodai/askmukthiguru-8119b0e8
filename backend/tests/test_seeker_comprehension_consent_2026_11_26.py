"""Seeker comprehension signals and seen-clip reads are consent-gated (audit finding 13)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from postgrest.exceptions import APIError

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


def _real_outbox_container(exc):
    """Real MemoryOutbox.active_consent code path over a client whose query raises ``exc``."""
    from services.memory_outbox import MemoryOutbox

    client = MagicMock()
    query = client.table.return_value.select.return_value
    query.eq.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.side_effect = exc
    return SimpleNamespace(
        memory_outbox=MemoryOutbox(supabase_client=client), supabase_client=client
    )


LOOKUP_ERRORS = [
    APIError({"message": "boom", "code": "500", "hint": None, "details": None}),
    httpx.ConnectError("down"),
    ConnectionError("down"),
]


@pytest.mark.parametrize("exc", LOOKUP_ERRORS, ids=lambda e: type(e).__name__)
def test_real_outbox_lookup_failure_is_no_consent_and_no_write(monkeypatch, exc):
    monkeypatch.setattr(settings, "seeker_comprehension_recovery_enabled", True)
    c = _real_outbox_container(exc)
    assert _run(consent.active_consent_receipt_id(_ctx(), c)) is None
    assert _run(consent.record_comprehension_signal(_ctx(), c, CITES)) is False
    c.supabase_client.table.return_value.insert.assert_not_called()


def _api_error(code):
    return APIError({"message": "x", "code": code, "hint": None, "details": None})


def test_erasure_missing_table_is_zero_rows():
    c = _container({"id": "r"})
    c.supabase_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.side_effect = _api_error(
        "PGRST205"
    )
    _run(consent.erase_seeker_signals(c, "u1", "oneness"))  # does not raise


def test_erasure_other_errors_still_raise():
    c = _container({"id": "r"})
    c.supabase_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.side_effect = _api_error(
        "500"
    )
    with pytest.raises(APIError):
        _run(consent.erase_seeker_signals(c, "u1", "oneness"))


def test_erasure_raises_when_seen_clip_cleanup_fails(monkeypatch):
    monkeypatch.setattr(consent, "clear_seen_clips", lambda *a, **k: False)
    with pytest.raises(RuntimeError):
        _run(consent.erase_seeker_signals(_container({"id": "r"}), "u1", "oneness"))


def test_seen_clip_keys_match_account_erasure_redis_pattern():
    # cascade_erasure purges redis keys matching f"*{user_id}*".
    assert USER in seen_store._clip_key("oneness", USER)
    assert USER in seen_store._video_key("oneness", USER)


def test_revocation_deletes_signals_scoped_to_user_and_tenant():
    c = _container(None)
    _run(consent.erase_seeker_signals(c, USER, "oneness"))
    delete = c.supabase_client.table.return_value.delete
    delete.assert_called_once()
    eqs = delete.return_value.eq
    eqs.assert_called_once_with("user_id", USER)
    eqs.return_value.eq.assert_called_once_with("tenant_id", "oneness")


# --- bridge-level behaviour -------------------------------------------------


@pytest.fixture
def bridge_env(monkeypatch):
    from app.pipeline.stages import first_person_bridge as bridge
    from tests import test_first_person_bridge as tb

    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    monkeypatch.setattr(settings, "memory_write", False)
    monkeypatch.setattr(
        bridge,
        "source_is_authoritatively_licensed",
        lambda **kw: kw.get("domain_rights_status") == "licensed",
    )
    pipeline = MagicMock()
    pipeline.execute = MagicMock(return_value=tb._fp_result())
    monkeypatch.setattr(bridge, "_fp_pipeline", lambda container: pipeline)
    return bridge, tb


async def _serve(bridge, tb, container):
    ctx = tb._ctx(container)
    ctx.user_id = USER
    ctx.user_msg = "I am confused, explain differently"
    ctx.state["user_msg_en"] = ctx.user_msg
    ctx.start_time = time.time()
    return await bridge.FirstPersonBridgeStage().run(ctx)


def test_bridge_flags_off_zero_consent_lookups_and_unchanged_answer(bridge_env, monkeypatch):
    bridge, tb = bridge_env
    monkeypatch.setattr(settings, "seeker_comprehension_recovery_enabled", False)
    monkeypatch.setattr(settings, "first_person_server_seen_clips_enabled", False)
    container = tb._container()
    outbox = MagicMock()
    outbox.active_consent = MagicMock(side_effect=AssertionError("consent looked up"))
    container.memory_outbox = outbox
    result = _run(_serve(bridge, tb, container))
    assert result.final_answer == tb._ANSWER
    outbox.active_consent.assert_not_called()


@pytest.mark.parametrize("exc", LOOKUP_ERRORS, ids=lambda e: type(e).__name__)
def test_bridge_consent_lookup_failure_leaves_answer_unchanged(bridge_env, monkeypatch, exc):
    bridge, tb = bridge_env
    monkeypatch.setattr(settings, "seeker_comprehension_recovery_enabled", True)
    monkeypatch.setattr(settings, "first_person_server_seen_clips_enabled", True)
    real = _real_outbox_container(exc)
    container = tb._container()
    container.memory_outbox = real.memory_outbox
    container.supabase_client = real.supabase_client
    container.redis_client = None
    result = _run(_serve(bridge, tb, container))
    assert result.final_answer == tb._ANSWER
    real.supabase_client.table.return_value.insert.assert_not_called()
