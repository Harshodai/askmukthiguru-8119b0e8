"""LLM Gateway — thin orchestration wrapper around already-constructed LLMProvider
instances.

Reuses existing infra, does not reimplement any of it:
  - services/circuit_breaker.py: DefaultCircuitBreaker / CircuitBreakerConfig
  - app/coalescer.py: get_or_run() single-flight coalescing
  - services/llm/base.py: LLMProvider interface (what `primary`/`secondary` implement)

Design:
  - Same-VENDOR model-tier fallback (e.g. OpenRouter primary model -> OpenRouter
    fallback model) is the default-on behavior — it's the dormant bug fix
    described in openrouter_service.py:322 ("fallback_model branch removed per
    security audit"), reactivated here at the gateway layer instead of inside
    the provider's own retry loop.
  - Cross-PROVIDER (different vendor) fallback is OFF by default and only runs
    when the caller explicitly passes cross_provider_fallback_enabled=True.
    This preserves the deliberate security-audit decision recorded in
    app/container.py:188-190 — no silent routing of a user's message to an
    undisclosed third-party vendor on failure.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from services.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitOpenException,
    DefaultCircuitBreaker,
)
from services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

TaskType = Literal["casual", "standard", "deep", "extraction"]


@dataclass
class GatewayMetrics:
    """Real counters only — every field is incremented at the point the thing
    actually happened, nothing pre-seeded or estimated."""

    calls: int = 0
    fallbacks: int = 0
    cache_hits: int = 0
    circuit_rejections: int = 0
    per_provider_errors: dict[str, int] = field(default_factory=dict)

    def record_error(self, provider_name: str) -> None:
        self.per_provider_errors[provider_name] = self.per_provider_errors.get(provider_name, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "fallbacks": self.fallbacks,
            "cache_hits": self.cache_hits,
            "circuit_rejections": self.circuit_rejections,
            "per_provider_errors": dict(self.per_provider_errors),
        }


class LLMGateway:
    """Single entry point for LLM generation.

    Does not construct providers — the composition root (ServiceContainer) builds
    `primary`/`secondary` and passes them in already-constructed.
    """

    def __init__(
        self,
        primary: LLMProvider,
        coalescer: Any,
        *,
        secondary: Optional[LLMProvider] = None,
        primary_name: str = "primary",
        secondary_name: str = "secondary",
        primary_model_fallback: Optional[str] = None,
        cross_provider_fallback_enabled: bool = False,
    ) -> None:
        self._primary = primary
        self._secondary = secondary
        self._primary_name = primary_name
        self._secondary_name = secondary_name
        self._primary_model_fallback = primary_model_fallback
        self._cross_provider_fallback_enabled = cross_provider_fallback_enabled
        self._coalescer = coalescer

        # ponytail: one breaker per wrapped provider, built here rather than
        # threaded in as constructor args — less code at every call site, and
        # this is genuinely a second, independent layer on top of whatever
        # breaker the concrete service already holds internally (e.g.
        # OpenRouterService._circuit) — this one gates whether the gateway
        # attempts the call at all.
        self._primary_breaker = DefaultCircuitBreaker(CircuitBreakerConfig.from_provider(primary_name))
        self._secondary_breaker = (
            DefaultCircuitBreaker(CircuitBreakerConfig.from_provider(secondary_name))
            if secondary is not None
            else None
        )

        self.metrics = GatewayMetrics()
        self._inflight: set[str] = set()  # local coalesce-hit tracking only, see generate()

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        *,
        task: TaskType = "standard",
        use_cache: bool = True,
        **kwargs: Any,
    ) -> str:
        """Single entry point for all LLM generation."""
        self.metrics.calls += 1
        if not use_cache:
            return await self._generate_routed(system_prompt, user_prompt, context, task, **kwargs)

        key = self._cache_key(system_prompt, user_prompt, context, task, kwargs)
        # Coalescer itself doesn't report hit/miss on its return value, so this
        # is our own bookkeeping: did an identical request already own this key
        # when we arrived? That's a real coalesce hit, not an estimate.
        if key in self._inflight:
            self.metrics.cache_hits += 1
        self._inflight.add(key)
        try:
            return await self._coalescer.get_or_run(
                key, lambda: self._generate_routed(system_prompt, user_prompt, context, task, **kwargs)
            )
        finally:
            self._inflight.discard(key)

    def _cache_key(self, system_prompt: str, user_prompt: str, context: str, task: str, kwargs: dict) -> str:
        payload = json.dumps(
            {
                "provider": self._primary_name,
                "sp": system_prompt,
                "up": user_prompt,
                "ctx": context,
                "task": task,
                "kw": kwargs,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def _generate_routed(
        self, system_prompt: str, user_prompt: str, context: str, task: str, **kwargs: Any
    ) -> str:
        """Primary -> same-provider model fallback -> (opt-in) cross-provider fallback."""
        kwargs.setdefault("operation", task)

        if not self._primary_breaker.can_execute():
            self.metrics.circuit_rejections += 1
            logger.warning(f"LLMGateway: primary '{self._primary_name}' circuit OPEN — rejected")
            open_exc = CircuitOpenException(self._primary_name)
            if self._cross_provider_fallback_enabled and self._secondary is not None:
                return await self._generate_secondary(system_prompt, user_prompt, context, open_exc, **kwargs)
            raise open_exc

        try:
            result = await self._primary.generate(system_prompt, user_prompt, context=context, **kwargs)
            self._primary_breaker.record_success()
            return result
        except Exception as primary_exc:
            self._primary_breaker.record_failure(primary_exc)
            self.metrics.record_error(self._primary_name)
            logger.warning(f"LLMGateway: primary '{self._primary_name}' failed: {primary_exc}")

            if self._primary_model_fallback:
                try:
                    result = await self._primary.generate(
                        system_prompt, user_prompt, context=context, model=self._primary_model_fallback, **kwargs
                    )
                    self._primary_breaker.record_success()
                    self.metrics.fallbacks += 1
                    return result
                except Exception as fb_exc:
                    self._primary_breaker.record_failure(fb_exc)
                    self.metrics.record_error(self._primary_name)
                    logger.warning(
                        f"LLMGateway: primary '{self._primary_name}' model-fallback "
                        f"'{self._primary_model_fallback}' also failed: {fb_exc}"
                    )
                    primary_exc = fb_exc

            if self._cross_provider_fallback_enabled and self._secondary is not None:
                return await self._generate_secondary(system_prompt, user_prompt, context, primary_exc, **kwargs)
            raise primary_exc

    async def _generate_secondary(
        self, system_prompt: str, user_prompt: str, context: str, upstream_exc: Exception, **kwargs: Any
    ) -> str:
        if not self._secondary_breaker.can_execute():
            self.metrics.circuit_rejections += 1
            logger.warning(f"LLMGateway: secondary '{self._secondary_name}' circuit OPEN — rejected")
            raise upstream_exc
        try:
            result = await self._secondary.generate(system_prompt, user_prompt, context=context, **kwargs)
            self._secondary_breaker.record_success()
            self.metrics.fallbacks += 1
            logger.info(f"LLMGateway: cross-provider fallback to '{self._secondary_name}' succeeded")
            return result
        except Exception as secondary_exc:
            self._secondary_breaker.record_failure(secondary_exc)
            self.metrics.record_error(self._secondary_name)
            logger.error(f"LLMGateway: secondary '{self._secondary_name}' also failed: {secondary_exc}")
            raise secondary_exc


if __name__ == "__main__":
    # Self-check — full suite lives in backend/tests/test_llm_gateway.py.
    import asyncio

    class _EchoProvider:
        async def generate(self, system_prompt, user_prompt, context="", **kwargs):
            return f"echo:{user_prompt}"

    async def _demo():
        from app.coalescer import _InMemoryCoalescer

        gw = LLMGateway(primary=_EchoProvider(), coalescer=_InMemoryCoalescer())
        out = await gw.generate("sys", "hello")
        assert out == "echo:hello", out
        assert gw.metrics.snapshot()["calls"] == 1
        print("llm_gateway self-check OK")

    asyncio.run(_demo())
