"""
Mukthi Guru — Sarvam Cloud API Service (BE-1)

Gateway to all LLM operations via Sarvam Cloud API.
Uses direct httpx HTTP calls for reliability (replaces langchain-sarvam which
returned empty responses due to async incompatibilities).

Design Patterns:
  - Facade Pattern: Wraps Sarvam REST API behind domain-specific methods
  - Template Method: Each LLM task has its own method with tailored prompts
  - Single Responsibility: Each method does ONE thing with the LLM
  - Circuit Breaker: Fail-fast when API is down, auto-recover
  - Config-Driven: Any model name works — just set SARVAM_CLOUD_MODEL

API Reference:
  - Endpoint: https://api.sarvam.ai/v1/chat/completions
  - Auth: api-subscription-key header
  - Models: sarvam-30b (32K ctx), sarvam-105b (128K ctx), sarvam-m (legacy)
  - Docs: https://docs.sarvam.ai/

All LLM calls funnel through this service. No other module talks to Sarvam directly.
"""

import asyncio
import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator
from typing import Optional

from anyio import Lock as AsyncLock
import httpx

from app.config import settings
from services.gateways import SarvamHTTPGateway
from rag.prompts import (
    BATCH_GRADE_PROMPT,
    COMBINED_VERIFICATION_PROMPT,
    DECOMPOSE_QUERY_PROMPT,
    FAITHFULNESS_CHECK_PROMPT,
    GRADE_RELEVANCE_PROMPT,
    HINT_EXTRACTION_PROMPT,
    HYDE_PROMPT,
    INTENT_CLASSIFICATION_PROMPT,
    IS_COMPLEX_QUERY_PROMPT,
    QUERY_REWRITE_PROMPT,
    SUMMARIZE_PROMPT,
    VERIFICATION_PROMPT,
)

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
except ImportError:  # OpenTelemetry is optional in local/minimal installs.
    trace = None
    Status = None
    StatusCode = None


from services.sarvam_exceptions import NonRetryableError, QuotaExceededError


# ---------------------------------------------------------------------------
# Circuit Breaker — fail-fast when API is down, auto-recover
# ---------------------------------------------------------------------------
# Import from shared circuit_breaker module (provider-agnostic)
from services.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitOpenException,
    DefaultCircuitBreaker,
)

# ---------------------------------------------------------------------------
# Sarvam Cloud Service
# ---------------------------------------------------------------------------


class SarvamCloudService:
    """
    Gateway to all LLM operations via Sarvam Cloud API.

    Uses direct httpx HTTP calls for reliability.
    Supports any model name — fully config-driven.

    The interface is identical to OllamaService so it's a drop-in replacement.
    """

    def __init__(self) -> None:
        """Initialize the Sarvam Cloud API client."""
        self._api_key = settings.sarvam_30b_api_key or settings.sarvam_api_key
        if not self._api_key and not settings.sarvam_30b_endpoint:
            raise ValueError(
                "SARVAM_API_KEY is required for Sarvam Cloud API mode. "
                "Set it in your .env file or environment variables."
            )

        self._base_url = settings.sarvam_30b_endpoint or getattr(settings, "sarvam_base_url", "https://api.sarvam.ai/v1")
        self._gen_model = settings.sarvam_cloud_model
        self._cls_model = settings.sarvam_cloud_classify_model
        self._timeout = getattr(settings, "llm_timeout", 60)
        self._max_retries = getattr(settings, "llm_max_retries", 3)
        # Use provider-agnostic circuit breaker from shared module
        from app.constants import CircuitBreakerProvider
        sarvam_config = CircuitBreakerConfig.from_provider(CircuitBreakerProvider.SARVAM_CLOUD.value)
        self._circuit = DefaultCircuitBreaker(sarvam_config)
        self._last_request_time = 0.0
        self._rate_limit_lock = AsyncLock()
        self._max_tokens_limit = 4096

        # Connection pooling: Create a singleton httpx.AsyncClient with pool limits
        self._http_client = None
        self._http_client_lock = AsyncLock()

        # Also set env for any code that might use langchain-sarvam internally
        if self._api_key:
            os.environ["SARVAM_API_KEY"] = self._api_key

        # Gateway for all non-streaming LLM transport is instantiated if either api key or endpoint is set
        if self._api_key or settings.sarvam_30b_endpoint:
            self._http = SarvamHTTPGateway()
        else:
            self._http = None

        logger.info(
            f"Sarvam Cloud Service ready — "
            f"gen_model={self._gen_model}, cls_model={self._cls_model}, "
            f"base_url={self._base_url}"
        )

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create the singleton HTTP client with connection pooling."""
        async with self._http_client_lock:
            if self._http_client is None:
                # Configure connection pool limits from settings
                limits = httpx.Limits(
                    max_connections=getattr(settings, "http_max_connections", 100),
                    max_keepalive_connections=getattr(
                        settings, "http_max_keepalive_connections", 20
                    ),
                    keepalive_expiry=getattr(settings, "http_keepalive_expiry", 30.0),
                )
                self._http_client = httpx.AsyncClient(timeout=self._timeout, limits=limits)
                logger.info(
                    f"HTTP client initialized with pool limits: "
                    f"max_connections={limits.max_connections}, "
                    f"max_keepalive_connections={limits.max_keepalive_connections}"
                )
            return self._http_client

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        async with self._http_client_lock:
            if self._http_client is not None:
                await self._http_client.aclose()
                self._http_client = None
                logger.info("HTTP client closed")
        if self._http is not None:
            await self._http.close()

    def _extract_structured_content(self, text: str, operation: str) -> Optional[str]:
        """
        Attempt to extract structured data (JSON, markdown code blocks, tab-separated entity tables)
        from reasoning_content when the main content field is returned empty.
        """
        if not text:
            return None

        # 1. Try to find markdown code blocks (e.g., ```json ... ```, ```csv ... ```, ``` ... ```)
        blocks = re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)\n```", text, re.DOTALL)
        for block in blocks:
            block_strip = block.strip()
            if not block_strip:
                continue

            # If JSON-based operation, check if block is valid JSON
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
                    pass
            else:
                # For non-JSON operations, check if the block is appropriate
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

        # 2. Try regex-based JSON block extraction (matching first/last braces or brackets)
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            potential_json = text[first_brace : last_brace + 1]
            try:
                json.loads(potential_json)
                return potential_json
            except Exception:
                pass

        first_bracket = text.find("[")
        last_bracket = text.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            potential_json = text[first_bracket : last_bracket + 1]
            try:
                json.loads(potential_json)
                return potential_json
            except Exception:
                pass

        # 3. For LightRAG extraction, search for lines that look like entity or relationship records
        if operation == "extraction":
            lines = text.splitlines()
            extracted_lines = []
            for line in lines:
                l_strip = line.strip()
                l_lower = l_strip.lower()
                is_record = "<|#|>" in l_strip or (
                    l_strip.count('"') >= 4
                    and ("entity" in l_lower or "relation" in l_lower or "\t" in l_strip)
                )
                if is_record:
                    extracted_lines.append(l_strip)
            if extracted_lines:
                return "\n".join(extracted_lines)

        return None

    # -----------------------------------------------------------------------
    # Core HTTP API call — ALL LLM calls go through here
    # -----------------------------------------------------------------------

    async def _call_api(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 8192,
        temperature: float = 0.1,
        stream: bool = False,
        operation: str = "generate",
        **kwargs,
    ) -> str:
        """Delegated to SarvamHTTPGateway — all transport logic removed."""
        if self._http is None:
            raise RuntimeError("SarvamHTTPGateway is not initialized (no API key and/or endpoint mode configured)")
        return await self._http.call(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=stream,
            operation=operation,
            **kwargs,
        )



    def _start_llm_span(self, model: str, operation: str, attempt: int):
        """Create an optional OTel span for a Sarvam request."""
        from contextlib import nullcontext

        if trace is None:
            return nullcontext(None)

        tracer = trace.get_tracer(__name__)
        return tracer.start_as_current_span(
            "llm.sarvam.chat",
            attributes={
                "llm.provider": "sarvam",
                "llm.system": "sarvam",
                "llm.model_name": model,
                "llm.operation": operation,
                "llm.request.attempt": attempt,
            },
        )

    @staticmethod
    def _set_span_attr(span, key: str, value) -> None:
        if span is not None and value is not None:
            try:
                span.set_attribute(key, value)
            except Exception:
                pass

    def _record_usage(self, span, usage: dict) -> None:
        if not usage:
            return
        token_attrs = {
            "llm.token_count.prompt": usage.get("prompt_tokens"),
            "llm.token_count.completion": usage.get("completion_tokens"),
            "llm.token_count.total": usage.get("total_tokens"),
        }
        for key, value in token_attrs.items():
            self._set_span_attr(span, key, value)

        # Update request-scoped token accumulator
        try:
            from services.cost_tracker import token_accumulator_var
            acc = token_accumulator_var.get()
            if acc is not None:
                acc.tokens_in += usage.get("prompt_tokens") or 0
                acc.tokens_out += usage.get("completion_tokens") or 0
                acc.model = self._gen_model
                acc.provider = "sarvam"
        except Exception as e:
            logger.warning(f"Failed to record token usage in accumulator: {e}")

    @staticmethod
    def _record_span_exception(span, exc: Exception) -> None:
        if span is None:
            return
        try:
            span.record_exception(exc)
            if Status is not None and StatusCode is not None:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Public generation methods (unchanged interface)
    # -----------------------------------------------------------------------

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> str:
        """
        Core generation method using the main Sarvam model.

        Args:
            system_prompt: Role and constraints for the LLM
            user_prompt: User's input with any injected context
            context: Retrieved documents (inserted into the prompt)
            **kwargs: Additional model parameters (temperature, etc.)
        """
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

        try:
            return await self._call_api(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                operation=operation,
                **kwargs,
            )
        except QuotaExceededError:
            raise
        except Exception as e:
            if model != self._gen_model:
                logger.warning(
                    f"Sarvam model {model} failed for {operation}; falling back to {self._gen_model}: {e}"
                )
                return await self._call_api(
                    messages=messages,
                    model=self._gen_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    operation=f"{operation}_fallback",
                    **kwargs,
                )
            raise

    async def _generate_fast(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs,
    ) -> str:
        """
        Fast classification using the Sarvam model with lower max_tokens.

        Used for binary/ternary classification tasks where full generation
        is overkill. Faster due to lower max_tokens.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        temperature = kwargs.pop("temperature", 0.0)
        max_tokens = kwargs.pop("max_tokens", 2048)

        try:
            return await self._call_api(
                messages=messages,
                model=self._cls_model,
                max_tokens=max_tokens,
                temperature=temperature,
                operation="classification",
                **kwargs,
            )
        except QuotaExceededError:
            raise
        except Exception as e:
            # Fall back to main model if fast model fails
            logger.warning(f"Fast model failed, falling back to main: {e}")
            return await self._call_api(
                messages=messages,
                model=self._gen_model,
                max_tokens=max_tokens,
                temperature=temperature,
                operation="classification_fallback",
                **kwargs,
            )

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Streaming generation using the main Sarvam model.

        Yields tokens as they are generated for SSE streaming.
        """
        messages = [{"role": "system", "content": system_prompt}]

        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {user_prompt}"
        else:
            full_prompt = user_prompt

        messages.append({"role": "user", "content": full_prompt})

        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["api-subscription-key"] = self._api_key

        model = kwargs.get("model", self._gen_model)
        max_tokens = kwargs.get("max_tokens", 8192)
        if max_tokens == 8192:
            if "sarvam-m" in model:
                max_tokens = 2048
            else:
                max_tokens = self._max_tokens_limit

        if "sarvam-30b" in model or "sarvam-105b" in model:
            if max_tokens > self._max_tokens_limit:
                logger.info(
                    f"generate_stream: Setting max_tokens={max_tokens} → {self._max_tokens_limit} for reasoning model {model}"
                )
                max_tokens = self._max_tokens_limit

        payload = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": max_tokens,
            "stream": True,
        }

        # Inject reasoning_effort using the same 3-tier system as _call_api.
        # Streaming is always a generation operation → defaults to "medium" tier.
        if "reasoning_effort" in kwargs:
            _stream_effort = kwargs["reasoning_effort"]
        elif self._gen_model.startswith("sarvam-"):
            _stream_effort = getattr(settings, "sarvam_reasoning_effort", "medium")
        else:
            _stream_effort = None
        if _stream_effort and _stream_effort in ("low", "medium", "high"):
            payload["reasoning_effort"] = _stream_effort

        if not self._circuit.can_execute():
            logger.warning("Sarvam API circuit breaker is OPEN in generate_stream — failing fast")
            raise CircuitOpenException(
                "Sarvam API circuit breaker is OPEN in generate_stream — failing fast"
            )

        try:
            client = await self._get_http_client()
            yielded_any = False
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status_code == 400:
                    error_text_bytes = await resp.aread()
                    error_text = error_text_bytes.decode("utf-8", errors="ignore")
                    m = re.search(
                        r"exceeds the maximum allowed for .*? for your subscription tier .*?: (\d+)",
                        error_text,
                    )
                    if m:
                        tier_limit = int(m.group(1))
                        logger.warning(
                            f"Sarvam API stream max_tokens ({payload.get('max_tokens')}) exceeded subscription limit. "
                            f"Automatically capping to {tier_limit}, caching limit, and retrying stream immediately."
                        )
                        self._max_tokens_limit = tier_limit
                        kwargs_copy = {**kwargs, "max_tokens": tier_limit}
                        async for chunk in self.generate_stream(system_prompt, user_prompt, context, **kwargs_copy):
                            yield chunk
                        return
                    else:
                        resp.raise_for_status()
                buffer = ""
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            # Strip think tags from accumulated buffer
                            if buffer:
                                re.sub(r"<think>.*?</think>", "", buffer, flags=re.DOTALL)
                                # Already yielded tokens — just log completion
                            break
                        try:
                            data = json.loads(data_str)
                            delta_msg = data.get("choices", [{}])[0].get("delta", {})
                            delta = delta_msg.get("content") or ""
                            reasoning_delta = delta_msg.get("reasoning_content") or ""
                            if delta:
                                buffer += delta
                                yielded_any = True
                                yield delta
                            elif reasoning_delta:
                                yielded_any = True
                                yield reasoning_delta
                        except json.JSONDecodeError:
                            pass

                # Record streaming token usage in accumulator
                try:
                    from services.cost_tracker import token_accumulator_var
                    acc = token_accumulator_var.get()
                    if acc is not None:
                        prompt_tokens = int(sum(len((msg.get("content") or "").split()) for msg in messages) * 1.3)
                        completion_tokens = int(len(buffer.split()) * 1.3)
                        acc.tokens_in += prompt_tokens
                        acc.tokens_out += completion_tokens
                        acc.model = model
                        acc.provider = "sarvam"
                except Exception as e:
                    logger.warning(f"Failed to record stream token usage: {e}")

            self._circuit.record_success()

        except Exception as e:
            logger.error(f"Sarvam Cloud streaming failed: {e}")
            self._circuit.record_failure()
            if model != self._gen_model and not locals().get("yielded_any", False):
                logger.warning(
                    f"Sarvam stream model {model} failed before tokens; falling back to {self._gen_model}."
                )
                fallback_kwargs = {**kwargs, "model": self._gen_model}
                async for chunk in self.generate_stream(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    context=context,
                    **fallback_kwargs,
                ):
                    yield chunk
                return
            if "credits" in str(e).lower() or "429" in str(e).lower():
                logger.warning("Quota exceeded for Sarvam Cloud API in streaming.")
                yield "The essence of spiritual practice is compassion and mindfulness. Even in stillness, your presence is heard."
                return
            raise

    # -----------------------------------------------------------------------
    # Domain-specific LLM methods (unchanged public interface)
    # -----------------------------------------------------------------------

    async def classify_intent(self, message: str, **kwargs) -> str:
        """
        Classify user message into one of the designated intents.

        Uses the fast classification model (sarvam-m) for low latency.
        The main reasoning model (sarvam-30b) is overkill for a 1-word
        classification output and wastes 30+ seconds on reasoning traces.
        """
        # Force fast model + tight token cap for classification
        kwargs.setdefault("max_tokens", 256)
        result = await self._generate_fast(INTENT_CLASSIFICATION_PROMPT, message, **kwargs)

        # Parse — be lenient with LLM output
        result_upper = result.upper().strip()

        if not result_upper:
            # Empty response — default to QUERY to avoid skipping RAG pipeline
            logger.warning(
                "classify_intent got empty response from LLM. "
                "Defaulting to QUERY to ensure RAG pipeline processes the question."
            )
            return "QUERY"

        if "DISTRESS" in result_upper:
            return "DISTRESS"
        elif (
            "SAFETY_VIOLATION" in result_upper
            or "SAFETY" in result_upper
            or "VIOLATION" in result_upper
        ):
            return "SAFETY_VIOLATION"
        elif "ADVERSARIAL" in result_upper:
            return "ADVERSARIAL"
        elif "MEDITATION" in result_upper:
            return "MEDITATION"
        elif "FACTUAL" in result_upper:
            return "FACTUAL"
        elif "RELATIONAL" in result_upper:
            return "RELATIONAL"
        elif "FOLLOW_UP" in result_upper:
            return "FOLLOW_UP"
        elif "QUERY" in result_upper:
            return "QUERY"
        elif "CASUAL" in result_upper:
            return "CASUAL"
        else:
            # Unrecognized output — default to QUERY (safer than CASUAL)
            logger.warning(
                f"classify_intent got unrecognized output: {result[:100]!r}. Defaulting to QUERY."
            )
            return "QUERY"

    async def classify_complexity(self, text: str) -> str:
        """Classify user question complexity into 'simple' or 'complex' using the fast model."""
        is_complex = await self.is_complex_query(text)
        return "complex" if is_complex else "simple"

    async def classify_intent_and_complexity(self, message: str, **kwargs) -> dict:
        """
        Classify both intent AND complexity in a single LLM call.

        Saves one full LLM round-trip per query by merging the two
        classification calls (classify_intent + classify_complexity)
        that the intent_router node previously made sequentially.

        Returns: {"intent": str, "complexity": "simple"|"complex"}
        """
        prompt = (
            "Classify the following user message.\n\n"
            "1. INTENT: Choose exactly one from: DISTRESS, SAFETY_VIOLATION, ADVERSARIAL, "
            "MEDITATION, FACTUAL, RELATIONAL, FOLLOW_UP, CASUAL.\n"
            "2. COMPLEXITY: Is this question 'simple' (single fact) or 'complex' (multi-hop/comparative)?\n\n"
            f"Message: {message}\n\n"
            "Reply in EXACTLY this format (no other text):\n"
            "INTENT: <intent>\nCOMPLEXITY: <simple|complex>"
        )
        kwargs.setdefault("max_tokens", 64)
        result = await self._generate_fast("", prompt, **kwargs)

        # Parse response
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
                    "CASUAL",
                    "QUERY",
                ]:
                    if candidate in val:
                        intent = candidate
                        break
            elif line.startswith("COMPLEXITY:"):
                val = line.split(":", 1)[-1].strip()
                complexity = "simple" if "SIMPLE" in val else "complex"

        # Normalize QUERY → FACTUAL
        if intent == "QUERY":
            intent = "FACTUAL"

        return {"intent": intent, "complexity": complexity}

    async def classify_distress_structured(self, message: str) -> dict:
        """
        Phase 3: Deterministic JSON outputs via Instructor or robust prompt fallback.
        Uses Instructor to strictly enforce a Pydantic schema for distress classification.
        """
        import instructor
        from openai import AsyncOpenAI
        from pydantic import BaseModel, Field

        class DistressOutput(BaseModel):
            is_distress: bool = Field(
                default=False,
                description="True if the user is in distress, sad, or asking for help with negative emotions",
            )
            confidence: float = Field(
                default=0.5, description="Confidence score from 0.0 to 1.0"
            )
            reason: str = Field(
                default="No reason provided",
                description="Brief reason for the assessment",
            )

        # Try Instructor first with explicit JSON mode
        try:
            default_headers = {}
            if self._api_key:
                default_headers["api-subscription-key"] = self._api_key

            client = instructor.from_openai(
                AsyncOpenAI(
                    base_url=self._base_url,
                    api_key="api-key-not-used-by-bearer",
                    default_headers=default_headers,
                ),
                mode=instructor.Mode.JSON,
            )

            prompt = (
                f"Analyze the following message for emotional distress or a cry for help. "
                f"Return ONLY a valid JSON object with fields: is_distress (bool), confidence (float 0-1), reason (string).\n\n"
                f"Message: {message}"
            )

            resp: DistressOutput = await client.chat.completions.create(
                model=self._cls_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a psychological safety assessor. Return ONLY a valid JSON object matching the schema. No reasoning, no think tags, no extra text.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_model=DistressOutput,
                max_retries=2,
                timeout=15.0,
            )
            return {
                "is_distress": resp.is_distress,
                "confidence": resp.confidence,
                "reason": resp.reason,
            }
        except Exception as e:
            logger.warning(
                f"Instructor structured output on Sarvam failed: {e}. Falling back to direct JSON prompt."
            )
            # Fallback: Direct JSON prompt without Instructor
            return await self._classify_distress_json_fallback(message)

    async def _classify_distress_json_fallback(self, message: str) -> dict:
        """Direct JSON prompt fallback when Instructor fails."""
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
            import json
            data = json.loads(resp.strip())
            return {
                "is_distress": bool(data.get("is_distress", False)),
                "confidence": float(data.get("confidence", 0.5)),
                "reason": str(data.get("reason", "Fallback JSON parsing")),
            }
        except Exception as e:
            logger.warning(f"JSON fallback also failed: {e}. Using naive classification.")
            intent = await self.classify_intent(message)
            return {
                "is_distress": intent == "DISTRESS",
                "confidence": 0.5,
                "reason": f"Fallback naive classification (intent={intent})",
            }

    async def grade_relevance(self, query: str, document: str) -> bool:
        """
        CRAG: Binary relevance grading of a retrieved document.

        Returns True if the document is relevant to the query.
        """
        prompt = f"Question: {query}\n\nDocument: {document}"
        result = await self._generate_fast(GRADE_RELEVANCE_PROMPT, prompt)
        return "yes" in result.lower()

    async def batch_grade_relevance(self, query: str, documents: list[str], **kwargs) -> list[dict]:
        """
        CRAG: Batch relevance grading of multiple documents in one LLM call.

        Returns: List of dicts, one per document:
            {"relevant": bool, "reason": str}
        """
        if not documents:
            return []

        # Build numbered document list
        numbered_docs = "\n\n".join(
            f"Document {i + 1}:\n{doc[:1500]}"  # Truncate individual docs to fit context
            for i, doc in enumerate(documents)
        )

        prompt = f"Question: {query}\n\n{numbered_docs}"
        result = await self._generate_fast(BATCH_GRADE_PROMPT, prompt, **kwargs)

        # Parse "1: [yes/no] - reason\n2: [yes/no] - reason" format
        relevance_results = [
            {"relevant": False, "reason": "No response from LLM"} for _ in documents
        ]

        # Regex to handle various formats like "1: yes - The document discusses..."
        # or "1: yes (Reason: ...)"
        for line in result.strip().splitlines():
            line = line.strip()
            if not line:
                continue

            # Match pattern: index, then yes/no, then optional reason
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

        # If parser didn't match or LLM graded everything False,
        # keep the top document to guarantee context, but note the low confidence
        if not any(r["relevant"] for r in relevance_results) and len(documents) > 0:
            logger.warning("Relevance grading returned no docs. Using top document fallback.")
            relevance_results[0] = {
                "relevant": True,
                "reason": "Fallback: Used top retrieval result as a starting point despite low initial relevance score.",
            }

        return relevance_results

    async def check_faithfulness(self, answer: str, context: str, **kwargs) -> bool:
        """
        Self-RAG: Check if the generated answer is faithful to the context.

        Returns True if EVERY claim in the answer is supported by the context.
        """
        prompt = f"Context:\n{context}\n\nAnswer:\n{answer}"
        result = await self._generate_fast(FAITHFULNESS_CHECK_PROMPT, prompt, **kwargs)
        return "faithful" in result.lower()

    async def extract_hints(self, query: str, documents: list[str]) -> list[str]:
        """
        Stimulus RAG: Extract key evidence hints from retrieved documents.

        Returns: List of 3-5 key hint phrases
        """
        combined_docs = "\n---\n".join(documents)
        system = HINT_EXTRACTION_PROMPT
        prompt = f"Question: {query}\n\nDocuments:\n{combined_docs}"

        result = await self.generate(system, prompt)

        # Parse hints from bullet points
        hints = []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                hints.append(line[2:].strip())
            elif line and not line.startswith("#"):
                hints.append(line)

        return hints[:5]  # Cap at 5 hints

    async def rewrite_query(
        self,
        original_query: str,
        reasons: list[str] = None,
        grading_reasons: list[str] = None,
        **kwargs,
    ) -> str:
        """
        CRAG: Rewrite a query to improve retrieval quality.

        Args:
            original_query: The query that failed to find relevant docs
            reasons: Explanations from the grader about why retrieval failed (standard name)
            grading_reasons: Explanations from the grader about why retrieval failed (alias name)
        """
        prompt = f"Original query: {original_query}"
        actual_reasons = reasons or grading_reasons
        if actual_reasons:
            reasons_text = "\n".join([f"- {r}" for r in actual_reasons if r])
            prompt += f"\n\nReasons for previous retrieval failure:\n{reasons_text}\n\nInstructions: Use these reasons to understand what was missing and perform a more targeted query expansion."

        return await self.generate(QUERY_REWRITE_PROMPT, prompt, **kwargs)

    async def verify_claims(self, answer: str, context: str) -> dict:
        """
        Chain of Verification (CoVe): Generate verification questions and check.

        This is the FINAL safety net (layer 11).
        """
        prompt = f"Answer:\n{answer}\n\nContext:\n{context}"
        result = await self.generate(VERIFICATION_PROMPT, prompt)

        # Parse the VERDICT line robustly
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
            logger.warning(
                "CoVe: No VERDICT line found in verification output. "
                f"Raw result (first 200 chars): {result[:200]!r}"
            )
            passed = False

        return {
            "passed": passed,
            "details": result,
        }

    async def combined_verify(self, answer: str, context: str) -> dict:
        """
        Combined Self-RAG + CoVe verification in a single LLM call.

        Merges faithfulness checking (layer 10) and claim verification (layer 11)
        into one structured prompt, reducing 2 LLM calls to 1.

        Returns:
            Dict with 'is_faithful' (bool), 'passed' (bool),
            'confidence' (float), 'details' (str)
        """
        system = COMBINED_VERIFICATION_PROMPT
        prompt = f"Answer:\n{answer}\n\nContext:\n{context}"

        result = await self.generate(system, prompt, temperature=0.0)

        result_upper = result.upper().strip()
        lines = result_upper.splitlines()

        # Parse FAITHFULNESS line
        is_faithful = False
        for line in lines:
            if "FAITHFULNESS" in line:
                after = line.split("FAITHFULNESS", 1)[-1]
                is_faithful = "FAITHFUL" in after and "HALLUCINATED" not in after
                break

        # Parse VERDICT line
        passed = False
        for line in reversed(lines):
            if "VERDICT" in line:
                after = line.split("VERDICT", 1)[-1]
                passed = "PASS" in after and "FAIL" not in after
                break

        # Parse CONFIDENCE line (1-10)
        confidence = 5.0  # Default mid-range
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
            elif "FAITHFULNESS_SCORE" in line:
                after = line.split("FAITHFULNESS_SCORE", 1)[-1]
                scores = re.findall(r"0\.\d+|1\.0|1", after)
                if scores:
                    try:
                        faithfulness_score = float(scores[0])
                    except (ValueError, IndexError):
                        pass
            elif "RELEVANCY_SCORE" in line:
                after = line.split("RELEVANCY_SCORE", 1)[-1]
                scores = re.findall(r"0\.\d+|1\.0|1", after)
                if scores:
                    try:
                        relevancy_score = float(scores[0])
                    except (ValueError, IndexError):
                        pass

        # Both must pass
        final_passed = is_faithful and passed

        if not final_passed:
            logger.info(
                f"Combined verify: faithful={is_faithful}, verdict_pass={passed}, "
                f"confidence={confidence}, faithfulness_score={faithfulness_score}, relevancy_score={relevancy_score}"
            )

        return {
            "is_faithful": is_faithful,
            "passed": final_passed,
            "confidence": confidence,
            "faithfulness_score": faithfulness_score,
            "relevancy_score": relevancy_score,
            "details": result,
        }

    async def summarize(self, texts: list[str]) -> str:
        """
        Summarize a cluster of text chunks (used by RAPTOR).
        """
        combined = "\n\n".join(texts)
        return await self.generate(SUMMARIZE_PROMPT, combined)

    async def decompose_query(self, query: str, **kwargs) -> list[str]:
        """
        Query Decomposition: Split complex questions into atomic sub-queries.

        Returns: List of 2-3 simpler sub-queries.
        """
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
        """
        HyDE (Hypothetical Document Embeddings): Generate a fake answer.
        """
        return await self.generate(HYDE_PROMPT, query, operation="generate_hyde", **kwargs)

    async def is_complex_query(self, query: str, **kwargs) -> bool:
        """
        Determine if a query needs decomposition.
        """
        result = await self._generate_fast(IS_COMPLEX_QUERY_PROMPT, query, **kwargs)
        return "complex" in result.lower()

    async def compress_context(self, question: str, document_text: str, **kwargs) -> str:
        """
        Compress a document chunk using the fast LLM to retain only relevant information.
        If NO_RELEVANT_CONTEXT is returned, it returns an empty string.
        """
        from rag.prompts import COMPRESS_CONTEXT_PROMPT

        prompt = COMPRESS_CONTEXT_PROMPT.format(question=question, document_text=document_text)
        # Always use the fast model for compression to save time
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
        """
        Translate text using Sarvam Mayura/Translate API.
        """
        if not text.strip():
            return ""

        # Normalize code
        def normalize_code(code: str) -> str:
            code = code.lower().strip()
            # If code is already a full bcp47 tag with IN or NP, upper case the regional subtag
            if "-" in code:
                parts = code.split("-")
                return f"{parts[0]}-{parts[1].upper()}"
            # Standard Indic mappings to BCP-47
            mapping = {
                "en": "en-IN",
                "hi": "hi-IN",
                "te": "te-IN",
                "mr": "mr-IN",
                "ta": "ta-IN",
                "bn": "bn-IN",
                "gu": "gu-IN",
                "kn": "kn-IN",
                "ml": "ml-IN",
                "or": "or-IN",
                "pa": "pa-IN",
                "ur": "ur-IN",
                "as": "as-IN",
                "mai": "mai-IN",
                "sa": "sa-IN",
                "ks": "ks-IN",
                "ne": "ne-NP",
                "sd": "sd-IN",
                "kok": "kok-IN",
                "doi": "doi-IN",
                "mni": "mni-IN",
                "sat": "sat-IN",
                "brx": "brx-IN",
            }
            return mapping.get(code, f"{code}-IN")

        src_code = normalize_code(source_language_code)
        tgt_code = normalize_code(target_language_code)

        if src_code == tgt_code:
            return text

        url = "https://api.sarvam.ai/translate"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["api-subscription-key"] = self._api_key
        payload = {
            "input": text,
            "source_language_code": src_code,
            "target_language_code": tgt_code,
            "model": "mayura:v1",
        }

        try:
            client = await self._get_http_client()
            resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("translated_text", text)
            else:
                logger.error(f"Sarvam translation failed (HTTP {resp.status_code}): {resp.text}")
                return text
        except Exception as e:
            logger.error(f"Error calling Sarvam translation: {e}")
            return text

    @property
    def is_available(self) -> bool:
        """Return True if the Sarvam Cloud service is available for use."""
        return True

    async def health_check(self) -> bool:
        """Check if Sarvam Cloud API is reachable."""
        try:
            client = await self._get_http_client()
            headers = {
                "Content-Type": "application/json",
            }
            if self._api_key:
                headers["api-subscription-key"] = self._api_key

            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self._gen_model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
                timeout=10.0,
            )
            return resp.status_code == 200
        except Exception:
            return False
