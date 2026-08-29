"""
Mukthi Guru — OpenRouter Service

Gateway to all LLM operations via OpenRouter API.
Uses direct httpx HTTP calls for reliability and standard SSE streaming.
Configurable to use free tier Llama models.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any, ClassVar, Optional

import httpx
from anyio import Lock as AsyncLock
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential


def _is_retryable_openrouter_error(exc: BaseException) -> bool:
    """429 can't be fixed by retrying the same model within seconds — the
    quota that's exhausted doesn't refill that fast. Retrying just adds
    latency before the inevitable graceful-degradation fallback. Other
    transient httpx/timeout errors are still worth a retry.
    """
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        return False
    return isinstance(exc, (httpx.HTTPError, asyncio.TimeoutError))


from app.config import settings
from app.constants import CircuitBreakerProvider
from app.llm_tracing import (
    current_llm_span,
    record_llm_error,
    record_llm_result,
    set_llm_request,
    traced_llm_call,
)
from app.model_policy import OpenRouterModelPolicy
from app.openrouter_budget import OpenRouterBudgetGuard
from rag.prompts import (
    BATCH_GRADE_PROMPT,
    COMBINED_VERIFICATION_PROMPT,
    COMPRESS_CONTEXT_PROMPT,
    DECOMPOSE_QUERY_PROMPT,
    FAITHFULNESS_CHECK_PROMPT,
    HINT_EXTRACTION_PROMPT,
    HYDE_PROMPT,
    INTENT_CLASSIFICATION_PROMPT,
    IS_COMPLEX_QUERY_PROMPT,
    QUERY_REWRITE_PROMPT,
    SUMMARIZE_PROMPT,
    VERIFICATION_PROMPT,
)
from services.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitOpenException,
    DefaultCircuitBreaker,
)

logger = logging.getLogger(__name__)

# OpenRouter normally reports the actual charged amount in ``usage.cost``.
# These model-specific prices are an accounting fallback only: they are used
# when that field is absent, never when a provider-reported value is present.
# Keep this table synchronized with the production model configuration and
# OpenRouter's model pages; the fallback must not influence generation.
_OPENROUTER_FALLBACK_RATES_PER_MILLION: dict[str, tuple[float, float]] = {
    "qwen/qwen3-30b-a3b-instruct-2507": (0.04815, 0.1931),
    "meta-llama/llama-3.1-8b-instruct": (0.02, 0.04),
    # OpenRouter pricing pages verified 2026-08-22. Provider-reported
    # usage.cost always takes precedence over these accounting fallbacks.
    "google/gemini-2.5-flash": (0.30, 2.50),
    "google/gemini-3.6-flash": (0.75, 3.75),
}


class OpenRouterService:
    """Gateway to all LLM operations via OpenRouter Cloud API."""

    # Rate-limit state is intentionally CLASS-level (shared by every
    # instance), not instance-level. Ingestion creates one fresh
    # OpenRouterService per component -- quality-gate scoring, contextual
    # chunking, LightRAG, OKF extraction -- ~53 instances in a single run.
    # With instance-level state each one enforced settings.openrouter_rpm_limit
    # independently, so real aggregate traffic to the OpenRouter API ran far
    # above the configured limit and tripped the circuit breaker within
    # minutes even at a "safe" RPM value (live-confirmed 2026-08-27). One
    # shared counter enforces the real process-wide limit.
    _shared_rpm_lock: ClassVar[Optional[AsyncLock]] = None
    _shared_request_count: ClassVar[int] = 0
    _shared_window_start: ClassVar[float] = 0.0

    def __init__(self) -> None:
        self._policy = OpenRouterModelPolicy.from_settings(settings)
        self._budget_guard = OpenRouterBudgetGuard.from_settings(settings, self._policy)

        """Initialize the OpenRouter API client."""
        self._api_key = settings.openrouter_api_key
        # Free models can be queried without key occasionally, but key is highly recommended
        self._base_url = getattr(settings, "openrouter_base_url", "https://openrouter.ai/api/v1")
        self._gen_model = settings.openrouter_generation_model
        self._gen_model_fallback = settings.openrouter_generation_model_fallback
        self._cls_model = settings.openrouter_classify_model
        self._timeout = getattr(settings, "llm_timeout", 60)
        self._max_retries = getattr(settings, "llm_max_retries", 3)
        self._rpm_limit = max(1, settings.openrouter_rpm_limit)

        # Use provider-specific circuit breaker
        config = CircuitBreakerConfig.from_provider(CircuitBreakerProvider.OPENROUTER.value)
        self._circuit = DefaultCircuitBreaker(config)
        from services.circuit_breaker import get_circuit_breaker_registry

        get_circuit_breaker_registry().register(
            CircuitBreakerProvider.OPENROUTER.value, self._circuit
        )

        # Rate limiting state -- shared across all instances, see the
        # class-level docstring above. Lazily create the shared lock once;
        # every subsequent instance reuses it instead of getting its own.
        if OpenRouterService._shared_rpm_lock is None:
            OpenRouterService._shared_rpm_lock = AsyncLock()
            OpenRouterService._shared_window_start = time.time()

        # Connection pooling: AsyncClient
        self._http_client: Optional[httpx.AsyncClient] = None
        self._http_client_lock = AsyncLock()

        logger.info(
            f"OpenRouter Service initialized: "
            f"gen_model={self._gen_model}, cls_model={self._cls_model}, "
            f"base_url={self._base_url}"
        )

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create the singleton HTTP client with connection pooling."""
        async with self._http_client_lock:
            if self._http_client is None:
                limits = httpx.Limits(
                    max_connections=getattr(settings, "http_max_connections", 100),
                    max_keepalive_connections=getattr(
                        settings, "http_max_keepalive_connections", 20
                    ),
                    keepalive_expiry=getattr(settings, "http_keepalive_expiry", 30.0),
                )
                headers = {"Content-Type": "application/json"}
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"
                self._http_client = httpx.AsyncClient(
                    base_url=self._base_url,
                    headers=headers,
                    timeout=self._timeout,
                    limits=limits,
                )
            return self._http_client

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        async with self._http_client_lock:
            if self._http_client is not None:
                await self._http_client.aclose()
                self._http_client = None
                logger.info("OpenRouter HTTP client closed")

    async def _enforce_rate_limit(self) -> None:
        """Enforce RPM limits before querying OpenRouter API.

        Uses the CLASS-level shared counter (see class docstring) so the
        limit is enforced against real aggregate traffic across every
        OpenRouterService instance in this process, not per-instance.
        """
        now = time.time()
        async with OpenRouterService._shared_rpm_lock:
            if now - OpenRouterService._shared_window_start >= 60:
                OpenRouterService._shared_window_start = now
                OpenRouterService._shared_request_count = 0
            if OpenRouterService._shared_request_count >= self._rpm_limit:
                delay = 60.0 - (now - OpenRouterService._shared_window_start)
                if delay > 0:
                    logger.warning(f"OpenRouter rate limit hit — sleeping {delay:.1f}s")
                    await asyncio.sleep(delay)
                    OpenRouterService._shared_window_start = time.time()
                    OpenRouterService._shared_request_count = 0
            OpenRouterService._shared_request_count += 1

    async def _record_rate_limit_response(self) -> None:
        """Adjust rate limiter after receiving a 429 response."""
        now = time.time()
        async with OpenRouterService._shared_rpm_lock:
            OpenRouterService._shared_request_count = self._rpm_limit
            delay = 60.0 - (now - OpenRouterService._shared_window_start)
            logger.warning(f"OpenRouter returned 429 — rate limiter exhausted for {delay:.1f}s")

    @classmethod
    def reset_shared_rate_limiter(cls) -> None:
        """Reset the process-wide rate-limit counter. Test-isolation hook:
        since the state is class-level (see class docstring), it otherwise
        accumulates across every instance and every test in one pytest run.
        """
        cls._shared_rpm_lock = None
        cls._shared_request_count = 0
        cls._shared_window_start = 0.0

    async def _graceful_degradation(self, messages: list[dict], operation: str = "fallback") -> str:
        """Return a graceful fallback response when OpenRouter is unavailable.

        This avoids 500 errors — instead the user gets a meaningful message.
        """
        logger.warning(f"Using graceful degradation for {operation}")
        # Check if the last message looks like a question
        last_msg = messages[-1]["content"] if messages else ""
        is_question = any(
            last_msg.lower().startswith(q)
            for q in ["what", "how", "who", "where", "why", "when", "can", "do", "is", "are"]
        )
        if is_question:
            return (
                "I'm currently experiencing a temporary connectivity issue with my knowledge base. "
                "Please try your question again in a few moments. "
                "I'll be happy to help you once I'm fully connected."
            )
        return (
            "I'm here and listening. However, I'm experiencing a temporary connection issue "
            "with my backend services. Please try again shortly."
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Fast heuristic: ~1.3 tokens per word."""
        if not text:
            return 0
        return int(len(text.split()) * 1.3)

    @staticmethod
    def _usage_cost(usage: Mapping[str, Any] | None) -> float | None:
        """Read the provider-reported cost; ``None`` means it was omitted."""
        if not isinstance(usage, Mapping) or "cost" not in usage:
            return None
        try:
            value = float(usage.get("cost") or 0.0)
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else 0.0

    @staticmethod
    def _fallback_cost(tokens_in: int, tokens_out: int, model: str) -> float:
        """Estimate cost only for configured models with known public rates."""
        input_rate, output_rate = _OPENROUTER_FALLBACK_RATES_PER_MILLION.get(model, (0.0, 0.0))
        return max(
            0.0,
            (max(0, int(tokens_in)) * input_rate + max(0, int(tokens_out)) * output_rate)
            / 1_000_000,
        )

    def _track_token_usage(
        self,
        *,
        tokens_in: int,
        tokens_out: int,
        model: str,
        operation: str = "generate",
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
        cost_usd: float | None = None,
    ) -> None:
        """Push provider cost or an explicit fallback estimate into accounting."""
        try:
            from services.cost_tracker import token_accumulator_var

            acc = token_accumulator_var.get()
            estimated_cost = (
                self._fallback_cost(tokens_in, tokens_out, model)
                if cost_usd is None
                else 0.0
            )
            if acc is not None:
                acc.tokens_in += tokens_in
                acc.tokens_out += tokens_out
                if cost_usd is None:
                    acc.estimated_cost_usd += estimated_cost
                    if estimated_cost > 0:
                        logger.info(
                            "OpenRouter usage cost missing; using fallback estimate "
                            "model=%s estimate_usd=%.8f",
                            model,
                            estimated_cost,
                        )
                else:
                    acc.cost_usd += max(0.0, cost_usd)
                acc.model = model
                acc.provider = "openrouter"
            from app.runtime_metrics import (
                observe_openrouter_accounting,
                observe_provider_actual_cost,
            )

            fallback_cost_known = model in _OPENROUTER_FALLBACK_RATES_PER_MILLION
            observe_openrouter_accounting(
                model=model,
                operation=operation,
                cached_tokens=cached_tokens,
                cache_write_tokens=cache_write_tokens,
                estimated_cost_usd=estimated_cost,
                cost_known=cost_usd is not None,
                fallback_cost_known=fallback_cost_known,
            )
            if cost_usd is not None and cost_usd > 0:
                observe_provider_actual_cost("openrouter", cost_usd)
        except Exception as exc:
            logger.warning(f"Failed to record openrouter token usage: {exc}")

    @traced_llm_call("openrouter")
    async def _call_api(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        operation: str = "generate",
        fallback_model: Optional[str] = None,
        _is_fallback_attempt: bool = False,
        **kwargs,
    ) -> str:
        """Call OpenRouter API with circuit breaker, rate limit, retries, and token tracking.

        On a 429/connection-error, retries once against `fallback_model` (a
        different model — a different rate-limit bucket entirely — before
        falling back to graceful degradation). Falls back to graceful
        degradation when OpenRouter is unavailable for both.

        The local `_enforce_rate_limit`/`_record_rate_limit_response` counters
        track this account's calls against the *primary* model's quota, not
        a per-model quota — a fallback attempt is deliberately a different
        model, so it must not inherit the primary model's just-triggered
        "sleep until window resets" state.
        """
        self._policy.assert_model_allowed(model)
        max_tokens = min(max_tokens, self._policy.output_ceiling(operation))

        if not _is_fallback_attempt:
            await self._enforce_rate_limit()

        if not self._circuit.can_execute():
            logger.warning(
                f"OpenRouter circuit breaker open — graceful degradation for {operation}"
            )
            return await self._graceful_degradation(messages, operation=operation)

        reservation = await self._budget_guard.reserve()

        is_anthropic = "anthropic/" in model or "claude" in model

        payload_messages = []
        for msg in messages:
            if is_anthropic and msg.get("role") == "system" and msg.get("content"):
                content = msg["content"]
                if isinstance(content, str):
                    payload_messages.append(
                        {
                            "role": "system",
                            "content": [
                                {
                                    "type": "text",
                                    "text": content,
                                    "cache_control": {"type": "ephemeral"},
                                }
                            ],
                        }
                    )
                else:
                    payload_messages.append(msg)
            else:
                payload_messages.append(msg)

        payload = {
            "model": model,
            "messages": payload_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Reasoning models (e.g. google/gemini-3.6-flash) burn hidden
            # reasoning_tokens out of the same max_tokens budget by default --
            # unbounded, that can consume the entire ceiling and leave the
            # visible answer truncated (finish_reason=length) before a word of
            # actual output. Cap it to a quarter of the ceiling, floor 64, so
            # there's always budget left for the visible completion. Safe to
            # send unconditionally: OpenRouter silently ignores `reasoning` for
            # models that don't support it (verified against gemma-3-12b-it),
            # and errors only if a caller tries `reasoning.enabled=false` on a
            # model where reasoning is mandatory -- capping the budget instead
            # of disabling it avoids that.
            "reasoning": {"max_tokens": max(64, max_tokens // 4)},
            "provider": self._policy.provider_preferences(),
        }

        # Handle potential parameters passed in kwargs
        for param in ["top_p", "frequency_penalty", "presence_penalty"]:
            if param in kwargs:
                payload[param] = kwargs[param]

        headers = {}
        if is_anthropic:
            headers["anthropic-beta"] = "prompt-caching-2024-07-31"

        async def _execute():
            attempt_started = time.perf_counter()
            client = await self._get_http_client()
            resp = await client.post("/chat/completions", json=payload, headers=headers or None)
            logger.info(
                "OPENROUTER_HTTP_TIMING operation=%s model=%s status_class=%s response_ms=%.1f",
                operation,
                model,
                f"{int(getattr(resp, 'status_code', 0)) // 100}xx",
                (time.perf_counter() - attempt_started) * 1000,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            retryer = AsyncRetrying(
                stop=stop_after_attempt(self._max_retries),
                wait=wait_exponential(multiplier=1, min=1, max=8),
                retry=retry_if_exception(_is_retryable_openrouter_error),
                reraise=True,
            )

            data = None
            attempt_count = 0
            call_started = time.perf_counter()
            async for attempt in retryer:
                attempt_count += 1
                with attempt:
                    data = await _execute()

            self._circuit.record_success()

            if not data or "choices" not in data or not data["choices"]:
                raise ValueError("Empty or invalid response from OpenRouter API")

            content = data["choices"][0]["message"]["content"]

            # Track provider-reported usage. Token estimates remain a fallback
            # only when OpenRouter omits usage metadata.
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens") or self._estimate_tokens(str(messages))
            tokens_out = usage.get("completion_tokens") or self._estimate_tokens(content)

            prompt_details = usage.get("prompt_tokens_details") or {}
            cached_tokens = (
                prompt_details.get("cached_tokens") or usage.get("cache_read_input_tokens") or 0
            )
            cache_write_tokens = (
                prompt_details.get("cache_write_tokens")
                or usage.get("cache_creation_input_tokens")
                or 0
            )
            if cached_tokens > 0 or cache_write_tokens > 0:
                logger.info(
                    "OpenRouter Cache Hit: cached_tokens=%s cache_write_tokens=%s "
                    "model=%s operation=%s",
                    cached_tokens,
                    cache_write_tokens,
                    model,
                    operation,
                )

            cost_usd = self._usage_cost(usage)
            self._track_token_usage(
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                model=model,
                operation=operation,
                cached_tokens=cached_tokens,
                cache_write_tokens=cache_write_tokens,
                cost_usd=cost_usd,
            )
            # Same values the OPENROUTER_CALL_TIMING log line below carries, but
            # as a queryable span (plus prompt/completion when LLM_TRACE_CONTENT
            # is on). See docs/architecture/llm-observability-design.md.
            _span = current_llm_span()
            set_llm_request(_span, model=model, operation=operation)
            record_llm_result(
                _span,
                completion=content,
                prompt=messages,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cached_tokens=cached_tokens,
                cost_usd=cost_usd,
                finish_reason=data.get("choices", [{}])[0].get("finish_reason"),
                response_model=data.get("model"),
            )
            await reservation.settle(cost_usd)
            logger.info(
                "OPENROUTER_CALL_TIMING operation=%s model=%s attempts=%d total_ms=%.1f "
                "prompt_tokens=%s completion_tokens=%s cached_tokens=%s cache_write_tokens=%s "
                "finish_reason=%s",
                operation,
                model,
                attempt_count,
                (time.perf_counter() - call_started) * 1000,
                tokens_in,
                tokens_out,
                cached_tokens,
                cache_write_tokens,
                str(data.get("choices", [{}])[0].get("finish_reason") or "unknown")[:32],
            )

            return content

        except Exception as exc:
            record_llm_error(current_llm_span(), exc)
            logger.warning(
                "OPENROUTER_CALL_ERROR_TIMING operation=%s model=%s attempts=%d elapsed_ms=%.1f "
                "error_type=%s",
                operation,
                model,
                locals().get("attempt_count", 0),
                (time.perf_counter() - locals().get("call_started", time.perf_counter())) * 1000,
                type(exc).__name__,
            )
            # Do NOT count 429 (rate limit) as a circuit breaker failure.
            # 429 is a transient quota signal — the service is up but throttling.
            # Only count service errors (5xx) and non-HTTP failures.
            is_rate_limit = (
                isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429
            )
            is_connection_error = isinstance(
                exc, (httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException)
            )
            if is_rate_limit or is_connection_error:
                if is_rate_limit:
                    await self._record_rate_limit_response()
                else:
                    # Connection-class failures count against the breaker even though
                    # we still degrade gracefully — matches ollama_service.py's pattern
                    # (services/ollama_service.py:298-301), so streak of dead-connection
                    # failures actually trips the circuit instead of looking healthy forever.
                    self._circuit.record_failure()
                reason = "rate limited (429)" if is_rate_limit else type(exc).__name__
                if fallback_model and not _is_fallback_attempt:
                    logger.warning(
                        f"OpenRouter {reason} during {operation} — retrying against "
                        f"fallback model {fallback_model} (same provider, separate rate-limit bucket)"
                    )
                    return await self._call_api(
                        messages,
                        fallback_model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        operation=operation,
                        _is_fallback_attempt=True,
                        **kwargs,
                    )
                logger.warning(f"OpenRouter {reason} during {operation} — graceful degradation")
                return await self._graceful_degradation(messages, operation=operation)

            self._circuit.record_failure()
            logger.error(f"OpenRouter call failed during {operation} (model={model}): {exc}")
            raise

    # -----------------------------------------------------------------------
    # Public Generation Methods
    # -----------------------------------------------------------------------

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> str:
        """Core generation method using the main generation model."""
        messages = [{"role": "system", "content": system_prompt}]
        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {user_prompt}"
        else:
            full_prompt = user_prompt
        messages.append({"role": "user", "content": full_prompt})

        temperature = kwargs.pop("temperature", 0.1)
        max_tokens = kwargs.pop("max_tokens", 8192)
        model = kwargs.pop("model", self._gen_model)
        operation = kwargs.pop("operation", "generate")
        # Only auto-fallback when using the default generation model — an
        # explicit model= override means the caller already picked deliberately.
        fallback_model = kwargs.pop(
            "fallback_model", self._gen_model_fallback if model == self._gen_model else None
        )

        return await self._call_api(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            operation=operation,
            fallback_model=fallback_model,
            **kwargs,
        )

    async def _generate_fast(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs,
    ) -> str:
        """Fast classification/grading using the fast model."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        temperature = kwargs.pop("temperature", 0.0)
        max_tokens = kwargs.pop("max_tokens", 2048)
        model = kwargs.pop("model", self._cls_model)

        return await self._call_api(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            operation="classification",
            **kwargs,
        )

    async def generate_raw(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        **kwargs,
    ) -> str:
        """Raw generation without graceful degradation — exceptions propagate.

        Intended for callers (e.g., translation providers) that need failures
        to bubble up for fallback logic, unlike `_generate_fast`/`translate_text`
        which swallow errors.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        temperature = kwargs.pop("temperature", 0.0)
        max_tokens = kwargs.pop("max_tokens", 2048)

        return await self._call_api(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            operation="raw_generation",
            **kwargs,
        )

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> AsyncIterator[str]:
        """Streaming generation using the main OpenRouter model."""
        await self._enforce_rate_limit()

        model = kwargs.get("model", self._gen_model)
        self._policy.assert_model_allowed(model)
        operation = kwargs.get("operation", "generate")

        is_anthropic = "anthropic/" in model or "claude" in model

        if is_anthropic and system_prompt:
            messages = [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            ]
        else:
            messages = [{"role": "system", "content": system_prompt}]

        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {user_prompt}"
        else:
            full_prompt = user_prompt
        messages.append({"role": "user", "content": full_prompt})

        max_tokens = min(kwargs.get("max_tokens", 8192), self._policy.output_ceiling(operation))
        temperature = kwargs.get("temperature", 0.1)

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "provider": self._policy.provider_preferences(),
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if not self._circuit.can_execute():
            raise CircuitOpenException(
                provider="openrouter",
                message="Circuit breaker OPEN in generate_stream",
            )

        reservation = await self._budget_guard.reserve()
        last_error = None
        stream_usage: dict | None = None
        stream_started = time.perf_counter()
        for attempt in range(self._max_retries):
            attempt_started = time.perf_counter()
            try:
                client = await self._get_http_client()
                buffer = ""
                headers_ready_ms = None
                first_event_ms = None
                first_token_ms = None
                finish_reason = "unknown"

                headers = {}
                if is_anthropic:
                    headers["anthropic-beta"] = "prompt-caching-2024-07-31"

                async with client.stream(
                    "POST",
                    "/chat/completions",
                    json=payload,
                    headers=headers or None,
                ) as resp:
                    headers_ready_ms = (time.perf_counter() - attempt_started) * 1000
                    resp.raise_for_status()

                    async for line in resp.aiter_lines():
                        if first_event_ms is None:
                            first_event_ms = (time.perf_counter() - attempt_started) * 1000
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        usage = data.get("usage")
                        if isinstance(usage, dict):
                            stream_usage = usage
                        choice = data.get("choices", [{}])[0] or {}
                        finish_reason = str(choice.get("finish_reason") or finish_reason)[:32]
                        delta_msg = choice.get("delta", {})
                        delta = delta_msg.get("content") or ""
                        if delta:
                            if first_token_ms is None:
                                first_token_ms = (time.perf_counter() - attempt_started) * 1000
                            buffer += delta
                            yield delta

                self._circuit.record_success()
                usage = stream_usage or {}
                prompt_tokens = usage.get("prompt_tokens") or self._estimate_tokens(str(messages))
                completion_tokens = usage.get("completion_tokens") or self._estimate_tokens(buffer)
                cost_usd = self._usage_cost(usage) if stream_usage is not None else None
                self._track_token_usage(
                    tokens_in=prompt_tokens,
                    tokens_out=completion_tokens,
                    model=model,
                    cost_usd=cost_usd or 0.0,
                )
                await reservation.settle(cost_usd)
                logger.info(
                    "OPENROUTER_STREAM_TIMING operation=%s model=%s attempt=%d status_class=%s "
                    "headers_ms=%.1f first_event_ms=%s ttft_ms=%s total_ms=%.1f "
                    "prompt_tokens=%s completion_tokens=%s cached_tokens=%s "
                    "finish_reason=%s",
                    operation,
                    model,
                    attempt + 1,
                    f"{int(getattr(resp, 'status_code', 0)) // 100}xx",
                    headers_ready_ms or 0.0,
                    "%.1f" % first_event_ms if first_event_ms is not None else "none",
                    "%.1f" % first_token_ms if first_token_ms is not None else "none",
                    (time.perf_counter() - stream_started) * 1000,
                    prompt_tokens,
                    completion_tokens,
                    (stream_usage or {}).get("prompt_tokens_details", {}).get("cached_tokens", 0)
                    if isinstance(stream_usage, dict)
                    else 0,
                    finish_reason,
                )
                return

            except Exception as e:
                logger.warning(
                    "OPENROUTER_STREAM_ERROR_TIMING operation=%s model=%s attempt=%d elapsed_ms=%.1f "
                    "error_type=%s",
                    operation,
                    model,
                    attempt + 1,
                    (time.perf_counter() - attempt_started) * 1000,
                    type(e).__name__,
                )
                last_error = e
                is_rate_limit = (
                    isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
                )
                if is_rate_limit:
                    await self._record_rate_limit_response()
                    wait = min(2**attempt, 8)
                    logger.warning(
                        f"OpenRouter streaming 429 — retry {attempt + 1}/{self._max_retries} after {wait}s"
                    )
                    await asyncio.sleep(wait)
                else:
                    self._circuit.record_failure()
                    logger.error(f"OpenRouter streaming failed: {e}")
                    raise

        if not self._circuit.can_execute():
            raise CircuitOpenException(
                provider="openrouter",
                message="Circuit breaker OPEN in generate_stream",
            )
        logger.error(f"OpenRouter streaming exhausted {self._max_retries} retries: {last_error}")
        raise last_error or Exception("Streaming failed after all retries")

    # -----------------------------------------------------------------------
    # Classification / RAG Operations
    # -----------------------------------------------------------------------

    async def classify_intent(self, message: str, **kwargs) -> str:
        """Classify intent of the message."""
        kwargs.setdefault("max_tokens", 256)
        result = await self._generate_fast(INTENT_CLASSIFICATION_PROMPT, message, **kwargs)
        result_upper = result.upper().strip()

        if not result_upper:
            return "QUERY"

        for candidate in [
            "DISTRESS",
            "SAFETY_VIOLATION",
            "ADVERSARIAL",
            "MEDITATION",
            "FACTUAL",
            "RELATIONAL",
            "FOLLOW_UP",
            "QUERY",
            "CASUAL",
            "COMPARATIVE",
        ]:
            if candidate in result_upper:
                return candidate
        return "QUERY"

    async def classify_complexity(self, text: str) -> str:
        """Classify question complexity."""
        result = await self._generate_fast(IS_COMPLEX_QUERY_PROMPT, text)
        return "complex" if "complex" in result.lower() else "simple"

    async def classify_intent_and_complexity(self, message: str, **kwargs) -> dict:
        """Classify both intent and complexity in a single call."""
        prompt = (
            "Classify the following user message.\n\n"
            "1. INTENT: Choose exactly one from: DISTRESS, SAFETY_VIOLATION, ADVERSARIAL, "
            "MEDITATION, FACTUAL, RELATIONAL, FOLLOW_UP, CASUAL, COMPARATIVE.\n"
            "2. COMPLEXITY: Is this question 'simple' (single fact) or 'complex' (multi-hop/comparative)?\n\n"
            f"Message: {message}\n\n"
            "Reply in EXACTLY this format (no other text):\n"
            "INTENT: <intent>\nCOMPLEXITY: <simple|complex>"
        )
        kwargs.setdefault("max_tokens", 64)
        result = await self._generate_fast("", prompt, **kwargs)

        result_upper = result.upper().strip()
        lines = result_upper.splitlines()

        intent = "FACTUAL"
        complexity = "complex"

        for line in lines:
            line = line.strip()
            if line.startswith("INTENT:"):
                val = line.split(":", 1)[-1].strip()
                for candidate in [
                    "DISTRESS",
                    "SAFETY_VIOLATION",
                    "ADVERSARIAL",
                    "MEDITATION",
                    "FACTUAL",
                    "RELATIONAL",
                    "FOLLOW_UP",
                    "COMPARATIVE",
                    "CASUAL",
                    "QUERY",
                ]:
                    if candidate in val:
                        intent = candidate
                        break
            elif line.startswith("COMPLEXITY:"):
                val = line.split(":", 1)[-1].strip()
                complexity = "simple" if "SIMPLE" in val else "complex"

        if intent == "QUERY":
            intent = "FACTUAL"

        return {"intent": intent, "complexity": complexity}

    async def classify_distress_structured(self, message: str) -> dict:
        """Assess emotional distress from a message, returning structured data."""
        # OpenRouter free Llama might not support Instructor JSON mode cleanly.
        # Fall back directly to robust JSON prompt formatting.
        prompt = (
            f"Analyze the following message for emotional distress or a cry for help. "
            f"Return ONLY a valid JSON object with fields: is_distress (bool), confidence (float 0-1), reason (string).\n\n"
            f"Message: {message}"
        )
        try:
            resp = await self._generate_fast(
                system_prompt="You are a psychological safety assessor. Return ONLY a valid JSON object with fields: is_distress (bool), confidence (float 0-1), reason (string). No reasoning, no think tags, no extra text.",
                user_prompt=prompt,
                timeout=10.0,
                max_retries=1,
            )
            # Clean up the response in case model returns markdown code block
            if not resp:
                raise ValueError("_generate_fast returned None or empty string")
            resp_clean = resp.strip()
            if resp_clean.startswith("```"):
                # strip markdown blocks if any
                resp_clean = re.sub(
                    r"^```(?:json)?\n(.*?)\n```$", r"\1", resp_clean, flags=re.DOTALL
                ).strip()

            first_brace = resp_clean.find("{")
            last_brace = resp_clean.rfind("}")
            if first_brace != -1 and last_brace != -1:
                resp_clean = resp_clean[first_brace : last_brace + 1]

            data = json.loads(resp_clean)
            return {
                "is_distress": bool(data.get("is_distress", False)),
                "confidence": float(data.get("confidence", 0.5)),
                "reason": str(data.get("reason", "Parsed successfully")),
            }
        except Exception as e:
            # A provider failure is not evidence of distress. Falling back to
            # classify_intent here can turn an unrelated question into a safety
            # redirect when the intent classifier is itself degraded. Deterministic
            # lexical checks (and the optional embedding detector) remain the
            # authoritative safety signals in SereneMindEngine.
            logger.warning(
                "OpenRouter distress JSON classification unavailable: %s; "
                "returning indeterminate non-distress result",
                e,
            )
            return {
                "is_distress": False,
                "confidence": 0.0,
                "reason": "Distress provider unavailable; deterministic safety checks remain authoritative",
            }

    async def batch_grade_relevance(self, query: str, documents: list[str], **kwargs) -> list[dict]:
        """CRAG: Grade documents batch-wise in one call."""
        if not documents:
            return []

        numbered_docs = "\n\n".join(
            f"Document {i + 1}:\n{doc[:1500]}" for i, doc in enumerate(documents)
        )

        prompt = f"Question: {query}\n\n{numbered_docs}"
        result = await self._generate_fast(BATCH_GRADE_PROMPT, prompt, **kwargs)

        relevance_results = [
            {"relevant": False, "reason": "No response from LLM"} for _ in documents
        ]

        for line in result.strip().splitlines():
            line = line.strip()
            if not line:
                continue

            match = re.match(r"(\d+)[:.]\s*(yes|no)(?:\s*[:-]\s*(.*))?", line, re.IGNORECASE)
            if match:
                try:
                    idx = int(match.group(1)) - 1
                    if 0 <= idx < len(documents):
                        is_relevant = match.group(2).lower() == "yes"
                        reason = (
                            match.group(3).strip()
                            if match.group(3)
                            else ("Relevant teaching" if is_relevant else "Irrelevant content")
                        )
                        relevance_results[idx] = {"relevant": is_relevant, "reason": reason}
                except (ValueError, IndexError):
                    continue

        if not any(r["relevant"] for r in relevance_results) and len(documents) > 0:
            relevance_results[0] = {
                "relevant": True,
                "reason": "Fallback: Used top retrieval result as a starting point.",
            }

        return relevance_results

    async def check_faithfulness(self, answer: str, context: str, **kwargs) -> bool:
        """Self-RAG: Check if answer is faithful to the context."""
        prompt = f"Context:\n{context}\n\nAnswer:\n{answer}"
        result = await self._generate_fast(FAITHFULNESS_CHECK_PROMPT, prompt, **kwargs)
        return "faithful" in result.lower()

    async def extract_hints(self, query: str, documents: list[str]) -> list[str]:
        """Stimulus RAG: Extract evidence hints."""
        combined_docs = "\n---\n".join(documents)
        system = HINT_EXTRACTION_PROMPT
        prompt = f"Question: {query}\n\nDocuments:\n{combined_docs}"

        result = await self.generate(system, prompt)

        hints = []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                hints.append(line[2:].strip())
            elif line and not line.startswith("#"):
                hints.append(line)

        return hints[:5]

    async def rewrite_query(
        self,
        original_query: str,
        reasons: list[str] = None,
        grading_reasons: list[str] = None,
        **kwargs,
    ) -> str:
        """CRAG: Rewrite query for retry."""
        prompt = f"Original query: {original_query}"
        actual_reasons = reasons or grading_reasons
        if actual_reasons:
            reasons_text = "\n".join([f"- {r}" for r in actual_reasons if r])
            prompt += f"\n\nReasons for previous retrieval failure:\n{reasons_text}\n\nInstructions: Use these reasons to understand what was missing."

        return await self.generate(QUERY_REWRITE_PROMPT, prompt, **kwargs)

    async def verify_claims(self, answer: str, context: str) -> dict:
        """CoVe: Generate verification questions and check."""
        prompt = f"Answer:\n{answer}\n\nContext:\n{context}"
        result = await self.generate(VERIFICATION_PROMPT, prompt)

        lines = result.upper().strip().splitlines()
        verdict_line = ""
        for line in reversed(lines):
            if "VERDICT" in line:
                verdict_line = line
                break

        if verdict_line:
            after_verdict = verdict_line.split("VERDICT", 1)[-1]
            passed = "PASS" in after_verdict and "FAIL" not in after_verdict
        else:
            passed = False

        return {
            "passed": passed,
            "details": result,
        }

    async def combined_verify(self, answer: str, context: str) -> dict:
        """Combined Self-RAG + CoVe verification in a single call."""
        system = COMBINED_VERIFICATION_PROMPT
        prompt = f"Answer:\n{answer}\n\nContext:\n{context}"

        result = await self.generate(system, prompt, temperature=0.0)

        result_upper = result.upper().strip()
        lines = result_upper.splitlines()

        is_faithful = False
        for line in lines:
            if "FAITHFULNESS" in line:
                after = line.split("FAITHFULNESS", 1)[-1]
                is_faithful = "FAITHFUL" in after and "HALLUCINATED" not in after
                break

        passed = False
        for line in reversed(lines):
            if "VERDICT" in line:
                after = line.split("VERDICT", 1)[-1]
                passed = "PASS" in after and "FAIL" not in after
                break

        confidence = 5.0
        faithfulness_score = 1.0 if is_faithful else 0.0
        relevancy_score = 1.0 if passed else 0.5

        for line in lines:
            if "CONFIDENCE" in line:
                after = line.split("CONFIDENCE", 1)[-1]
                nums = re.findall(r"\d+", after)
                if nums:
                    try:
                        confidence = float(min(int(nums[0]), 10))
                    except (ValueError, IndexError):
                        pass

        final_passed = is_faithful and passed

        return {
            "is_faithful": is_faithful,
            "passed": final_passed,
            "confidence": confidence,
            "faithfulness_score": faithfulness_score,
            "relevancy_score": relevancy_score,
            "details": result,
        }

    async def summarize(self, texts: list[str]) -> str:
        """Summarize texts (RAPTOR)."""
        combined = "\n\n".join(texts)
        return await self.generate(SUMMARIZE_PROMPT, combined)

    async def decompose_query(self, query: str, **kwargs) -> list[str]:
        """Split complex query into atomic sub-queries."""
        result = await self._generate_fast(DECOMPOSE_QUERY_PROMPT, query, **kwargs)

        sub_queries = []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                sub_queries.append(line[2:].strip())
            elif line.startswith(("1.", "2.", "3.")):
                sub_queries.append(line[2:].strip())

        return sub_queries if sub_queries else [query]

    async def generate_hypothetical_answer(self, query: str, **kwargs) -> str:
        """HyDE: Generate hypothetical answer."""
        return await self.generate(HYDE_PROMPT, query, operation="generate_hyde", **kwargs)

    async def compress_context(self, question: str, document_text: str, **kwargs) -> str:
        """Compress context chunk."""
        prompt = COMPRESS_CONTEXT_PROMPT.format(question=question, document_text=document_text)
        compressed = await self._generate_fast("", prompt, **kwargs)

        if "NO_RELEVANT_CONTEXT" in compressed:
            return ""
        return compressed.strip()

    async def translate_text(
        self,
        text: str,
        source_language_code: str,
        target_language_code: str,
    ) -> str:
        """Translate text using LLM."""
        if not text.strip():
            return ""

        src_code = source_language_code.lower().split("-")[0]
        tgt_code = target_language_code.lower().split("-")[0]

        if src_code == tgt_code:
            return text

        prompt = (
            f"You are a professional translator. Translate the following text from "
            f"language code '{src_code}' to language code '{tgt_code}'. "
            f"Provide ONLY the final translation. Do not include any notes, explanations, or quotes.\n\n"
            f"Text to translate:\n{text}"
        )
        try:
            translated = await self._generate_fast(
                system_prompt="You are a professional translator. Output only the translated text.",
                user_prompt=prompt,
            )
            return translated.strip()
        except Exception as e:
            logger.error(f"OpenRouter translation failed: {e}")
            return text

    @property
    def is_available(self) -> bool:
        """Return True if OpenRouter is configured."""
        return self._api_key is not None and len(self._api_key.strip()) > 0

    async def health_check(self) -> bool:
        """Ping OpenRouter /models endpoint to verify connectivity."""
        try:
            client = await self._get_http_client()
            resp = await client.get("/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False
