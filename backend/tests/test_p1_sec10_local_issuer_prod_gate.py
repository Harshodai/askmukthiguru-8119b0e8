"""P1-SEC-10: local Supabase JWT issuers are only accepted outside production.

The ``SupabaseAuthStrategy`` issuer allowlist used to include
``http://127.0.0.1:54321/auth/v1`` and ``http://localhost:54321/auth/v1``
unconditionally. A forged token claiming a local issuer would have been
trusted in production whenever the HS256 shared-secret path was reachable
(e.g. a leaked ``JWT_SECRET``). The local issuers are now gated on
``is_production=False``.

Covered here (forged HS256 tokens decoded by the real strategy):
  - test_sec10_local_issuer_rejected_in_prod: a token with a local issuer
    fails authentication when is_production=True.
  - test_sec10_local_issuer_accepted_in_dev: the same token authenticates
    outside production (regression guard for local dev).
  - test_sec10_prod_base_issuer_still_accepted: the configured Supabase base
    issuer continues to authenticate in production (no over-gating).
"""
from __future__ import annotations

import time

import jwt
import pytest
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials

from app.config import settings
from services.auth_service import SupabaseAuthStrategy

LOCAL_ISSUER = "http://127.0.0.1:54321/auth/v1"
_SENTINEL_SUB = "00000000-0000-0000-0000-000000000001"


def _forge_hs256_token(issuer: str) -> str:
    import services.auth_service as auth_svc
    payload = {
        "sub": _SENTINEL_SUB,
        "email": "tester@example.com",
        "role": "authenticated",
        "aud": auth_svc.settings.supabase_jwt_audience,
        "iss": issuer,
        "aal": "aal1",
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
    """Pin a known signing secret so forged tokens verify against the same
    secret the strategy reads at call time (settings.jwt_secret)."""
    import services.auth_service as auth_svc
    monkeypatch.setattr(auth_svc.settings, "jwt_secret", "mock_jwt_secret_for_testing_12345")
    monkeypatch.setattr(settings, "jwt_secret", "mock_jwt_secret_for_testing_12345")
    yield


async def _no_admin_role(self, user_id: str, jwt_token: str | None = None) -> bool:
    return False


class TestSec10LocalIssuerProdGate:
    @pytest.mark.asyncio
    async def test_sec10_local_issuer_rejected_in_prod(self, monkeypatch):
        import services.auth_service as auth_svc
        monkeypatch.setattr(auth_svc.settings, "is_production", True)
        monkeypatch.setattr(settings, "is_production", True)
        monkeypatch.setattr(SupabaseAuthStrategy, "_check_admin_role", _no_admin_role)
        strategy = SupabaseAuthStrategy()
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=_forge_hs256_token(LOCAL_ISSUER)
        )
        user = await strategy.authenticate(_make_request(), creds)
        assert user is None, (
            "a forged token with a local issuer must be rejected in production"
        )

    @pytest.mark.asyncio
    async def test_sec10_local_issuer_accepted_in_dev(self, monkeypatch):
        import services.auth_service as auth_svc
        monkeypatch.setattr(auth_svc.settings, "is_production", False)
        monkeypatch.setattr(settings, "is_production", False)
        monkeypatch.setattr(SupabaseAuthStrategy, "_check_admin_role", _no_admin_role)
        strategy = SupabaseAuthStrategy()
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=_forge_hs256_token(LOCAL_ISSUER)
        )
        user = await strategy.authenticate(_make_request(), creds)
        assert user is not None, "local issuer must still authenticate in dev"
        assert user["id"] == "00000000-0000-0000-0000-000000000001"

    @pytest.mark.asyncio
    async def test_sec10_localhost_issuer_also_gated_in_prod(self, monkeypatch):
        import services.auth_service as auth_svc
        monkeypatch.setattr(auth_svc.settings, "is_production", True)
        monkeypatch.setattr(settings, "is_production", True)
        monkeypatch.setattr(SupabaseAuthStrategy, "_check_admin_role", _no_admin_role)
        strategy = SupabaseAuthStrategy()
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=_forge_hs256_token("http://localhost:54321/auth/v1"),
        )
        user = await strategy.authenticate(_make_request(), creds)
        assert user is None, "localhost issuer must also be rejected in production"

    @pytest.mark.asyncio
    async def test_sec10_prod_base_issuer_still_accepted(self, monkeypatch):
        import services.auth_service as auth_svc
        monkeypatch.setattr(auth_svc.settings, "is_production", True)
        monkeypatch.setattr(settings, "is_production", True)
        monkeypatch.setattr(SupabaseAuthStrategy, "_check_admin_role", _no_admin_role)
        strategy = SupabaseAuthStrategy()
        base = settings.supabase_url.rstrip("/")
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=_forge_hs256_token(f"{base}/auth/v1")
        )
        user = await strategy.authenticate(_make_request(), creds)
        assert user is not None, "the configured base issuer must still work in prod"
        assert user["id"] == "00000000-0000-0000-0000-000000000001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
