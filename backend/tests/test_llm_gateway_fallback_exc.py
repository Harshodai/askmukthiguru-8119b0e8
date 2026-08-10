"""P1-BE-1 — fallback-provider failures must record the fallback's OWN exception.

Regression: ``_stream_routed`` recorded the FIRST provider's exception
(``primary_exc``) on the circuit breaker when the same-provider model fallback
also failed, masking the true root cause (the fallback failure) in metrics and
breaker state. The same class of bug existed in the non-stream model-fallback
paths and was fixed by reassigning ``primary_exc = fb_exc``.

Fakes only, no network — mirrors tests/test_llm_gateway.py conventions.
"""

import asyncio

import pytest

from app.coalescer import _InMemoryCoalescer
from services.llm_gateway import LLMGateway


class _FakeProvider:
    """Minimal LLMProvider-shaped fake with scriptable per-model failures."""

    def __init__(self, name="fake", fail_models=None):
        self.name = name
        self.calls: list[dict] = []
        self._fail_models = fail_models or set()

    async def generate(self, system_prompt, user_prompt, context="", **kwargs):
        model = kwargs.get("model")
        self.calls.append(
            {"system_prompt": system_prompt, "user_prompt": user_prompt, "context": context, **kwargs}
        )
        if model in self._fail_models:
            raise RuntimeError(f"{self.name} model {model} failed")
        return f"{self.name}:{model or 'default'}:{user_prompt}"

    async def generate_stream(self, system_prompt, user_prompt, context="", **kwargs):
        model = kwargs.get("model")
        self.calls.append(
            {"system_prompt": system_prompt, "user_prompt": user_prompt, "context": context, **kwargs}
        )
        if model in self._fail_models:
            raise RuntimeError(f"{self.name} stream model {model} failed")
        yield f"{self.name}:{model or 'default'}:{user_prompt}"


class _SlowStreamingProvider:
    """Streams a first chunk successfully, then fails — the mid-stream case.

    ``_stream_routed`` refuses to fall back once a chunk was emitted, so this
    verifies the plain re-raise path also carries the failing provider's
    exception (no cross-contamination from an earlier error).
    """

    def __init__(self, name="slow", fail_after=0):
        self.name = name
        self._fail_after = fail_after
        self.calls = 0

    async def generate_stream(self, system_prompt, user_prompt, context="", **kwargs):
        self.calls += 1
        yield "partial chunk"
        raise RuntimeError(f"{self.name} stream exploded mid-flight")


def _gateway(primary, **kw) -> LLMGateway:
    coalescer = kw.pop("coalescer", None) or _InMemoryCoalescer(ttl=5.0)
    return LLMGateway(primary=primary, coalescer=coalescer, **kw)


@pytest.mark.asyncio
async def test_model_fallback_failure_records_fallback_exception():
    """Both the default model and the fallback model fail → the breaker records
    the FALLBACK's exception (the one actually raised), not the primary's."""
    primary = _FakeProvider("primary", fail_models={None, "fallback-model"})
    gw = _gateway(primary, primary_model_fallback="fallback-model")

    with pytest.raises(RuntimeError, match="fallback-model failed"):
        await gw.generate("sys", "hi", use_cache=False)

    # The breaker's last recorded failure must be the fallback failure.
    breaker_failure = gw._primary_breaker.get_stats()
    assert breaker_failure["failures"] >= 2  # primary + fallback both counted
    assert gw.metrics.snapshot()["per_provider_errors"]["primary"] == 2
    assert len(primary.calls) == 2  # default model then fallback model


@pytest.mark.asyncio
async def test_stream_model_fallback_failure_records_fallback_exception():
    """Uncached stream path: same-provider fallback fails → the breaker records
    the fallback's own exception, not the primary's."""
    primary = _FakeProvider("primary", fail_models={None, "fallback-model"})
    gw = _gateway(primary, primary_model_fallback="fallback-model")

    with pytest.raises(RuntimeError, match="stream model fallback-model failed"):
        chunks = []
        async for chunk in gw.generate_stream("sys", "hi", use_cache=False):
            chunks.append(chunk)

    assert chunks == []  # nothing emitted — fallback happened pre-first-chunk
    assert gw.metrics.snapshot()["per_provider_errors"]["primary"] == 2
    assert gw._primary_breaker.get_stats()["failures"] >= 2


@pytest.mark.asyncio
async def test_mid_stream_failure_re_raises_own_exception():
    """Once a chunk was emitted the gateway does NOT fall back — the failure
    must propagate as-is and count exactly once (the failing provider)."""
    primary = _SlowStreamingProvider()
    gw = _gateway(primary, primary_model_fallback="fallback-model")

    with pytest.raises(RuntimeError, match="slow stream exploded mid-flight"):
        async for _chunk in gw.generate_stream("sys", "hi", use_cache=False):
            pass

    assert primary.calls == 1  # no fallback attempt after emission
    assert gw.metrics.snapshot()["per_provider_errors"]["primary"] == 1
    assert gw.metrics.snapshot()["fallbacks"] == 0


if __name__ == "__main__":
    # ponytail: one runnable self-check — run pytest on this module.
    raise SystemExit(pytest.main([__file__, "-v"]))
