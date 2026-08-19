"""Tests for the require_aal2 MFA step-up dependency and /api/health/mfa probe.

These tests verify:
  - an authenticated user with aal='aal1' is rejected with 403
  - an authenticated user with aal='aal2' is accepted with 200
  - an unauthenticated caller is rejected

Route-level behavior is exercised deterministically by overriding the auth
bridge dependency (FastAPI's idiomatic seam for route tests); the X-Test-Key /
X-Test-Aal benchmark backdoor itself is covered at the strategy level with a
scoped Request, mirroring test_test_auth_strategy.py.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from services.auth_service import (
    TestAuthStrategy,
    get_current_user_from_supabase,
    require_aal2,
)

client = TestClient(app)

_TEST_KEY = settings.benchmark_secret
_NO_BACKDOOR = not _TEST_KEY


def _make_request(headers: dict) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/health/mfa",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


class TestRequireAal2Dependency:
    """Direct unit tests for the require_aal2 dependency function."""

    @pytest.mark.asyncio
    async def test_unauthenticated_user_raises_401(self):
        """No user -> 401 Authentication required."""
        with pytest.raises(HTTPException) as exc_info:
            await require_aal2(user=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_aal1_user_raises_403(self):
        """User with aal='aal1' -> 403 AAL2 step-up required."""
        with pytest.raises(HTTPException) as exc_info:
            await require_aal2(user={"id": "u1", "aal": "aal1"})
        assert exc_info.value.status_code == 403
        assert "AAL2" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_aal_defaults_to_rejection(self):
        """User without an aal claim must be denied (deny by default)."""
        with pytest.raises(HTTPException) as exc_info:
            await require_aal2(user={"id": "u1"})
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_aal2_user_returns_user(self):
        """User with aal='aal2' is returned unchanged."""
        user = {"id": "u2", "aal": "aal2"}
        assert await require_aal2(user=user) == user

    @pytest.mark.asyncio
    async def test_aal2_accepted_as_object_attribute(self):
        """require_aal2 also works when user is a dataclass-like object."""
        from types import SimpleNamespace

        result = await require_aal2(user=SimpleNamespace(aal="aal2", id="u3"))
        assert result.aal == "aal2"
        assert result.id == "u3"


class TestTestAuthStrategyAal:
    """Unit tests for the X-Test-Aal header on the benchmark backdoor."""

    @pytest.mark.skipif(
        _NO_BACKDOOR, reason="BENCHMARK_SECRET not set - test auth backdoor unavailable"
    )
    @pytest.mark.asyncio
    async def test_authenticate_defaults_to_aal1(self):
        """X-Test-Key without X-Test-Aal -> aal1 identity."""
        strategy = TestAuthStrategy()
        user = await strategy.authenticate(_make_request({"X-Test-Key": _TEST_KEY}), None)
        assert user is not None
        assert user["aal"] == "aal1"

    @pytest.mark.skipif(
        _NO_BACKDOOR, reason="BENCHMARK_SECRET not set - test auth backdoor unavailable"
    )
    @pytest.mark.asyncio
    async def test_authenticate_accepts_aal2(self):
        """X-Test-Aal: aal2 -> aal2 identity."""
        strategy = TestAuthStrategy()
        user = await strategy.authenticate(
            _make_request({"X-Test-Key": _TEST_KEY, "X-Test-Aal": "aal2"}), None
        )
        assert user is not None
        assert user["aal"] == "aal2"

    @pytest.mark.skipif(
        _NO_BACKDOOR, reason="BENCHMARK_SECRET not set - test auth backdoor unavailable"
    )
    @pytest.mark.asyncio
    async def test_authenticate_ignores_invalid_aal(self):
        """Unsupported X-Test-Aal values fall back to aal1."""
        strategy = TestAuthStrategy()
        user = await strategy.authenticate(
            _make_request({"X-Test-Key": _TEST_KEY, "X-Test-Aal": "aal3"}), None
        )
        assert user is not None
        assert user["aal"] == "aal1"


class TestHealthMfaRoute:
    """Integration tests for the /api/health/mfa probe route."""

    def _override_user(self, user: dict | None):
        """Override the auth bridge dependency for the duration of a request."""
        if user is None:

            async def no_user():
                raise HTTPException(status_code=401, detail="Authentication required")

            app.dependency_overrides[get_current_user_from_supabase] = no_user
        else:

            async def fixed_user():
                return user

            app.dependency_overrides[get_current_user_from_supabase] = fixed_user

    def test_route_rejects_aal1_with_403(self):
        """An authenticated aal1 identity must be rejected."""
        self._override_user({"id": "u1", "aal": "aal1"})
        try:
            response = client.get("/api/health/mfa")
            assert response.status_code == 403, response.text
            assert "AAL2" in response.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_current_user_from_supabase, None)

    def test_route_accepts_aal2_with_200(self):
        """An authenticated aal2 identity must be accepted."""
        self._override_user({"id": "u2", "aal": "aal2"})
        try:
            response = client.get("/api/health/mfa")
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["ok"] is True
            assert data["aal"] == "aal2"
        finally:
            app.dependency_overrides.pop(get_current_user_from_supabase, None)

    def test_route_rejects_absent_aal_with_403(self):
        """A user without an aal claim is denied by default."""
        self._override_user({"id": "u3"})
        try:
            response = client.get("/api/health/mfa")
            assert response.status_code == 403, response.text
        finally:
            app.dependency_overrides.pop(get_current_user_from_supabase, None)

    def test_route_rejects_anonymous_without_auth(self):
        """No authenticated user -> 401 (never 200)."""
        self._override_user(None)
        try:
            response = client.get("/api/health/mfa")
            assert response.status_code == 401, response.text
        finally:
            app.dependency_overrides.pop(get_current_user_from_supabase, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
