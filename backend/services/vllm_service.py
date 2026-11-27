"""Opt-in self-hosted vLLM provider (OpenAI-compatible /v1/chat/completions).

Registered only when ``settings.vllm_base_url`` is set (``services/llm_factory.py``).
Differences from ``OpenRouterService`` and ``NimService``, on purpose:

* own circuit breaker (``"vllm"``) and own limiter key (``vllm:rpm:<model>``);
* spend: ``vllm_fixed_cost_per_call_usd`` (default 0.0 = free) via the budget guard, so no
  ``usage.cost`` is needed and the OpenRouter ledger is not touched;
* the request carries only fields vLLM understands (no ``provider``/``reasoning``/``session_id``);
  OpenRouter-only keywords are accepted and dropped. Thinking is NOT controlled here: serve the
  model with the template you want;
* every failure raises (``ProviderConnectionError`` and friends from ``openrouter_service``, the
  classes the first-person scorer catches); there is no canned text and no fallback provider;
* prompts and replies are never logged.

Models are whatever vLLM serves (``--served-model-name``): the scorer sends its configured
``first_person_relevance_model`` id, so serve under that name. ``OpenRouterModelPolicy`` is not
applied, and is not loosened, here.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, ClassVar, Optional

import httpx

from app.config import settings
from app.openrouter_budget import OpenRouterBudgetGuard
from app.security_utils import RedisBackedRateLimiter
from services.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitOpenException,
    DefaultCircuitBreaker,
    get_circuit_breaker_registry,
)
from services.openrouter_service import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderRateLimitedError,
    ProviderRefusalError,
)
from services.resilience import call_with_full_jitter

logger = logging.getLogger(__name__)

_NAME = "vllm"
# Request fields vLLM's OpenAI server understands; anything else a caller passes is dropped.
_PASSTHROUGH = ("top_p", "frequency_penalty", "presence_penalty", "response_format")


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, (httpx.TransportError, asyncio.TimeoutError))


class VllmService:
    provider_name = _NAME
    _limiter: ClassVar[Optional[RedisBackedRateLimiter]] = None

    def __init__(self) -> None:
        self._base_url = settings.vllm_base_url.strip()
        if not self._base_url:
            raise ValueError("VllmService needs settings.vllm_base_url")
        self._gen_model = settings.openrouter_generation_model
        self._cls_model = settings.openrouter_classify_model
        self._max_retries = getattr(settings, "llm_max_retries", 3)
        self._circuit = DefaultCircuitBreaker(CircuitBreakerConfig.from_provider(_NAME))
        get_circuit_breaker_registry().register(_NAME, self._circuit)
        self._budget = OpenRouterBudgetGuard(
            enabled=bool(settings.openrouter_budget_guard_enabled),
            redis_url=settings.redis_url,
            daily_budget_usd=settings.openrouter_daily_budget_usd,
            monthly_budget_usd=settings.openrouter_monthly_budget_usd,
            max_request_cost_usd=settings.openrouter_max_request_cost_usd,
            fail_closed=True,
            fixed_cost_usd=settings.vllm_fixed_cost_per_call_usd,
        )
        if VllmService._limiter is None:
            VllmService._limiter = RedisBackedRateLimiter(
                redis_url=settings.redis_url, ttl=60.0, max_requests=settings.vllm_rpm_limit
            )
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None
        logger.info("vLLM service initialized: base_url=%s gen=%s", self._base_url, self._gen_model)

    @property
    def model(self) -> str:
        return self._gen_model

    def _http(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        if self._client is None or self._client_loop is not loop:
            headers = {"Content-Type": "application/json"}
            if settings.vllm_api_key:
                headers["Authorization"] = f"Bearer {settings.vllm_api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url, headers=headers, timeout=settings.vllm_timeout_s
            )
            self._client_loop = loop
        return self._client

    async def _call_api(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: Optional[float],
        **kwargs: Any,
    ) -> str:
        limiter = VllmService._limiter
        if limiter is not None:
            allowed, retry_after = await limiter.is_allowed_async(f"{_NAME}:rpm:{model}")
            if not allowed:
                raise ProviderRateLimitedError(f"vLLM rpm limit; retry after {retry_after:.1f}s")
        if not self._circuit.can_execute():
            raise CircuitOpenException(provider=_NAME, message="vLLM circuit breaker is open")
        reservation = await self._budget.reserve()
        payload: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if temperature is not None:
            payload["temperature"] = temperature
        payload.update({k: kwargs[k] for k in _PASSTHROUGH if k in kwargs})
        sent = arrived = False
        cost: Optional[float] = None
        started = time.perf_counter()

        async def _post() -> dict:
            nonlocal sent, arrived, cost
            sent = True
            resp = await self._http().post("/chat/completions", json=payload)
            arrived = True
            resp.raise_for_status()
            body = resp.json()
            usage = body.get("usage") if isinstance(body, dict) else None
            if isinstance(usage, dict) and usage.get("cost") is not None:
                cost = max(0.0, float(usage["cost"]))
            return body

        try:
            data = await call_with_full_jitter(
                _post, max_retries=self._max_retries, is_retryable=_retryable
            )
            choice = (data.get("choices") or [{}])[0] if isinstance(data, dict) else {}
            message = choice.get("message") or {}
            if choice.get("finish_reason") in ("refusal", "content_filter") or message.get(
                "refusal"
            ):
                self._circuit.release_reservation()
                raise ProviderRefusalError("vLLM refusal")
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError("Empty or invalid response from vLLM")
            self._circuit.record_success()
            logger.info(
                "VLLM_CALL model=%s total_ms=%.1f", model, (time.perf_counter() - started) * 1000
            )
            return content
        except ProviderRefusalError:
            raise
        except asyncio.CancelledError:
            self._circuit.release_reservation()
            raise
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in (401, 403):
                self._circuit.release_reservation()
                raise ProviderAuthError(f"vLLM auth error ({code})") from exc
            if code == 429:
                self._circuit.release_reservation()
                raise ProviderRateLimitedError("vLLM 429") from exc
            if code >= 500 or code == 404:
                self._circuit.record_failure()
                raise ProviderConnectionError(f"vLLM HTTP {code}") from exc
            self._circuit.release_reservation()
            raise
        except (TimeoutError, httpx.TransportError, ValueError) as exc:
            self._circuit.record_failure()
            raise ProviderConnectionError(f"vLLM {type(exc).__name__}") from exc
        finally:
            await reservation.finalize(
                request_sent=sent, response_arrived=arrived, response_cost_usd=cost
            )

    @staticmethod
    def _messages(system_prompt: str, user_prompt: str, context: str = "") -> list[dict]:
        user = f"Context:\n{context}\n\nQuestion: {user_prompt}" if context else user_prompt
        return ([{"role": "system", "content": system_prompt}] if system_prompt else []) + [
            {"role": "user", "content": user}
        ]

    async def generate(
        self, system_prompt: str, user_prompt: str, context: str = "", **kwargs: Any
    ) -> str:
        return await self._call_api(
            self._messages(system_prompt, user_prompt, context),
            kwargs.pop("model", self._gen_model),
            kwargs.pop("max_tokens", 8192),
            kwargs.pop("temperature", 0.1),
            **kwargs,
        )

    async def _generate_fast(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        return await self._call_api(
            self._messages(system_prompt, user_prompt),
            kwargs.pop("model", self._cls_model),
            kwargs.pop("max_tokens", 2048),
            kwargs.pop("temperature", 0.0),
            **kwargs,
        )

    async def generate_hyde(self, question: str, **kwargs: Any) -> str:
        from rag.prompts import HYDE_PROMPT

        return await self._generate_fast(HYDE_PROMPT, question, **kwargs)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


if __name__ == "__main__":
    # Self-check (no network): the provider only builds when a base URL is configured.
    import sys

    if not settings.vllm_base_url.strip():
        try:
            VllmService()
        except ValueError as exc:
            print("ok:", exc)
            sys.exit(0)
        sys.exit("expected ValueError without vllm_base_url")
    print("vllm_base_url set; VllmService would build")
