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

    async def no_limit(self, strict_gateway=False):
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
