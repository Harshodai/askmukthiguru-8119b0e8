"""Tests for LLMGateway — fakes only, no network, no real provider classes.

Covers: primary success, same-provider model-tier fallback, cross-provider
fallback gating (off by default / on when enabled), circuit breaker trip, and
coalescing of concurrent identical calls.
"""

import asyncio

import pytest

from app.coalescer import _InMemoryCoalescer
from services.circuit_breaker import CircuitOpenException
from services.llm_gateway import LLMGateway


class _FakeProvider:
    """Minimal LLMProvider-shaped fake: async generate(), scriptable failures."""

    def __init__(self, name="fake", fail_models=None, always_fail=False):
        self.name = name
        self.calls: list[dict] = []
        self._fail_models = fail_models or set()
        self._always_fail = always_fail

    async def generate(self, system_prompt, user_prompt, context="", **kwargs):
        model = kwargs.get("model")
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt, "context": context, **kwargs})
        if self._always_fail:
            raise RuntimeError(f"{self.name} always fails")
        if model in self._fail_models:
            raise RuntimeError(f"{self.name} model {model} failed")
        return f"{self.name}:{model or 'default'}:{user_prompt}"


def _gateway(primary, **kw) -> LLMGateway:
    coalescer = kw.pop("coalescer", None) or _InMemoryCoalescer(ttl=5.0)
    return LLMGateway(primary=primary, coalescer=coalescer, **kw)


@pytest.mark.asyncio
async def test_primary_success_path():
    primary = _FakeProvider("primary")
    gw = _gateway(primary)

    result = await gw.generate("sys", "hello")

    assert result == "primary:default:hello"
    assert len(primary.calls) == 1
    snap = gw.metrics.snapshot()
    assert snap["calls"] == 1
    assert snap["fallbacks"] == 0
    assert snap["per_provider_errors"] == {}


@pytest.mark.asyncio
async def test_same_provider_model_fallback_fires_on_primary_model_failure():
    # Default model (unset -> None) fails; the configured fallback model succeeds.
    primary = _FakeProvider("primary", fail_models={None})
    gw = _gateway(primary, primary_model_fallback="fallback-model")

    result = await gw.generate("sys", "hi")

    assert result == "primary:fallback-model:hi"
    assert len(primary.calls) == 2
    assert primary.calls[0].get("model") is None
    assert primary.calls[1]["model"] == "fallback-model"
    assert gw.metrics.snapshot()["fallbacks"] == 1


@pytest.mark.asyncio
async def test_cross_provider_fallback_off_by_default_raises():
    primary = _FakeProvider("primary", always_fail=True)
    secondary = _FakeProvider("secondary")
    gw = _gateway(primary, secondary=secondary, cross_provider_fallback_enabled=False)

    with pytest.raises(RuntimeError):
        await gw.generate("sys", "hi")

    assert len(secondary.calls) == 0  # never touched — flag was off


@pytest.mark.asyncio
async def test_cross_provider_fallback_fires_when_enabled():
    primary = _FakeProvider("primary", always_fail=True)
    secondary = _FakeProvider("secondary")
    gw = _gateway(primary, secondary=secondary, cross_provider_fallback_enabled=True)

    result = await gw.generate("sys", "hi")

    assert result == "secondary:default:hi"
    assert len(secondary.calls) == 1
    assert gw.metrics.snapshot()["fallbacks"] == 1


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold_and_rejects():
    primary = _FakeProvider("primary", always_fail=True)
    # "ollama" circuit config = failure_threshold 3 (lowest configured) — trips fastest.
    gw = _gateway(primary, primary_name="ollama")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await gw.generate("sys", "hi", use_cache=False)
    assert len(primary.calls) == 3

    # 4th call: breaker is now OPEN — gateway must reject before touching the provider.
    with pytest.raises(CircuitOpenException):
        await gw.generate("sys", "hi", use_cache=False)
    assert len(primary.calls) == 3  # unchanged
    assert gw.metrics.snapshot()["circuit_rejections"] == 1


@pytest.mark.asyncio
async def test_coalescing_collapses_concurrent_identical_calls():
    call_count = 0

    class _SlowProvider:
        async def generate(self, system_prompt, user_prompt, context="", **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return "answer"

    gw = _gateway(_SlowProvider())

    results = await asyncio.gather(
        gw.generate("sys", "same question"),
        gw.generate("sys", "same question"),
        gw.generate("sys", "same question"),
    )

    assert results == ["answer", "answer", "answer"]
    assert call_count == 1  # only one actually reached the provider
    assert gw.metrics.snapshot()["cache_hits"] == 2


if __name__ == "__main__":
    # ponytail: self-check without pytest — mirrors llm_gateway.py's own __main__ block.
    async def _run_all():
        await test_primary_success_path()
        await test_same_provider_model_fallback_fires_on_primary_model_failure()
        await test_cross_provider_fallback_off_by_default_raises()
        await test_cross_provider_fallback_fires_when_enabled()
        await test_circuit_breaker_opens_after_threshold_and_rejects()
        await test_coalescing_collapses_concurrent_identical_calls()
        print("test_llm_gateway self-check: all OK")

    asyncio.run(_run_all())
