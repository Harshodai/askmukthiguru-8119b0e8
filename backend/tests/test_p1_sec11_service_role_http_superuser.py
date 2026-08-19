"""P1-SEC-11: service_role JWTs presented over HTTP never yield superuser.

P1-SEC-1 (T2) already made the ``SupabaseAuthStrategy`` service_role branch
return ``is_superuser=False`` for inbound HTTP tokens; the P1-SEC-1 suite
pins that structurally (test_p1_sec1_admin_aal2.py) and via route-level 403s
on admin/ingest/kg endpoints. This module adds the missing DIRECT unit test:
an actual forged service_role JWT decoded by the strategy must produce an
identity dict with ``is_superuser=False`` and ``role="service_role"``.

Sink verification: the telemetry sink reads ``SUPABASE_SERVICE_ROLE_KEY``
from the environment directly (backend/app/telemetry_sink.py:
``os.environ.get("SUPABASE_SERVICE_ROLE_KEY", settings.supabase_key)``) and
never routes through SupabaseAuthStrategy, so the non-superuser change does
not affect it — already asserted by
``test_telemetry_sink_does_not_use_auth_bridge``.
"""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials

from app.config import settings
from services.auth_service import SupabaseAuthStrategy

_SENTINEL_SUB = "00000000-0000-0000-0000-000000000002"


def _forge_service_role_token() -> str:
    import services.auth_service as auth_svc

    payload = {
        "sub": _SENTINEL_SUB,
        "email": None,
        "role": "service_role",
        "aud": auth_svc.settings.supabase_jwt_audience,
        "iss": f"{auth_svc.settings.supabase_url.rstrip('/')}/auth/v1",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, auth_svc.settings.jwt_secret, algorithm="HS256")


def _make_request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/health",
        "headers": [],
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _pin_jwt_secret(monkeypatch):
    import services.auth_service as auth_svc

    monkeypatch.setattr(auth_svc.settings, "jwt_secret", "mock_jwt_secret_for_testing_12345")
    monkeypatch.setattr(settings, "jwt_secret", "mock_jwt_secret_for_testing_12345")
    yield


class TestSec11ServiceRoleHttpNeverSuperuser:
    @pytest.mark.asyncio
    async def test_sec11_service_role_jwt_never_superuser(self, monkeypatch):
        """A forged service_role JWT decoded by the strategy yields
        is_superuser=False and role='service_role' — never superuser."""

        async def _no_admin(self, user_id, token=None):
            return False

        monkeypatch.setattr(SupabaseAuthStrategy, "_check_admin_role", _no_admin)
        strategy = SupabaseAuthStrategy()
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=_forge_service_role_token()
        )
        user = await strategy.authenticate(_make_request(), creds)
        assert user is not None, "service_role token must still authenticate"
        assert user["role"] == "service_role"
        assert user["is_superuser"] is False, (
            "service_role over HTTP must never be superuser (P1-SEC-11)"
        )
        assert user["provider"] == "supabase"
        assert user["id"] == _SENTINEL_SUB

    def test_sec11_sink_reads_service_role_key_from_env_directly(self):
        """Telemetry sink must read SUPABASE_SERVICE_ROLE_KEY from env, not
        via the auth bridge — otherwise the non-superuser change would break
        telemetry writes."""
        import inspect

        import app.telemetry_sink as ts

        src = inspect.getsource(ts)
        assert "SUPABASE_SERVICE_ROLE_KEY" in src, (
            "telemetry sink must read service_role key from env directly"
        )
        assert "auth_service" not in src, "telemetry sink must not import the auth bridge"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
