"""Regression tests for AMK-E-002 (OpenRouter 401/403 non-retry and error sanitization)."""

from unittest.mock import patch

import httpx
import pytest

from app.config import settings
from app.sanitization import sanitize_client_error
from services.openrouter_service import OpenRouterService, _is_retryable_openrouter_error


@pytest.fixture(autouse=True)
def _disable_budget_guard(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_budget_guard_enabled", False)


def test_is_retryable_openrouter_error_rejects_401_and_403():
    """401 and 403 must return False (non-retryable)."""
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    resp_401 = httpx.Response(401, request=req)
    err_401 = httpx.HTTPStatusError("401 Unauthorized", request=req, response=resp_401)
    assert _is_retryable_openrouter_error(err_401) is False

    resp_403 = httpx.Response(403, request=req)
    err_403 = httpx.HTTPStatusError("403 Forbidden", request=req, response=resp_403)
    assert _is_retryable_openrouter_error(err_403) is False


@pytest.mark.asyncio
async def test_call_api_auth_error_returns_graceful_degradation():
    """401/403 in _call_api must degrade gracefully instead of re-raising raw exception."""
    service = OpenRouterService()
    client = await service._get_http_client()
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    resp_401 = httpx.Response(401, request=req, content=b'{"error": "Invalid API key"}')
    err_401 = httpx.HTTPStatusError("401 Unauthorized", request=req, response=resp_401)

    # Patch client.post to raise 401
    with patch.object(client, "post", side_effect=err_401):
        # Must return graceful degradation string, NOT raise
        result = await service._call_api(
            messages=[{"role": "user", "content": "Hello"}],
            model=service._gen_model,
            operation="test",
        )
        assert isinstance(result, str)
        assert "experiencing" in result.lower() or "connection" in result.lower()


def test_sanitize_client_error_masks_raw_exceptions():
    """Raw exceptions, status codes, and secret traces must be sanitized for clients."""
    raw_error = "httpx.HTTPStatusError: 401 Unauthorized for url 'https://openrouter.ai/api/v1/chat/completions' with key sk-or-v1-abcdef"
    safe = sanitize_client_error(raw_error)
    assert "sk-or-v1" not in safe
    assert "openrouter.ai" not in safe
    assert "HTTPStatusError" not in safe
    assert "An error occurred" in safe or "Please try again" in safe
