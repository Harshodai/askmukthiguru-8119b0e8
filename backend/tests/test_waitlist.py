"""Focused safety tests for consent-required waitlist intake."""
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
async def test_waitlist_is_closed_by_default(monkeypatch):
    monkeypatch.setattr(settings, "waitlist_enabled", False)

    with pytest.raises(HTTPException) as exc:
        await _call(WaitlistSignup(email="seeker@example.com", consent_to_contact=True), SimpleNamespace())

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_waitlist_requires_explicit_contact_consent(monkeypatch):
    monkeypatch.setattr(settings, "waitlist_enabled", True)

    with pytest.raises(HTTPException) as exc:
        await _call(WaitlistSignup(email="seeker@example.com", consent_to_contact=False), SimpleNamespace(supabase_client=MagicMock()))

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_waitlist_upserts_normalized_email_without_disclosure(monkeypatch):
    monkeypatch.setattr(settings, "waitlist_enabled", True)
    supabase = MagicMock()
    container = SimpleNamespace(supabase_client=supabase)

    result = await _call(
        WaitlistSignup(email="Seeker@Example.com", name=" Seeker ", consent_to_contact=True),
        container,
    )

    assert result.status == "accepted"
    table = supabase.table.return_value
    table.upsert.assert_called_once_with(
        {"email": "seeker@example.com", "name": "Seeker", "source": "website"},
        on_conflict="email_key",
    )
    table.upsert.return_value.execute.assert_called_once()
