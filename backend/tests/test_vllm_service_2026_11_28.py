"""Opt-in self-hosted vLLM provider (2026-11-28). No network: httpx.MockTransport."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.config import Settings, settings
from services.circuit_breaker import CircuitOpenException, get_circuit_breaker_registry
from services.llm_factory import LLMServiceFactory, _register_default_providers, _registry
from services.openrouter_service import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderRateLimitedError,
    ProviderRefusalError,
)
from services.vllm_service import VllmService

SECRET_PROMPT = "PROMPT-MUST-NOT-BE-LOGGED-7731"


def _ok(content="3", **extra):
    body = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
    body.update(extra)
    return httpx.Response(200, json=body)


@pytest.fixture
def make(monkeypatch):
    monkeypatch.setattr(settings, "vllm_base_url", "http://vllm.test/v1")
    monkeypatch.setattr(settings, "vllm_api_key", "k-test")
    monkeypatch.setattr(settings, "openrouter_budget_guard_enabled", True)
    VllmService._limiter = None

    def build(handler):
        import asyncio

        svc = VllmService()
        svc._max_retries = 1
        svc._client = httpx.AsyncClient(
            base_url="http://vllm.test/v1",
            headers={"Authorization": "Bearer k-test"},
            transport=httpx.MockTransport(handler),
        )
        svc._client_loop = asyncio.get_running_loop()
        return svc

    yield build
    get_circuit_breaker_registry().unregister("vllm")
    VllmService._limiter = None


def test_default_settings_do_not_register_vllm():
    assert Settings(_env_file=None).vllm_base_url == ""
    assert "vllm" not in LLMServiceFactory.list_providers()
    with pytest.raises(ValueError):
        VllmService()


def test_registered_only_when_base_url_set(monkeypatch):
    monkeypatch.setattr(settings, "vllm_base_url", "http://vllm.test/v1")
    try:
        _register_default_providers()
        assert "vllm" in LLMServiceFactory.list_providers()
    finally:
        _registry._constructors.pop("vllm", None)


@pytest.mark.asyncio
async def test_request_has_only_vllm_fields_and_never_logs_prompts(make, caplog):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        return _ok("hello")

    svc = make(handler)
    with caplog.at_level(logging.DEBUG):
        out = await svc.generate(
            "sys",
            SECRET_PROMPT,
            model="anthropic/claude-haiku-5.5",
            max_tokens=64,
            temperature=None,
            response_format={"type": "json_object"},
            operation="verify",
            reasoning_effort="low",
            session_id="s1",
            fallback_model="x/y",
            provider_overrides={"zdr": True},
        )
    assert out == "hello"
    body = seen["body"]
    assert seen["path"].endswith("/chat/completions") and seen["auth"] == "Bearer k-test"
    assert set(body) == {"model", "messages", "max_tokens", "response_format"}  # no temperature
    assert body["model"] == "anthropic/claude-haiku-5.5"
    assert SECRET_PROMPT not in caplog.text


@pytest.mark.asyncio
async def test_temperature_sent_when_given_and_fast_model_default(make):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return _ok("YES")

    svc = make(handler)
    assert await svc._generate_fast("sys", "q") == "YES"
    assert seen["body"]["model"] == settings.openrouter_classify_model
    assert seen["body"]["temperature"] == 0.0 and seen["body"]["max_tokens"] == 2048


@pytest.mark.asyncio
async def test_free_provider_never_touches_the_openrouter_ledger(make):
    class _Boom:
        async def eval(self, *a):
            raise AssertionError("shared spend ledger must not be touched")

    svc = make(lambda r: _ok("3"))  # no usage.cost in the reply
    svc._budget._client = _Boom()
    assert await svc.generate("s", "u") == "3"


@pytest.mark.asyncio
async def test_metered_provider_settles_at_declared_cost(make, monkeypatch):
    monkeypatch.setattr(settings, "vllm_fixed_cost_per_call_usd", 0.002)

    class _Redis:
        def __init__(self):
            self.calls = []

        async def eval(self, *a):
            self.calls.append(a)
            return [1, 0.002, 0.002]

    svc = make(lambda r: _ok("3"))
    redis = _Redis()
    svc._budget._client = redis
    await svc.generate("s", "u")
    assert len(redis.calls) == 1  # reserved 0.002, settled at 0.002: nothing refunded
    assert redis.calls[0][4] == 0.002


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "exc"),
    [(429, ProviderRateLimitedError), (401, ProviderAuthError), (503, ProviderConnectionError)],
)
async def test_http_errors_raise_the_classes_the_scorer_catches(make, status, exc):
    svc = make(lambda r: httpx.Response(status, json={"error": "x"}))
    with pytest.raises(exc):
        await svc.generate("s", "u")


@pytest.mark.asyncio
async def test_refusal_empty_and_transport_failures_raise(make):
    svc = make(
        lambda r: httpx.Response(
            200, json={"choices": [{"message": {"content": ""}, "finish_reason": "content_filter"}]}
        )
    )
    with pytest.raises(ProviderRefusalError):
        await svc.generate("s", "u")

    svc = make(lambda r: httpx.Response(200, json={"choices": []}))
    with pytest.raises(ProviderConnectionError):
        await svc.generate("s", "u")

    def boom(request):
        raise httpx.ConnectError("down")

    svc = make(boom)
    with pytest.raises(ProviderConnectionError):
        await svc.generate("s", "u")


@pytest.mark.asyncio
async def test_own_circuit_breaker_and_limiter_key(make):
    svc = make(lambda r: _ok("3"))
    registry = get_circuit_breaker_registry()
    assert registry.get("vllm") is svc._circuit
    assert registry.get("openrouter") is not svc._circuit

    keys = []

    class _Limiter:
        async def is_allowed_async(self, key):
            keys.append(key)
            return True, 0.0

    VllmService._limiter = _Limiter()
    await svc.generate("s", "u", model="m1")
    assert keys == ["vllm:rpm:m1"]

    for _ in range(20):
        svc._circuit.record_failure()
    with pytest.raises(CircuitOpenException):
        await svc.generate("s", "u")


@pytest.mark.asyncio
async def test_rate_limited_locally_raises_instead_of_failing_open(make):
    class _Deny:
        async def is_allowed_async(self, key):
            return False, 2.0

    svc = make(lambda r: _ok("3"))
    VllmService._limiter = _Deny()
    with pytest.raises(ProviderRateLimitedError):
        await svc.generate("s", "u")
