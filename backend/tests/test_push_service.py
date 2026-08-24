"""Regression coverage for OH-P1-02: push must not report a false success when
a platform's credentials are unconfigured, and stale/unregistered tokens must
be pruned rather than replayed forever.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.push_service import PushService


def _devices_supabase_mock(rows: list[dict]) -> MagicMock:
    supabase = MagicMock()
    execute_result = MagicMock()
    execute_result.data = rows
    supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        execute_result
    )
    return supabase


@pytest.mark.asyncio
async def test_send_reports_not_ok_when_android_credentials_missing():
    supabase = _devices_supabase_mock(
        [{"id": "d1", "platform": "android", "token": "tok-android", "active": True}]
    )
    service = PushService(supabase_client=supabase)

    with patch("services.push_service._ensure_firebase", return_value=False):
        result = await service.send(None, "title", "body", None, None)

    assert result["ok"] is False
    assert result["sent"] == 0
    assert any("firebase credentials not configured" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_send_ok_true_when_no_active_devices():
    supabase = _devices_supabase_mock([])
    service = PushService(supabase_client=supabase)
    result = await service.send(None, "title", "body", None, None)
    assert result["ok"] is True
    assert result["sent"] == 0


@pytest.mark.asyncio
async def test_send_deactivates_unregistered_fcm_tokens():
    supabase = _devices_supabase_mock(
        [{"id": "d1", "platform": "android", "token": "dead-token", "active": True}]
    )
    service = PushService(supabase_client=supabase)

    fake_response = MagicMock(
        success_count=0,
        failure_count=1,
        responses=[MagicMock(success=False, exception=MagicMock(code="UNREGISTERED"))],
    )
    # firebase-admin is an optional/lazy dependency not installed in this test
    # environment (`_send_fcm` does `from firebase_admin import messaging`
    # inside its try block) — inject a fake module rather than requiring the
    # real package just to exercise the stale-token branch.
    fake_messaging = MagicMock()
    fake_messaging.send_each_for_multicast = MagicMock(return_value=fake_response)
    fake_firebase_admin = MagicMock(messaging=fake_messaging)

    with (
        patch("services.push_service._ensure_firebase", return_value=True),
        patch.dict(
            sys.modules,
            {"firebase_admin": fake_firebase_admin, "firebase_admin.messaging": fake_messaging},
        ),
        patch.object(service, "_deactivate_devices", new=AsyncMock()) as deactivate,
    ):
        result = await service.send(None, "title", "body", None, None)

    deactivate.assert_awaited_once_with(["d1"])
    assert result["failed"] == 1


@pytest.mark.asyncio
async def test_unregister_device_scopes_to_user_id():
    supabase = MagicMock()
    execute_result = MagicMock()
    execute_result.data = [{"id": "d1"}]
    chain = supabase.table.return_value.update.return_value.eq.return_value.eq.return_value
    chain.execute.return_value = execute_result

    service = PushService(supabase_client=supabase)
    ok = await service.unregister_device("some-token", "user-123")

    assert ok is True
    supabase.table.return_value.update.assert_called_with({"active": False})


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
