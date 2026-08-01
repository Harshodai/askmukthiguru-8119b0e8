"""Persona updated_at freshness: persona_store.py plumbing + the staleness gate.

Regression coverage for: get_persona/save_persona now round-trip a real
updated_at instead of always returning "" (GET /memory/persona previously
hardcoded an empty timestamp), and prepare_user_memory now skips injecting
a persona older than settings.persona_max_age_days.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("PERSONA_ENCRYPTION_SECRET", "a" * 32)

import pytest

from app.orchestrator_utils import _is_persona_fresh
from services.layered_memory.persona_store import encrypt, get_persona, save_persona


def _mock_supabase(select_data: dict | None) -> MagicMock:
    """A supabase client whose select().eq().eq().maybe_single().execute() and
    upsert().execute() chains are awaitable and return canned responses."""
    client = MagicMock()
    table = client.table.return_value

    select_execute = table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute
    select_execute.side_effect = AsyncMock(return_value=MagicMock(data=select_data))

    upsert_execute = table.upsert.return_value.execute
    upsert_execute.side_effect = AsyncMock(return_value=MagicMock())

    return client


@pytest.mark.asyncio
async def test_get_persona_returns_content_and_updated_at():
    encrypted = encrypt("# Persona\nLikes meditation.", "user-1")
    supabase = _mock_supabase({"content": encrypted, "updated_at": "2026-07-01T00:00:00+00:00"})

    content, updated_at = await get_persona(supabase, "user-1")

    assert content == "# Persona\nLikes meditation."
    assert updated_at == "2026-07-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_get_persona_returns_none_none_on_miss():
    supabase = _mock_supabase(None)

    content, updated_at = await get_persona(supabase, "user-1")

    assert (content, updated_at) == (None, None)


@pytest.mark.asyncio
async def test_save_persona_sets_updated_at_in_payload():
    supabase = _mock_supabase(None)

    ok = await save_persona(supabase, "user-1", "# Persona\nCalm and steady.")

    assert ok is True
    payload = supabase.table.return_value.upsert.call_args[0][0]
    assert "updated_at" in payload
    # Must parse as a real timestamp, not a placeholder.
    datetime.fromisoformat(payload["updated_at"])


def test_is_persona_fresh_within_window():
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert _is_persona_fresh(recent, max_age_days=30) is True


def test_is_persona_fresh_rejects_stale():
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    assert _is_persona_fresh(old, max_age_days=30) is False


def test_is_persona_fresh_treats_missing_as_fresh():
    assert _is_persona_fresh(None, max_age_days=30) is True


def test_is_persona_fresh_treats_malformed_as_fresh():
    assert _is_persona_fresh("not-a-timestamp", max_age_days=30) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
