"""P1-SEC-8: TestAuthStrategy must never register in production builds.

The X-Test-Key benchmark backdoor is gated on ALL THREE local-only
conditions:
  1. ENABLE_TEST_AUTH=true
  2. IS_PRODUCTION=false (or unset)
  3. BENCHMARK_SECRET is set (non-empty)

Rule 9 of the audit remediation plan: security gates in auth_service.py must
fail closed even under ``python -O``. The production gate is therefore an
explicit RuntimeError — never a bare boolean check, which CPython strips
when running optimized. A source-level scan enforces that the word "assert"
does not appear anywhere in the auth service.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import Request

_AUTH_SERVICE_PATH = Path(__file__).resolve().parents[1] / "services" / "auth_service.py"

_SENTINEL_NIL_UUID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear the lru_cache on get_settings between tests (mirrors
    test_test_auth_strategy.py)."""
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_request(headers: dict) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/health/mfa",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


def _reload_auth_module():
    import importlib

    import services.auth_service as auth_module

    importlib.reload(auth_module)
    return auth_module


class TestTestAuthRegistrationGates:
    """P1-SEC-8: the X-Test-Key backdoor must not be registered whenever any
    local-only condition fails."""

    def test_testauth_not_registered_in_prod(self):
        """IS_PRODUCTION=true never registers TestAuthStrategy, and rejects ENABLE_TEST_AUTH=true."""
        # 1. Reject enable_test_auth=true in production
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "true",
            "ANON_SESSION_HMAC_SECRET": "test-anon-secret-0123456789abcdef",
            "ENABLE_TEST_AUTH": "true",
            "BENCHMARK_SECRET": "my-secret",
        }, clear=False):
            from app.config import Settings
            with pytest.raises(ValueError, match="enable_test_auth must be False when is_production is True"):
                Settings()

        # 2. When enable_test_auth=false in production, strategy is not registered
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "true",
            "ANON_SESSION_HMAC_SECRET": "test-anon-secret-0123456789abcdef",
            "ENABLE_TEST_AUTH": "false",
            "BENCHMARK_SECRET": "my-secret",
        }, clear=False):
            from app.config import Settings

            settings = Settings()
            assert settings.is_production is True

            auth_module = _reload_auth_module()
            from services.auth_service import TestAuthStrategy

            assert not any(isinstance(s, TestAuthStrategy) for s in auth_module._strategies)

    def test_testauth_absent_without_benchmark_secret(self):
        """ENABLE_TEST_AUTH=true + non-prod but empty BENCHMARK_SECRET ->
        strategy absent."""
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "false",
            "ENABLE_TEST_AUTH": "true",
            "BENCHMARK_SECRET": "",
        }, clear=False):
            from app.config import Settings

            settings = Settings()
            assert settings.enable_test_auth is True
            assert settings.is_production is False
            assert settings.benchmark_secret == ""

            auth_module = _reload_auth_module()
            from services.auth_service import TestAuthStrategy

            assert not any(isinstance(s, TestAuthStrategy) for s in auth_module._strategies)

    def test_assert_free_security_gates(self):
        """Rule 9: auth_service.py must be free of bare boolean-check gates.

        ``assert`` statements are stripped under ``python -O``, silently
        disabling security checks in optimized runs. A word-boundary scan of
        the auth service source must come back clean.
        """
        source = _AUTH_SERVICE_PATH.read_text(encoding="utf-8")
        assert not re.search(r"\bassert\b", source), (
            "services/auth_service.py must not contain `assert` (Rule 9: it "
            "is stripped under `python -O`, silently disabling security gates)."
        )

    @pytest.mark.asyncio
    async def test_benchmark_identity_uses_nil_uuid_sentinel(self):
        """The fixed benchmark identity is the NIL UUID sentinel — a value
        Supabase GoTrue never assigns to a real user, so it cannot collide
        with a genuine account."""
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "false",
            "ENABLE_TEST_AUTH": "true",
            "BENCHMARK_SECRET": "benchmark-sentinel-check",
        }, clear=False):
            from app.config import settings

            settings.enable_test_auth = True
            settings.is_production = False
            settings.benchmark_secret = "benchmark-sentinel-check"

            auth_module = _reload_auth_module()
            strategy = auth_module.TestAuthStrategy()

            user = await strategy.authenticate(
                _make_request({"X-Test-Key": "benchmark-sentinel-check"}), None
            )
            assert user is not None
            assert user["id"] == _SENTINEL_NIL_UUID
            assert user["tenant_id"] == _SENTINEL_NIL_UUID
            assert user["is_superuser"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
