"""The backend waitlist route is retired: launch signup has exactly one path.

The only consented signup is the `subscribe_launch_updates` RPC (consent flag, source allowlist,
throttles, erase and retention all live in the database). The old route upserted without
`consent_to_contact` and with an off-allowlist source, so every write failed. It now answers 410
in every state and never touches Supabase.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.waitlist import WaitlistSignup, signup_waitlist
from app.config import settings


async def _call(payload, container):
    handler = getattr(signup_waitlist, "__wrapped__", signup_waitlist)
    return await handler(MagicMock(), payload, container)


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("consent", [False, True])
async def test_waitlist_route_is_gone_and_never_writes(monkeypatch, enabled, consent):
    monkeypatch.setattr(settings, "waitlist_enabled", enabled)
    supabase = MagicMock()

    with pytest.raises(HTTPException) as exc:
        await _call(
            WaitlistSignup(email="seeker@example.com", consent_to_contact=consent),
            SimpleNamespace(supabase_client=supabase),
        )

    assert exc.value.status_code == 410
    supabase.table.assert_not_called()
