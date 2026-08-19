"""Mukthi Guru — Sarvam HTTP Gateway

Extracts the core HTTP transport layer from SarvamCloudService.
Handles: connections, auth, retries, circuit breaker, rate limiting,
tracing spans, and self-healing logic.

All domain logic (prompt assembly, classification, etc.) lives elsewhere.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Optional
from urllib.parse import urlparse

import httpx
from anyio import Lock as AsyncLock

from app.config import settings
from services.circuit_breaker import DefaultCircuitBreaker
from services.sarvam_exceptions import CircuitOpenException, NonRetryableError, QuotaExceededError

logger = logging.getLogger(__name__)

# Documented Sarvam Cloud hosts allowed to receive the API subscription key.
# Mirrors backend/scripts/verify_sarvam.py (SARVAM_EXPECTED_HOST).
_SARVAM_ALLOWED_HOSTS = frozenset({"api.sarvam.ai"})

try:
    from opentelemetry import trace

    _has_otel = True
except ImportError:
    trace = None  # type: ignore[assignment]
    _has_otel = False


class SarvamHTTPGateway:
    """Thin HTTP gateway for Sarvam Cloud API.

    Responsible ONLY for transport concerns:
      - Connection pooling & lifecycle
      - Authentication headers
      - API key rotation (comma-separated keys, rotates on 429)
      - Retry logic with exponential backoff
      - Circuit breaker integration
      - Rate limiting (RPM throttling)
      - Self-healing (dynamic max_tokens/model adjustments)
      - OpenTelemetry span recording
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, circuit: Optional[DefaultCircuitBreaker] = None) -> None:
        """
        Args:
            circuit: Shared circuit breaker instance. When the caller (e.g.
                SarvamCloudService) already owns a "sarvam_cloud" breaker for its
                streaming path, pass it in so streaming and non-streaming Sarvam
                calls trip the same breaker instead of tracking failures in two
                independent instances that never see each other's state.
        """
        raw_key = settings.sarvam_30b_api_key or settings.sarvam_api_key or ""
        if not raw_key and not settings.sarvam_30b_endpoint:
            raise ValueError(
                "SARVAM_API_KEY is required for Sarvam Cloud API mode. "
                "Set it in .env or environment."
            )

        self._api_keys = [k.strip() for k in raw_key.split(",") if k.strip()]
        self._api_key = self._api_keys[0] if self._api_keys else ""
        self._key_index = 0
        self._key_lock = AsyncLock()

        # Validate the endpoint BEFORE any credentialed client or header is
        # constructed: the api-subscription-key must never leave for an
        # unvalidated URL (scheme/https + documented allowlist host).
        self._base_url = self._validate_base_url(
            settings.sarvam_30b_endpoint
            or getattr(settings, "sarvam_base_url", "https://api.sarvam.ai/v1"),
            has_api_key=bool(self._api_key),
        )
        self._timeout = getattr(settings, "llm_timeout", 60)
        self._max_retries = getattr(settings, "llm_max_retries", 3)

        # Circuit breaker (imported from shared module). Reuse the caller's shared
        # breaker when given (see __init__ docstring); only build a fresh one for
        # standalone construction (tests, scripts/ops/resolve_entities.py).
        if circuit is not None:
            self._circuit = circuit
        else:
            from app.constants import CircuitBreakerProvider
            from services.circuit_breaker import CircuitBreakerConfig, DefaultCircuitBreaker

            sarvam_config = CircuitBreakerConfig.from_provider(
                CircuitBreakerProvider.SARVAM_CLOUD.value
            )
            self._circuit = DefaultCircuitBreaker(sarvam_config)

        # Rate limiting
        self._last_request_time = 0.0
        self._rate_limit_lock = AsyncLock()
        self._max_tokens_limit = getattr(settings, "sarvam_max_tokens", 4096)

        # Connection pooling
        self._http_client: httpx.AsyncClient | None = None
        self._http_client_lock = AsyncLock()

        # Back-compat: set env for any code still using langchain-sarvam
        if self._api_key:
            os.environ["SARVAM_API_KEY"] = self._api_key

        key_count = len(self._api_keys)
        if key_count > 1:
            logger.info(
                f"SarvamHTTPGateway ready — {key_count} API keys loaded, key rotation enabled"
            )
        else:
            logger.info(f"SarvamHTTPGateway ready — base_url={self._base_url}")

    @staticmethod
    def _validate_base_url(base_url: str, *, has_api_key: bool) -> str:
        """Validate the Sarvam endpoint before any credentialed client is built.

        Keyed traffic is only ever sent to the documented Sarvam allowlist over
        https (``_SARVAM_ALLOWED_HOSTS``, mirroring ``verify_sarvam.py``). An
        unallowlisted host (documented self-hosted E2E endpoint) is accepted
        ONLY when no API key is configured, so a credential can never be sent
        to an unvalidated URL. Raises ValueError otherwise.
        """
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.hostname:
            raise ValueError(f"Invalid Sarvam base URL (missing scheme/host): {base_url!r}")
        if parsed.hostname in _SARVAM_ALLOWED_HOSTS:
            if parsed.scheme != "https":
                raise ValueError(
                    f"Sarvam base URL must use https for allowlisted host {parsed.hostname!r}: {base_url!r}"
                )
            return base_url
        if has_api_key:
            raise ValueError(
                f"Sarvam base URL host {parsed.hostname!r} is not in the allowlist "
                f"{sorted(_SARVAM_ALLOWED_HOSTS)}; refusing to send the API key to an "
                f"unvalidated endpoint: {base_url!r}"
            )
        return base_url

    async def _rotate_api_key(
        self, excluded: Optional[set[int]] = None
    ) -> Optional[tuple[int, str]]:
        """Rotate to the next untried API key in the comma-separated list.

        While holding ``_key_lock``, searches the key ring for the next index
        NOT present in ``excluded`` (the indices already tried this attempt).
        Returns (new_index, new_key) — captured under the lock so the caller's
        header and bookkeeping always agree — or None when every configured
        key is excluded.
        """
        excluded = excluded or set()
        async with self._key_lock:
            if not self._api_keys:
                return None
            for _ in range(len(self._api_keys)):
                self._key_index = (self._key_index + 1) % len(self._api_keys)
                if self._key_index in excluded:
                    continue
                self._api_key = self._api_keys[self._key_index]
                os.environ["SARVAM_API_KEY"] = self._api_key
                logger.info(
                    f"Rotated Sarvam API key to key {self._key_index + 1}/{len(self._api_keys)}"
                )
                return (self._key_index, self._api_key)
            return None

    async def close(self) -> None:
        async with self._http_client_lock:
            if self._http_client is not None:
                await self._http_client.aclose()
                self._http_client = None
                logger.info("HTTP client closed")

    async def _get_http_client(self) -> httpx.AsyncClient:
        async with self._http_client_lock:
            if self._http_client is None:
                limits = httpx.Limits(
                    max_connections=getattr(settings, "http_max_connections", 100),
                    max_keepalive_connections=getattr(
                        settings, "http_max_keepalive_connections", 20
                    ),
                    keepalive_expiry=getattr(settings, "http_keepalive_expiry", 30.0),
                )
                self._http_client = httpx.AsyncClient(
                    timeout=self._timeout,
                    limits=limits,
                    follow_redirects=False,  # never let a 3xx redirect move a credentialed request
                )
                logger.info(f"HTTP client initialised with pool {limits}")
            return self._http_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def call(
        self,
        *,
        messages: list[dict],
        model: str,
        max_tokens: int = 0,  # 0 = use _max_tokens_limit (updated by self-healing 400 responses)
        temperature: float = 0.1,
        stream: bool = False,
        operation: str = "generate",
        **kwargs,
    ) -> str:
        """Execute an HTTP POST to /chat/completions.

        Includes retry logic, circuit breaker, rate limiting, and
        self-healing parameter adjustments.

        max_tokens=0 (default) uses the current _max_tokens_limit which
        is dynamically lowered on 400 tier-exceeded responses. Callers may
        pass an explicit value but it is silently clamped to _max_tokens_limit
        so requests always stay within the subscription tier.
        """
        # Resolve and clamp max_tokens against the subscription tier limit.
        effective_max = max_tokens if max_tokens > 0 else self._max_tokens_limit
        effective_max = min(effective_max, self._max_tokens_limit)
        # 1. Circuit breaker check
        if not self._circuit.can_execute():
            exc = CircuitOpenException(
                "Sarvam API circuit breaker is OPEN — failing fast. "
                "Will retry after recovery timeout."
            )
            span = self._start_llm_span(model=model, operation=operation, attempt=0)
            self._record_span_exception(span, exc)
            raise exc

        # 2. Build headers (api-subscription-key is set per attempt from a
        #    lock-captured key pair so it matches rotation bookkeeping)
        headers = {
            "Content-Type": "application/json",
        }

        # 3. Validate/sanitize messages
        validated: list[dict] = []
        for msg in messages:
            content = (msg.get("content") or "").strip()
            if not content:
                if msg.get("role") == "system":
                    content = "You are a helpful spiritual guide."
                elif msg.get("role") == "user":
                    content = "Please respond."
                else:
                    continue
            validated.append({"role": msg["role"], "content": content})

        if not validated:
            logger.warning("call: No valid messages after validation")
            return ""

        # 4. Dynamic max_tokens / model adjustments
        if "sarvam-m" in model and effective_max > 2048:
            effective_max = 2048

        # 5. Reasoning effort selection
        reasoning_effort: str | None = kwargs.pop("reasoning_effort", None)
        if not reasoning_effort and model.startswith("sarvam-"):
            op = (operation or "").lower()
            fast_tags = (
                "classification",
                "intent",
                "grade",
                "followup",
                "decompose",
                "tree",
                "hyde",
                "sufficiency",
                "rerank",
                "extraction",
                "summarize",
                "keyword",
                "extract",
            )
            complex_tags = (
                "complex",
                "cove",
                "multi_hop",
                "verify",
                "faithfulness",
                "self_rag",
                "reflect",
            )
            if any(tag in op for tag in fast_tags):
                reasoning_effort = getattr(settings, "sarvam_reasoning_effort_fast", "low")
            elif any(tag in op for tag in complex_tags):
                reasoning_effort = getattr(settings, "sarvam_reasoning_effort_complex", "high")
            else:
                reasoning_effort = getattr(settings, "sarvam_reasoning_effort", "medium")

        payload: dict = {
            "model": model,
            "messages": validated,
            "temperature": temperature,
            "max_tokens": effective_max,
            "stream": stream,
        }
        if reasoning_effort and reasoning_effort in ("low", "medium", "high"):
            payload["reasoning_effort"] = reasoning_effort

        # 5b. Force JSON output for extraction/keyword/structured operations.
        # Sarvam's reasoning model outputs chain-of-thought text instead of raw JSON
        # for keyword extraction prompts, causing LightRAG to fail keyword parsing
        # and burn through the entire pipeline timeout with retries.
        is_structured = kwargs.pop("is_structured", False)
        passed_format = kwargs.pop("response_format", None)
        op_lower = (operation or "").lower()
        wants_json = (
            is_structured
            or passed_format == {"type": "json_object"}
            or any(tag in op_lower for tag in ("extraction", "keyword", "extract"))
        )

        # If wants JSON, and NOT a reasoning model, we force JSON format at API level.
        # If it IS a reasoning model (sarvam-30b/sarvam-105b), forcing JSON format
        # causes reasoning runaway/loops, so we DO NOT force it and instead extract it below.
        is_reasoning_model = "sarvam-30b" in model or "sarvam-105b" in model
        if wants_json and not is_reasoning_model:
            payload["response_format"] = {"type": "json_object"}

        # 6. Retry loop with tenacity
        from tenacity import (
            AsyncRetrying,
            retry_if_not_exception_type,
            stop_after_attempt,
            wait_exponential,
        )

        tracer = None
        if trace is not None:
            tracer = trace.get_tracer("sarvam")

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(kwargs.pop("max_retries", self._max_retries)),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_not_exception_type((NonRetryableError, QuotaExceededError)),
            reraise=True,  # surface the last HTTPStatusError, not tenacity.RetryError (parity with other providers)
            before_sleep=lambda rs: logger.warning(
                f"Sarvam call failed attempt {rs.attempt_number}. Retrying..."
            ),
        ):
            with attempt:
                attempt_num = attempt.retry_state.attempt_number
                # Capture the current key pair under the lock so the header
                # and 429 bookkeeping always agree, even if another call
                # rotates between attempts.
                async with self._key_lock:
                    _current_index = self._key_index
                    _current_key = self._api_key
                # Track which key indices have already returned 429 in this
                # tenacity attempt so we never cycle through them infinitely.
                _tried_key_indices: set[int] = {_current_index}
                if _current_key:
                    headers["api-subscription-key"] = _current_key
                while True:
                    span_ctx = None
                    if tracer is not None:
                        span_ctx = tracer.start_as_current_span(
                            "llm.sarvam.chat",
                            attributes={
                                "llm.provider": "sarvam",
                                "llm.system": "sarvam",
                                "llm.model_name": model,
                                "llm.operation": operation,
                                "llm.request.attempt": attempt_num,
                            },
                        )

                    if span_ctx is not None:
                        span = span_ctx.__enter__()
                    else:
                        span = None

                    try:
                        # Rate limiting
                        rpm_limit = float(os.environ.get("SARVAM_RPM_LIMIT", "60"))
                        if rpm_limit > 0:
                            async with self._rate_limit_lock:
                                now = time.time()
                                elapsed = now - self._last_request_time
                                min_interval = 60.0 / rpm_limit
                                if elapsed < min_interval:
                                    sleep_time = min_interval - elapsed
                                    self._last_request_time = now + sleep_time
                                else:
                                    sleep_time = 0.0
                                    self._last_request_time = now
                            if sleep_time > 0:
                                logger.info(f"Rate limiting: sleeping {sleep_time:.2f}s")
                                await asyncio.sleep(sleep_time)

                        # Execute HTTP call
                        client = await self._get_http_client()
                        resp = await client.post(
                            f"{self._base_url}/chat/completions",
                            headers=headers,
                            json=payload,
                            timeout=self._timeout,
                        )

                        # Self-healing on 400 (tier limit)
                        if resp.status_code == 400:
                            m = re.search(
                                r"exceeds the maximum allowed for .*? for your subscription tier .*?: (\d+)",
                                resp.text,
                            )
                            if m:
                                tier_limit = int(m.group(1))
                                logger.warning(f"Tier limit hit; capping max_tokens → {tier_limit}")
                                self._max_tokens_limit = tier_limit
                                payload["max_tokens"] = tier_limit
                                if span_ctx is not None:
                                    span_ctx.__exit__(None, None, None)
                                continue  # retry immediately within while loop

                        # Self-healing on 422 (context window)
                        if (
                            resp.status_code == 422
                            and "exceeds the model context window" in resp.text
                        ):
                            if payload.get("model") == "sarvam-m":
                                logger.warning(
                                    "Context exceeded on sarvam-m; upgrading → sarvam-30b"
                                )
                                payload["model"] = "sarvam-30b"
                                payload["max_tokens"] = min(payload.get("max_tokens", 4096), 4096)
                                if span_ctx is not None:
                                    span_ctx.__exit__(None, None, None)
                                continue  # retry immediately within while loop
                            else:
                                m = re.search(
                                    r"prompt_tokens \((\d+)\) \+ max_tokens \(\d+\) = \d+ exceeds the model context window of (\d+)",
                                    resp.text,
                                )
                                if m:
                                    prompt_t, window_t = int(m.group(1)), int(m.group(2))
                                    allowed = window_t - prompt_t - 50
                                    if allowed > 0:
                                        logger.warning(
                                            f"Context exceeded; reducing max_tokens → {allowed}"
                                        )
                                        payload["max_tokens"] = allowed
                                        if span_ctx is not None:
                                            span_ctx.__exit__(None, None, None)
                                        continue  # retry immediately within while loop

                        # API key rotation on 429 (rate limit / quota exceeded)
                        if resp.status_code == 429:
                            # The exclusion set guarantees the returned index was
                            # not tried yet this attempt, so no re-check needed.
                            rotated = await self._rotate_api_key(excluded=_tried_key_indices)
                            if rotated:
                                new_index, new_key = rotated
                                _tried_key_indices.add(new_index)
                                headers["api-subscription-key"] = new_key
                                logger.warning("Sarvam 429 — rotated API key, retrying immediately")
                                if span_ctx is not None:
                                    span_ctx.__exit__(None, None, None)
                                continue
                            # All available keys exhausted for this attempt —
                            # fall through to resp.raise_for_status() so tenacity
                            # handles the 429 via its exponential backoff.
                            logger.warning(
                                "Sarvam 429 — all %d API key(s) exhausted for this attempt; "
                                "yielding to tenacity retry",
                                len(self._api_keys),
                            )

                        resp.raise_for_status()

                        data = resp.json()

                        if span is not None:
                            span.set_attribute("http.status_code", resp.status_code)
                            usage = data.get("usage", {})
                            span.set_attribute("llm.token_count.prompt", usage.get("prompt_tokens"))
                            span.set_attribute(
                                "llm.token_count.completion", usage.get("completion_tokens")
                            )
                            span.set_attribute("llm.token_count.total", usage.get("total_tokens"))

                        choice = data.get("choices", [{}])[0]
                        content = (choice.get("message", {}) or {}).get("content", "") or ""
                        reasoning = (choice.get("message", {}) or {}).get(
                            "reasoning_content", ""
                        ) or ""

                        # If user wants JSON, extract from content or reasoning (reasoning as fallback if content is empty)
                        combined_text = content
                        if not combined_text.strip() and reasoning:
                            combined_text = reasoning

                        if wants_json:
                            extracted = self._extract_structured_content(combined_text, operation)
                            if extracted:
                                content = extracted
                            else:
                                content = combined_text
                        else:
                            content = combined_text

                        # Record token usage in cost tracker
                        try:
                            from services.cost_tracker import token_accumulator_var

                            acc = token_accumulator_var.get()
                            if acc is not None:
                                usage = data.get("usage", {})
                                acc.tokens_in += usage.get("prompt_tokens") or 0
                                acc.tokens_out += usage.get("completion_tokens") or 0
                                acc.model = model
                                acc.provider = "sarvam"
                        except Exception as e:
                            logger.warning(f"Failed to record token usage: {e}")

                        if span_ctx is not None:
                            span_ctx.__exit__(None, None, None)

                        return content.strip()
                    except Exception as e:
                        if span_ctx is not None:
                            span_ctx.__exit__(type(e), e, e.__traceback__)
                        raise

        # Should never reach here (tenacity raises after exhaustion)
        return ""  # fallback

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_structured_content(text: str, operation: str) -> Optional[str]:
        if not text:
            return None

        # Markdown code blocks
        blocks = re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)\n```", text, re.DOTALL)
        for block in blocks:
            block_strip = block.strip()
            if not block_strip:
                continue
            if operation in (
                "grading",
                "combined_verify",
                "verify_claims",
                "classification",
                "classification_fallback",
            ):
                try:
                    json.loads(block_strip)
                    return block_strip
                except Exception:
                    try:
                        import json_repair

                        if json_repair.loads(block_strip):
                            return block_strip
                    except Exception as _e:
                        logger.debug("[sarvam gateway] suppressed non-critical error: %s", _e)
            else:
                if operation == "extraction":
                    block_lower = block_strip.lower()
                    if (
                        "<|#|>" in block_strip
                        or "entity" in block_lower
                        or "relation" in block_lower
                        or "\t" in block_strip
                    ):
                        return block_strip
                else:
                    return block_strip

        # Regex JSON fallback
        first_brace, last_brace = text.find("{"), text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            potential = text[first_brace : last_brace + 1]
            try:
                json.loads(potential)
                return potential
            except Exception:
                try:
                    import json_repair

                    repaired = json_repair.repair(potential)
                    if repaired:
                        return repaired
                except Exception as _e:
                    logger.debug("[sarvam gateway] suppressed non-critical error: %s", _e)
                return potential

        first_bracket, last_bracket = text.find("["), text.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            potential = text[first_bracket : last_bracket + 1]
            try:
                json.loads(potential)
                return potential
            except Exception:
                try:
                    import json_repair

                    repaired = json_repair.repair(potential)
                    if repaired:
                        return repaired
                except Exception as _e:
                    logger.debug("[sarvam gateway] suppressed non-critical error: %s", _e)
                return potential

        if operation == "extraction":
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            extracted = [
                line
                for line in lines
                if "<|#|>" in line
                or (
                    line.count('"') >= 4
                    and ("entity" in line.lower() or "relation" in line.lower() or "\t" in line)
                )
            ]
            if extracted:
                return "\n".join(extracted)

        return None

    # ------------------------------------------------------------------
    # OpenTelemetry helpers (stubs when otel unavailable)
    # ------------------------------------------------------------------

    @staticmethod
    def _start_llm_span(model: str, operation: str, attempt: int):
        class FakeSpan:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            pass

        if not _has_otel:
            return FakeSpan()

        tracer = trace.get_tracer("sarvam")
        span = tracer.start_span(f"llm.{operation}")
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.attempt", attempt)
        return span

    @staticmethod
    def _record_span_exception(span, exc: Exception) -> None:
        if _has_otel and span and hasattr(span, "record_exception"):
            span.record_exception(exc)
            span.set_status(trace.status.Status(trace.status.StatusCode.ERROR))  # type: ignore[attr-defined]
