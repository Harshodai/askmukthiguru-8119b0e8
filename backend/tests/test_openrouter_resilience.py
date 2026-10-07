"""Resilience and failure-injection tests for OpenRouter service.

Covers B19 failure matrix:
1. Malformed JSON payload from provider -> graceful degradation
2. 503 / upstream server error with fallback model recovery
3. Connection / timeout failure handling
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

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


class Fake404Response:
    """Primary model de-listed from OpenRouter. Must fail over, not raise."""

    status_code = 404

    def raise_for_status(self):
        req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        resp = httpx.Response(404, request=req)
        raise httpx.HTTPStatusError("404 Not Found", request=req, response=resp)

    def json(self):
        return {"error": {"message": "No endpoints found for deepseek/deepseek-chat"}}


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
async def test_openrouter_404_recovers_via_fallback_model(monkeypatch):
    """A 404 means the primary model id is de-listed: retrying it in place
    can never succeed, so the request must fail over to the fallback model
    (one attempt) instead of raising."""
    monkeypatch.setattr(settings, "openrouter_generation_model", "deepseek/deepseek-chat")
    monkeypatch.setattr(
        settings, "openrouter_generation_model_fallback", "meta-llama/llama-3.3-70b-instruct"
    )
    monkeypatch.setattr(settings, "llm_max_retries", 1)

    models_called = []

    class FakeFailoverClient:
        async def post(self, url, json=None, **kwargs):
            model = json.get("model") if json else None
            models_called.append(model)
            if model == "deepseek/deepseek-chat":
                return Fake404Response()
            return FakeSuccessResponse()

    async def fake_get_client(self):
        return FakeFailoverClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)

    svc = OpenRouterService()
    res = await svc.generate(system_prompt="Be a monk", user_prompt="What is peace?")

    assert models_called == ["deepseek/deepseek-chat", "meta-llama/llama-3.3-70b-instruct"]
    assert res == "Wisdom from the fallback model."


@pytest.mark.asyncio
async def test_openrouter_404_without_fallback_degrades_gracefully(monkeypatch):
    """A 404 with no fallback model configured must not raise on the chat
    path: it degrades gracefully (same as a 5xx with no fallback)."""

    class Fake404Client:
        async def post(self, url, json=None, **kwargs):
            return Fake404Response()

    async def fake_get_client(self):
        return Fake404Client()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)
    monkeypatch.setattr(settings, "openrouter_generation_model", "gone/removed-model")
    monkeypatch.setattr(settings, "openrouter_generation_model_fallback", "")

    svc = OpenRouterService()
    res = await svc.generate(
        system_prompt="Be a monk", user_prompt="What is freedom?", model="gone/removed-model"
    )

    assert isinstance(res, str)
    assert "connectivity issue" in res.lower() or "connection issue" in res.lower()


@pytest.mark.asyncio
async def test_openrouter_503_recovers_via_fallback_model(monkeypatch):
    """When the primary model returns 503, the request should fall back to the secondary model."""
    monkeypatch.setattr(settings, "openrouter_generation_model", "deepseek/deepseek-chat")
    monkeypatch.setattr(
        settings, "openrouter_generation_model_fallback", "meta-llama/llama-3.3-70b-instruct"
    )
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
            raise TimeoutError("Connection timed out after 60s")

    async def fake_get_client(self):
        return FakeTimeoutClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)

    svc = OpenRouterService()
    res = await svc.generate(system_prompt="Be a monk", user_prompt="What is freedom?")

    assert isinstance(res, str)
    assert "connectivity issue" in res.lower() or "connection issue" in res.lower()


@pytest.mark.asyncio
async def test_cancelled_call_releases_half_open_reservation(monkeypatch):
    """A caller-side cancellation (our own timeout) must not wedge the breaker.

    ``can_execute()`` reserves a half-open slot that only ``record_success()``/
    ``record_failure()`` release. ``asyncio.CancelledError`` is a
    ``BaseException`` (Py3.8+), so it skips a bare ``except Exception`` clause
    -- a request our own timeout cancels while in flight leaked the
    reservation forever, exhausting ``half_open_max_calls`` after a few
    caller-side timeouts and wedging the breaker open with no natural
    recovery (mirrors the 2026-09-15 probe-leak wedge, but via a real
    cancelled call instead of a read-only probe).
    """

    class FakeCancelledClient:
        async def post(self, url, json=None, **kwargs):
            raise asyncio.CancelledError()

    async def fake_get_client(self):
        return FakeCancelledClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)
    monkeypatch.setattr(settings, "llm_max_retries", 1)

    svc = OpenRouterService()
    # Trip the breaker OPEN, then make the recovery window already elapsed so
    # the next can_execute() (inside _call_api, below) transitions it into
    # HALF_OPEN and reserves the single probe slot in the same call -- exactly
    # what a real just-recovered breaker does.
    for _ in range(svc._circuit.config.failure_threshold):
        svc._circuit.record_failure(RuntimeError("down"))
    assert svc._circuit.get_state().value == "open"
    svc._circuit.config.recovery_timeout = 0.0
    svc._circuit.config.half_open_max_calls = 1

    with pytest.raises(asyncio.CancelledError):
        await svc.generate(system_prompt="Be a monk", user_prompt="What is silence?")

    stats = svc._circuit.get_stats()
    assert stats["half_open_in_flight"] == 0, (
        "cancelled call leaked a half-open reservation; the breaker is now "
        "wedged and will refuse every future call"
    )
    # The leaked slot must not still be blocking a genuine next attempt.
    assert svc._circuit.can_execute() is True


@pytest.mark.asyncio
async def test_our_own_cancellations_never_trip_a_closed_breaker(monkeypatch):
    """A caller-side cancellation is our timeout, not a provider failure.
    Counting it as a failure lets a few slow requests trip the breaker open
    and refuse every chat -- the same outage by another route."""

    class FakeCancelledClient:
        async def post(self, url, json=None, **kwargs):
            raise asyncio.CancelledError()

    async def fake_get_client(self):
        return FakeCancelledClient()

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)
    monkeypatch.setattr(settings, "llm_max_retries", 1)

    svc = OpenRouterService()
    for _ in range(svc._circuit.config.failure_threshold + 2):
        with pytest.raises(asyncio.CancelledError):
            await svc.generate(system_prompt="Be a monk", user_prompt="What is silence?")

    assert svc._circuit.get_state().value == "closed"
    assert svc._circuit.get_stats().get("failures", 0) == 0
