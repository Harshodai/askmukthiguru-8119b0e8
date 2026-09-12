"""Resilience and failure-injection tests for OpenRouter service.

Covers B19 failure matrix:
1. Malformed JSON payload from provider -> graceful degradation
2. 503 / upstream server error with fallback model recovery
3. Connection / timeout failure handling
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch
import pytest
import httpx

from app.config import settings
from services.openrouter_service import OpenRouterService


@pytest.fixture(autouse=True)
def _disable_budget_guard(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_budget_guard_enabled", False)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-api-key")
    monkeypatch.setattr(settings, "openrouter_enforce_model_policy", False)
    monkeypatch.setattr(settings, "llm_max_retries", 1)


class FakeMalformedResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")

    @property
    def text(self):
        return "malformed non-json response body"


class Fake503Response:
    status_code = 503

    def raise_for_status(self):
        req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        resp = httpx.Response(503, request=req)
        raise httpx.HTTPStatusError("503 Service Unavailable", request=req, response=resp)

    def json(self):
        return {"error": {"message": "Service unavailable"}}


class FakeSuccessResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"message": {"content": "Wisdom from the fallback model."}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 10},
        }


@pytest.mark.asyncio
async def test_openrouter_malformed_json_degrades_gracefully(monkeypatch):
    """When the provider returns invalid JSON, generate() should return graceful degradation."""
    class FakeMalformedClient:
        async def post(self, url, json=None, **kwargs):
            return FakeMalformedResponse()

    async def fake_get_client(self):
        return FakeMalformedClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)

    svc = OpenRouterService()
    res = await svc.generate(system_prompt="Be a monk", user_prompt="What is love?")

    assert isinstance(res, str)
    assert len(res) > 0
    # Must return a graceful fallback string, not crash with uncaught json/value error
    assert "connectivity issue" in res.lower() or "connection issue" in res.lower()


@pytest.mark.asyncio
async def test_openrouter_503_recovers_via_fallback_model(monkeypatch):
    """When the primary model returns 503, the request should fall back to the secondary model."""
    monkeypatch.setattr(settings, "openrouter_generation_model", "deepseek/deepseek-chat")
    monkeypatch.setattr(settings, "openrouter_generation_model_fallback", "meta-llama/llama-3.3-70b-instruct")
    monkeypatch.setattr(settings, "llm_max_retries", 1)

    models_called = []

    class FakeFailoverClient:
        async def post(self, url, json=None, **kwargs):
            model = json.get("model") if json else None
            models_called.append(model)
            if model == "deepseek/deepseek-chat":
                return Fake503Response()
            return FakeSuccessResponse()

    async def fake_get_client(self):
        return FakeFailoverClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)

    svc = OpenRouterService()
    res = await svc.generate(system_prompt="Be a monk", user_prompt="What is peace?")

    assert models_called == ["deepseek/deepseek-chat", "meta-llama/llama-3.3-70b-instruct"]
    assert res == "Wisdom from the fallback model."


@pytest.mark.asyncio
async def test_openrouter_timeout_returns_graceful_degradation(monkeypatch):
    """When OpenRouter API times out, generate() returns graceful degradation message."""
    class FakeTimeoutClient:
        async def post(self, url, json=None, **kwargs):
            raise asyncio.TimeoutError("Connection timed out after 60s")

    async def fake_get_client(self):
        return FakeTimeoutClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)

    svc = OpenRouterService()
    res = await svc.generate(system_prompt="Be a monk", user_prompt="What is freedom?")

    assert isinstance(res, str)
    assert "connectivity issue" in res.lower() or "connection issue" in res.lower()
