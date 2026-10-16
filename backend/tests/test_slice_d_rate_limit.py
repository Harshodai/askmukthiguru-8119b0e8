"""Slice D — rate-limit hardening: reset hygiene, call-site model proof.

1. ``finally``-reset: the class-level shared limiter is test pollution by
   design (see conftest); every test below resets it in a ``finally`` and
   PROVES the reset (limiter gone; a fresh instance rebuilds it; a
   previously-throttled key is allowed again).
2. Call-site model-arg proof: ``_enforce_rate_limit`` forwards its ``model``
   to the limiter key — recorded live against the configured generation
   model, not a hardcoded string.
3. Legacy ``None``-model path: ``model=None`` still keys the bare global
   window (backward compatible, no crash).
4. Isolation through the enforce path: 429s recorded for model A make
   ``_enforce_rate_limit(model=A)`` sleep while ``model=B`` returns at once
   with zero sleeps (per-model buckets, end to end).
"""

from __future__ import annotations

import asyncio

import pytest

from services.openrouter_service import OpenRouterService


class _KeyRecordingLimiter:
    """Stands in for the shared limiter; always allows, records keys."""

    def __init__(self):
        self.keys: list[str] = []

    async def is_allowed_async(self, key):
        self.keys.append(key)
        return True, 0.0

    async def record_attempt_async(self, key, success=True):  # pragma: no cover
        self.keys.append(key)


@pytest.mark.asyncio
async def test_shared_limiter_finally_reset_restores_clean_state(monkeypatch):
    svc = OpenRouterService()
    slow = "slice-d-reset-probe-model"
    try:
        for _ in range(3):
            await svc._record_rate_limit_response(slow)
        limiter = OpenRouterService._shared_rate_limiter
        allowed, _ = await limiter.is_allowed_async(svc._rate_limit_key(slow))
        assert allowed is False, "probe key should be throttled before reset"
    finally:
        OpenRouterService.reset_shared_rate_limiter()
    assert OpenRouterService._shared_rate_limiter is None
    fresh = OpenRouterService()  # rebuilds the shared limiter on construction
    assert OpenRouterService._shared_rate_limiter is not None
    try:
        allowed_after, _ = await OpenRouterService._shared_rate_limiter.is_allowed_async(
            fresh._rate_limit_key(slow)
        )
        assert allowed_after is True, "reset must clear the throttled state"
    finally:
        OpenRouterService.reset_shared_rate_limiter()


@pytest.mark.asyncio
async def test_enforce_forwards_configured_model_to_limiter_key(monkeypatch):
    """The call site passes the live generation model into the per-model key."""
    svc = OpenRouterService()
    probe = _KeyRecordingLimiter()
    try:
        monkeypatch.setattr(OpenRouterService, "_shared_rate_limiter", probe)
        await svc._enforce_rate_limit(model=svc._gen_model)
        assert probe.keys == [f"openrouter:rpm:{svc._gen_model}"]
        assert svc._gen_model, "generation model must be a real configured value"
    finally:
        OpenRouterService.reset_shared_rate_limiter()


@pytest.mark.asyncio
async def test_enforce_legacy_none_model_uses_global_key(monkeypatch):
    """``model=None`` keeps the legacy bare-global window (no crash)."""
    svc = OpenRouterService()
    probe = _KeyRecordingLimiter()
    try:
        monkeypatch.setattr(OpenRouterService, "_shared_rate_limiter", probe)
        await svc._enforce_rate_limit(model=None)
        assert probe.keys == [OpenRouterService._RATE_LIMIT_KEY]
    finally:
        OpenRouterService.reset_shared_rate_limiter()


@pytest.mark.asyncio
async def test_throttled_model_sleeps_while_other_model_passes(monkeypatch):
    """End-to-end per-model isolation through the real limiter + enforce path."""
    svc = OpenRouterService()
    model_a = svc._gen_model
    model_b = (
        svc._cls_model if svc._cls_model != model_a else "synthetic/slice-d-other-model"
    )
    sleeps: list[float] = []

    async def _fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    try:
        for _ in range(3):
            await svc._record_rate_limit_response(model_a)
        await svc._enforce_rate_limit(model=model_a)
        assert sleeps, "throttled model must back off (slept)"
        assert all(s >= 0 for s in sleeps)
        sleeps.clear()
        await svc._enforce_rate_limit(model=model_b)
        assert sleeps == [], "unthrottled model must pass with zero sleeps"
    finally:
        OpenRouterService.reset_shared_rate_limiter()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
