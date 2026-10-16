"""Throttling (provider 429 or our own RPM limiter) means the service is up.

2026-09-26, benchmark retry: OpenRouter 429s drove our limiter's backoff to
~115 s, the gateway's 60 s task timeout fired while the call slept, and the
gateway recorded each timeout as a provider failure -- five of them opened the
breaker and every chat got an instant system_error. Throttling must never trip
the breaker, and must not turn into a canned answer either.
"""

import asyncio

import httpx
import pytest

from app.coalescer import _InMemoryCoalescer
from app.config import settings
from services.circuit_breaker import CircuitState
from services.llm_gateway import LLMGateway
from services.openrouter_service import OpenRouterService, ProviderRateLimitedError


class _ThrottledProvider:
    def __init__(self):
        self.calls = 0

    async def generate(self, system_prompt, user_prompt, context="", **kwargs):
        self.calls += 1
        raise ProviderRateLimitedError("OpenRouter throttled")


@pytest.mark.asyncio
async def test_gateway_does_not_trip_the_breaker_on_throttling():
    gw = LLMGateway(primary=_ThrottledProvider(), coalescer=_InMemoryCoalescer(ttl=0.0))
    for i in range(gw._primary_breaker.config.failure_threshold + 3):
        with pytest.raises(ProviderRateLimitedError):
            await gw.generate("sys", f"q{i}")
    assert gw._primary_breaker.get_state() == CircuitState.CLOSED
    assert gw._primary_breaker.get_stats()["failures"] == 0


@pytest.mark.asyncio
async def test_gateway_limiter_raises_instead_of_sleeping_past_the_budget(monkeypatch):
    svc = OpenRouterService()

    async def throttled(key):
        return False, 115.0

    monkeypatch.setattr(OpenRouterService._shared_rate_limiter, "is_allowed_async", throttled)
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(ProviderRateLimitedError):
        await svc._enforce_rate_limit(strict_gateway=True)
    assert all(s <= OpenRouterService._MAX_GATEWAY_THROTTLE_WAIT_S for s in sleeps)


@pytest.mark.asyncio
async def test_gateway_path_429_raises_rate_limited_not_canned_text(monkeypatch):
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")

    class Client429:
        async def post(self, url, json=None, **kwargs):
            return httpx.Response(429, request=request, json={"error": "rate limited"})

    async def fake_get_client(self):
        return Client429()

    async def no_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(OpenRouterService, "_get_http_client", fake_get_client)
    monkeypatch.setattr(OpenRouterService, "_enforce_rate_limit", no_limit)
    monkeypatch.setattr(settings, "llm_max_retries", 1)
    svc = OpenRouterService()
    with pytest.raises(ProviderRateLimitedError):
        await svc._call_api(
            [{"role": "user", "content": "q"}],
            svc._gen_model,
            operation="standard",
            strict_gateway=True,
        )
    assert svc._circuit.get_stats()["failures"] == 0


def test_rate_limit_key_is_scoped_per_model():
    """2026-10-15: one model's 429 must not back off every other model (gate, scorer)."""
    from services.openrouter_service import OpenRouterService

    assert OpenRouterService._rate_limit_key(None) == OpenRouterService._RATE_LIMIT_KEY
    a = OpenRouterService._rate_limit_key("deepseek/deepseek-chat")
    b = OpenRouterService._rate_limit_key("meta-llama/llama-3.1-8b-instruct")
    assert a != b and a.startswith(OpenRouterService._RATE_LIMIT_KEY)


@pytest.mark.asyncio
async def test_429_on_one_model_does_not_throttle_another():
    """A 429 recorded for model X backs off X only; model Y stays unthrottled."""
    from services.openrouter_service import OpenRouterService

    OpenRouterService.reset_shared_rate_limiter()
    svc = OpenRouterService()
    slow, fast = "deepseek/deepseek-chat", "meta-llama/llama-3.1-8b-instruct"
    for _ in range(3):
        await svc._record_rate_limit_response(slow)
    limiter = OpenRouterService._shared_rate_limiter
    allowed_slow, wait_slow = await limiter.is_allowed_async(svc._rate_limit_key(slow))
    allowed_fast, wait_fast = await limiter.is_allowed_async(svc._rate_limit_key(fast))
    assert allowed_slow is False and wait_slow > 0
    assert allowed_fast is True
    OpenRouterService.reset_shared_rate_limiter()
