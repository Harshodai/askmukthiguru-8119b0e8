"""Regression coverage for OH-P1-08: the email-domain allowlist
(src/integrations/supabase/client.ts's ALLOWED_EMAIL_DOMAINS) was enforced
client-only — a caller hitting the API directly, never loading AuthPage.tsx,
could authenticate with any email domain. get_optional_user() now enforces
the same declared policy server-side.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services.auth_service import get_optional_user


async def _call_with_user(user: dict) -> dict:
    with patch("services.auth_service.auth_bridge.get_user", new=AsyncMock(return_value=user)):
        return await get_optional_user(request=None, token="fake-token")


@pytest.mark.asyncio
async def test_rejects_authenticated_user_with_disallowed_email_domain():
    user = {"id": "u1", "email": "seeker@example.com", "is_anonymous": False}
    with pytest.raises(HTTPException) as exc_info:
        await _call_with_user(user)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_allows_authenticated_user_with_allowlisted_email_domain():
    user = {"id": "u1", "email": "seeker@gmail.com", "is_anonymous": False}
    result = await _call_with_user(user)
    assert result == user


@pytest.mark.asyncio
async def test_allows_anonymous_user_regardless_of_email():
    user = {"id": "anonymous", "email": None, "is_anonymous": True}
    result = await _call_with_user(user)
    assert result == user


@pytest.mark.asyncio
async def test_allows_superuser_regardless_of_email_domain():
    """The synthetic benchmark identity (benchmark-admin@mukthi.guru,
    is_superuser=True) must not be locked out by this gate."""
    user = {
        "id": "00000000-0000-0000-0000-000000000000",
        "email": "benchmark-admin@mukthi.guru",
        "is_superuser": True,
        "is_anonymous": False,
    }
    result = await _call_with_user(user)
    assert result == user


@pytest.mark.asyncio
async def test_allows_service_role_regardless_of_email_domain():
    user = {"id": "svc", "email": "svc@internal.example", "role": "service_role", "is_anonymous": False}
    result = await _call_with_user(user)
    assert result == user


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
