"""Tests for TestAuthStrategy registration and authentication behavior.

These tests verify that the benchmark auth backdoor (X-Test-Key) is only active
when ALL THREE conditions are met:
1. IS_PRODUCTION=false (or unset)
2. ENABLE_TEST_AUTH=true
3. BENCHMARK_SECRET is set (non-empty)

The X-Test-Key value must match BENCHMARK_SECRET.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi import Request


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear the lru_cache on get_settings between tests."""
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_request(headers: dict) -> Request:
    """Create a mock FastAPI Request with given headers."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/chat",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


class TestTestAuthStrategyRegistration:
    """Test that TestAuthStrategy is registered only under correct conditions."""

    def test_not_registered_by_default(self):
        """Default config (ENABLE_TEST_AUTH=false) → strategy NOT registered."""
        with patch.dict(os.environ, {
            "ENABLE_TEST_AUTH": "false",
            "IS_PRODUCTION": "true",
            "BENCHMARK_SECRET": "",
        }, clear=False):
            from app.config import Settings
            settings = Settings()
            assert settings.enable_test_auth is False
            assert settings.is_production is True
            assert settings.benchmark_secret == ""

            import importlib

            import services.auth_service as auth_module
            importlib.reload(auth_module)

            # Should NOT have TestAuthStrategy
            from services.auth_service import TestAuthStrategy
            assert not any(isinstance(s, TestAuthStrategy) for s in auth_module._strategies)

    def test_not_registered_when_enable_true_but_no_secret(self):
        """ENABLE_TEST_AUTH=true but BENCHMARK_SECRET unset → strategy NOT registered."""
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

            import importlib

            import services.auth_service as auth_module
            importlib.reload(auth_module)

            from services.auth_service import TestAuthStrategy
            assert not any(isinstance(s, TestAuthStrategy) for s in auth_module._strategies)

    def test_not_registered_when_production_true(self):
        """IS_PRODUCTION=true → strategy NOT registered even with secret."""
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "true",
            "ENABLE_TEST_AUTH": "true",
            "BENCHMARK_SECRET": "my-secret",
        }, clear=False):
            from app.config import Settings
            settings = Settings()
            assert settings.is_production is True

            import importlib

            import services.auth_service as auth_module
            importlib.reload(auth_module)

            from services.auth_service import TestAuthStrategy
            assert not any(isinstance(s, TestAuthStrategy) for s in auth_module._strategies)

    def test_registered_when_all_conditions_met(self):
        """All three conditions met → strategy IS registered."""
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "false",
            "ENABLE_TEST_AUTH": "true",
            "BENCHMARK_SECRET": "my-benchmark-secret",
        }, clear=False):
            from app.config import Settings
            settings = Settings()
            assert settings.enable_test_auth is True
            assert settings.is_production is False
            assert settings.benchmark_secret == "my-benchmark-secret"

            import importlib

            import services.auth_service as auth_module
            importlib.reload(auth_module)

            from services.auth_service import TestAuthStrategy
            assert any(isinstance(s, TestAuthStrategy) for s in auth_module._strategies)


class TestTestAuthStrategyAuthentication:
    """Test the authenticate method of TestAuthStrategy."""

    @pytest.mark.asyncio
    async def test_authenticate_with_matching_secret(self):
        """Correct X-Test-Key matching BENCHMARK_SECRET → returns user dict."""
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "false",
            "ENABLE_TEST_AUTH": "true",
            "BENCHMARK_SECRET": "my-secret",
        }, clear=False):
            import importlib

            import services.auth_service as auth_module
            importlib.reload(auth_module)

            from services.auth_service import TestAuthStrategy
            strategy = TestAuthStrategy()

            request = _make_request({"X-Test-Key": "my-secret"})
            result = await strategy.authenticate(request, None)

            assert result is not None
            assert result["id"] == "00000000-0000-0000-0000-000000000000"
            assert result["email"] == "benchmark-admin@mukthi.guru"
            assert result["is_superuser"] is True
            assert result["provider"] == "test"

    @pytest.mark.asyncio
    async def test_authenticate_with_wrong_secret(self):
        """Wrong X-Test-Key → returns None (401)."""
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "false",
            "ENABLE_TEST_AUTH": "true",
            "BENCHMARK_SECRET": "correct-secret",
        }, clear=False):
            import importlib

            import services.auth_service as auth_module
            importlib.reload(auth_module)

            from services.auth_service import TestAuthStrategy
            strategy = TestAuthStrategy()

            request = _make_request({"X-Test-Key": "wrong-secret"})
            result = await strategy.authenticate(request, None)

            assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_without_header(self):
        """No X-Test-Key header → returns None."""
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "false",
            "ENABLE_TEST_AUTH": "true",
            "BENCHMARK_SECRET": "my-secret",
        }, clear=False):
            import importlib

            import services.auth_service as auth_module
            importlib.reload(auth_module)

            from services.auth_service import TestAuthStrategy
            strategy = TestAuthStrategy()

            request = _make_request({})
            result = await strategy.authenticate(request, None)

            assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_empty_secret(self):
        """Empty BENCHMARK_SECRET → returns None even with header."""
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "false",
            "ENABLE_TEST_AUTH": "true",
            "BENCHMARK_SECRET": "",
        }, clear=False):
            import importlib

            import services.auth_service as auth_module
            importlib.reload(auth_module)

            from services.auth_service import TestAuthStrategy
            strategy = TestAuthStrategy()

            request = _make_request({"X-Test-Key": "anything"})
            result = await strategy.authenticate(request, None)

            assert result is None


class TestAuthBridgeIntegration:
    """Integration test for the full AuthBridge with TestAuthStrategy."""

    @pytest.mark.asyncio
    async def test_auth_bridge_returns_401_when_not_registered(self):
        """When strategy not registered, X-Test-Key should result in 401."""
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "true",
            "ENABLE_TEST_AUTH": "false",
        }, clear=False):
            import importlib

            import services.auth_service as auth_module
            importlib.reload(auth_module)

            from services.auth_service import auth_bridge

            request = _make_request({"X-Test-Key": "any-secret"})

            # Should raise 401 because TestAuthStrategy is not registered
            # and no other strategy will authenticate X-Test-Key
            with pytest.raises(Exception) as exc_info:
                await auth_bridge.get_user(request, None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_auth_bridge_authenticates_when_registered(self):
        """When strategy registered with secret, correct key authenticates."""
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "false",
            "ENABLE_TEST_AUTH": "true",
            "BENCHMARK_SECRET": "test-secret-123",
        }, clear=False):
            import importlib

            import services.auth_service as auth_module
            importlib.reload(auth_module)

            from services.auth_service import auth_bridge

            request = _make_request({"X-Test-Key": "test-secret-123"})
            user = await auth_bridge.get_user(request, None)

            assert user["id"] == "00000000-0000-0000-0000-000000000000"
            assert user["is_superuser"] is True
            assert user["provider"] == "test"

    @pytest.mark.asyncio
    async def test_auth_bridge_rejects_wrong_key_when_registered(self):
        """When strategy registered, wrong key → 401."""
        with patch.dict(os.environ, {
            "IS_PRODUCTION": "false",
            "ENABLE_TEST_AUTH": "true",
            "BENCHMARK_SECRET": "correct-secret",
        }, clear=False):
            import importlib

            import services.auth_service as auth_module
            importlib.reload(auth_module)

            from services.auth_service import auth_bridge

            request = _make_request({"X-Test-Key": "wrong-secret"})

            with pytest.raises(Exception) as exc_info:
                await auth_bridge.get_user(request, None)
            assert exc_info.value.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])