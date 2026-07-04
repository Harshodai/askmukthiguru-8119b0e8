"""
Mukthi Guru — Nvidia NIM Service

Gateway to all LLM operations via Nvidia NIM hosted API Catalog.
Uses direct httpx to the OpenAI-compatible /v1/chat/completions endpoint.
https://integrate.api.nvidia.com/v1
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any, Optional

from anyio import Lock as AsyncLock
import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.constants import CircuitBreakerProvider
from services.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitOpenException,
    DefaultCircuitBreaker,
)
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
    INTENT_AND_COMPLEXITY_PROMPT,
    QUERY_REWRITE_PROMPT,
    SUMMARIZE_PROMPT,
    VERIFICATION_PROMPT,
    COMPRESS_CONTEXT_PROMPT,
)

logger = logging.getLogger(__name__)


class NimService:
    """Gateway to all LLM operations via Nvidia NIM hosted API."""

    def __init__(self) -> None:
        self._api_key = settings.nim_api_key
        self._base_url = settings.nim_base_url
        self._gen_model = settings.nim_generation_model
        self._cls_model = settings.nim_classify_model
        self._timeout = getattr(settings, "llm_timeout", 60)
        self._max_retries = getattr(settings, "llm_max_retries", 3)
        self._rpm_limit = max(1, settings.nim_rpm_limit)

        config = CircuitBreakerConfig.from_provider(CircuitBreakerProvider.NIM.value)
        self._circuit = DefaultCircuitBreaker(config)

        self._rpm_lock = AsyncLock()
        self._request_count = 0
        self._window_start = time.time()

        self._http_client: Optional[httpx.AsyncClient] = None
        self._http_client_lock = AsyncLock()

        logger.info(
            f"NIM Service initialized: "
            f"gen_model={self._gen_model}, cls_model={self._cls_model}, "
            f"base_url={self._base_url}"
        )

    async def _get_http_client(self) -> httpx.AsyncClient:
        async with self._http_client_lock:
            if self._http_client is None:
                limits = httpx.Limits(
                    max_connections=getattr(settings, "http_max_connections", 100),
                    max_keepalive_connections=getattr(settings, "http_max_keepalive_connections", 20),
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
        async with self._http_client_lock:
            if self._http_client is not None:
                await self._http_client.aclose()
                self._http_client = None
                logger.info("NIM HTTP client closed")

    async def _enforce_rate_limit(self) -> None:
        now = time.time()
        async with self._rpm_lock:
            if now - self._window_start >= 60:
                self._window_start = now
                self._request_count = 0
            if self._request_count >= self._rpm_limit:
                delay = 60.0 - (now - self._window_start)
                if delay > 0:
                    logger.warning(f"NIM rate limit hit — sleeping {delay:.1f}s")
                    await asyncio.sleep(delay)
                    self._window_start = time.time()
                    self._request_count = 0
            self._request_count += 1

    async def _record_rate_limit_response(self) -> None:
        now = time.time()
        async with self._rpm_lock:
            self._request_count = self._rpm_limit
            delay = 60.0 - (now - self._window_start)
            logger.warning(f"NIM returned 429 — rate limiter exhausted for {delay:.1f}s")

    async def _graceful_degradation(self, messages: list[dict], operation: str = "fallback") -> str:
        logger.warning(f"Using graceful degradation for {operation}")
        last_msg = messages[-1]["content"] if messages else ""
        is_question = any(last_msg.lower().startswith(q) for q in ["what", "how", "who", "where", "why", "when", "can", "do", "is", "are"])
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
        if not text:
            return 0
        return int(len(text.split()) * 1.3)

    def _track_token_usage(self, *, tokens_in: int, tokens_out: int, model: str) -> None:
        try:
            from services.cost_tracker import token_accumulator_var
            acc = token_accumulator_var.get()
            if acc is not None:
                acc.tokens_in += tokens_in
                acc.tokens_out += tokens_out
                acc.model = model
                acc.provider = "nim"
        except Exception as exc:
            logger.warning(f"Failed to record NIM token usage: {exc}")

    async def _call_api(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        operation: str = "generate",
        **kwargs,
    ) -> str:
        await self._enforce_rate_limit()

        if not self._circuit.can_execute():
            logger.warning(f"NIM circuit breaker open — graceful degradation for {operation}")
            return await self._graceful_degradation(messages, operation=operation)

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        for param in ["top_p", "frequency_penalty", "presence_penalty"]:
            if param in kwargs:
                payload[param] = kwargs[param]

        async def _execute():
            client = await self._get_http_client()
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            return resp.json()

        try:
            retryer = AsyncRetrying(
                stop=stop_after_attempt(self._max_retries),
                wait=wait_exponential(multiplier=1, min=1, max=8),
                retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
                reraise=True,
            )

            data = None
            async for attempt in retryer:
                with attempt:
                    data = await _execute()

            self._circuit.record_success()

            if not data or "choices" not in data or not data["choices"]:
                raise ValueError("Empty or invalid response from NIM API")

            message_data = data["choices"][0]["message"]
            content = message_data.get("content") or message_data.get("reasoning_content") or ""

            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens") or self._estimate_tokens(str(messages))
            tokens_out = usage.get("completion_tokens") or self._estimate_tokens(content)
            self._track_token_usage(tokens_in=tokens_in, tokens_out=tokens_out, model=model)

            return content

        except Exception as exc:
            is_rate_limit = (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code == 429
            )
            is_connection_error = isinstance(exc, (httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException))
            if is_rate_limit or is_connection_error:
                if is_rate_limit:
                    await self._record_rate_limit_response()
                reason = "rate limited (429)" if is_rate_limit else type(exc).__name__
                logger.warning(f"NIM {reason} during {operation} — graceful degradation")
                return await self._graceful_degradation(messages, operation=operation)
            self._circuit.record_failure()
            logger.error(f"NIM call failed during {operation} (model={model}): {exc}")
            raise

    async def _call_api_stream(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        operation: str = "generate_stream",
        **kwargs,
    ) -> AsyncIterator[str]:
        await self._enforce_rate_limit()

        if not self._circuit.can_execute():
            yield "I'm currently experiencing a temporary connectivity issue. Please try again."
            return

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        try:
            client = await self._get_http_client()
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(chunk)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as exc:
            logger.warning(f"NIM stream error during {operation}: {exc}")
            yield ""

    # ------------------------------------------------------------------#
    # Public Generation Methods
    # ------------------------------------------------------------------#

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> str:
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

        return await self._call_api(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            operation=operation,
            **kwargs,
        )

    async def _generate_fast(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs,
    ) -> str:
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
        )

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> AsyncIterator[str]:
        messages = [{"role": "system", "content": system_prompt}]
        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {user_prompt}"
        else:
            full_prompt = user_prompt
        messages.append({"role": "user", "content": full_prompt})

        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 4096)
        model = kwargs.pop("model", self._gen_model)

        async for token in self._call_api_stream(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            yield token

    # ------------------------------------------------------------------#
    # Classification & Analysis
    # ------------------------------------------------------------------#

    async def classify_intent(self, message: str, **kwargs) -> str:
        messages = [
            {"role": "system", "content": INTENT_CLASSIFICATION_PROMPT},
            {"role": "user", "content": message},
        ]
        return await self._call_api(
            messages=messages,
            model=self._cls_model,
            max_tokens=50,
            temperature=0.0,
            operation="classify_intent",
        )

    async def classify_intent_and_complexity(self, message: str, **kwargs) -> dict[str, str]:
        messages = [
            {"role": "system", "content": INTENT_AND_COMPLEXITY_PROMPT},
            {"role": "user", "content": message},
        ]
        raw = await self._call_api(
            messages=messages,
            model=self._cls_model,
            max_tokens=64,
            temperature=0.0,
            operation="classify_intent_and_complexity",
        )
        result_upper = raw.upper().strip()
        
        # Robust fallback for JSON formatted responses (e.g. from mock tests)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                intent_raw = parsed.get("intent")
                intent = str(intent_raw).upper() if intent_raw is not None else "FACTUAL"
                complexity_raw = parsed.get("complexity")
                complexity = str(complexity_raw).lower() if complexity_raw is not None else "complex"
                if intent == "QUERY":
                    intent = "FACTUAL"
                return {"intent": intent, "complexity": complexity}
        except (json.JSONDecodeError, TypeError):
            pass

        lines = result_upper.splitlines()

        intent = "FACTUAL"
        complexity = "complex"

        for line in lines:
            line = line.strip()
            if line.startswith("INTENT:"):
                val = line.split(":", 1)[-1].strip()
                for candidate in ["DISTRESS", "SAFETY_VIOLATION", "ADVERSARIAL", "MEDITATION", "FACTUAL", "RELATIONAL", "FOLLOW_UP", "CASUAL", "QUERY"]:
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
        from services.serene_mind_service import DISTRESS_CLASSIFICATION_SYSTEM_PROMPT
        messages = [
            {"role": "system", "content": DISTRESS_CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
        raw = await self._call_api(
            messages=messages,
            model=self._cls_model,
            max_tokens=200,
            temperature=0.0,
            operation="classify_distress",
        )
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {"distress_level": "none", "reason": "parse_failed"}

    # ------------------------------------------------------------------#
    # Retrieval & Grading
    # ------------------------------------------------------------------#

    async def batch_grade_relevance(self, query: str, documents: list[str], **kwargs) -> list[dict]:
        results = []
        for doc in documents:
            messages = [
                {"role": "system", "content": GRADE_RELEVANCE_PROMPT},
                {"role": "user", "content": f"Query: {query}\nDocument: {doc}"},
            ]
            raw = await self._call_api(
                messages=messages,
                model=self._cls_model,
                max_tokens=50,
                temperature=0.0,
                operation="grade_relevance",
            )
            try:
                score = float(raw.strip())
            except (ValueError, TypeError):
                score = 0.0
            results.append({"score": score, "text": doc})
        return results

    async def check_faithfulness(self, answer: str, context: str, **kwargs) -> bool:
        messages = [
            {"role": "system", "content": FAITHFULNESS_CHECK_PROMPT},
            {"role": "user", "content": f"Answer: {answer}\nContext: {context}"},
        ]
        raw = await self._call_api(
            messages=messages,
            model=self._cls_model,
            max_tokens=10,
            temperature=0.0,
            operation="check_faithfulness",
        )
        return "yes" in raw.strip().lower()

    async def extract_hints(self, query: str, documents: list[str]) -> list[str]:
        messages = [
            {"role": "system", "content": HINT_EXTRACTION_PROMPT},
            {"role": "user", "content": f"Query: {query}\nDocuments: {documents}"},
        ]
        raw = await self._call_api(
            messages=messages,
            model=self._cls_model,
            max_tokens=300,
            temperature=0.0,
            operation="extract_hints",
        )
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    async def rewrite_query(self, original_query: str, reasons: Optional[list[str]] = None, **kwargs) -> str:
        reasons_text = f"Reasons: {reasons}" if reasons else ""
        messages = [
            {"role": "system", "content": QUERY_REWRITE_PROMPT},
            {"role": "user", "content": f"Original query: {original_query}\n{reasons_text}"},
        ]
        return await self._call_api(
            messages=messages,
            model=self._cls_model,
            max_tokens=256,
            temperature=0.3,
            operation="rewrite_query",
        )

    # ------------------------------------------------------------------#
    # Verification
    # ------------------------------------------------------------------#

    async def verify_claims(self, answer: str, context: str) -> dict:
        messages = [
            {"role": "system", "content": VERIFICATION_PROMPT},
            {"role": "user", "content": f"Answer: {answer}\nContext: {context}"},
        ]
        raw = await self._call_api(
            messages=messages,
            model=self._cls_model,
            max_tokens=300,
            temperature=0.0,
            operation="verify_claims",
        )
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {"verified": False, "details": "parse_failed"}

    async def combined_verify(self, answer: str, context: str) -> dict:
        messages = [
            {"role": "system", "content": COMBINED_VERIFICATION_PROMPT},
            {"role": "user", "content": f"Answer: {answer}\nContext: {context}"},
        ]
        raw = await self._call_api(
            messages=messages,
            model=self._cls_model,
            max_tokens=300,
            temperature=0.0,
            operation="combined_verify",
        )
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {"verified": False, "faithful": False, "issues": ["parse_failed"]}

    # ------------------------------------------------------------------#
    # Summarization & Decomposition
    # ------------------------------------------------------------------#

    async def summarize(self, texts: list[str]) -> str:
        combined = "\n".join(texts)
        messages = [
            {"role": "system", "content": SUMMARIZE_PROMPT},
            {"role": "user", "content": f"Texts:\n{combined}"},
        ]
        return await self._call_api(
            messages=messages,
            model=self._gen_model,
            max_tokens=1024,
            temperature=0.3,
            operation="summarize",
        )

    async def decompose_query(self, query: str, **kwargs) -> list[str]:
        messages = [
            {"role": "system", "content": DECOMPOSE_QUERY_PROMPT},
            {"role": "user", "content": query},
        ]
        raw = await self._call_api(
            messages=messages,
            model=self._gen_model,
            max_tokens=512,
            temperature=0.0,
            operation="decompose_query",
        )
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return [query]

    async def generate_hypothetical_answer(self, query: str, **kwargs) -> str:
        messages = [
            {"role": "system", "content": HYDE_PROMPT},
            {"role": "user", "content": query},
        ]
        return await self._call_api(
            messages=messages,
            model=self._gen_model,
            max_tokens=512,
            temperature=0.3,
            operation="generate_hypothetical_answer",
        )

    async def compress_context(self, question: str, document_text: str, **kwargs) -> str:
        messages = [
            {"role": "system", "content": COMPRESS_CONTEXT_PROMPT},
            {"role": "user", "content": f"Question: {question}\nDocument: {document_text}"},
        ]
        return await self._call_api(
            messages=messages,
            model=self._gen_model,
            max_tokens=1024,
            temperature=0.2,
            operation="compress_context",
        )

    async def translate_text(self, text: str, source_language_code: str, target_language_code: str) -> str:
        system_prompt = f"Translate the following text from {source_language_code} to {target_language_code}. Return only the translation, no explanations."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
        return await self._call_api(
            messages=messages,
            model=self._gen_model,
            max_tokens=2048,
            temperature=0.1,
            operation="translate",
        )

    # ------------------------------------------------------------------#
    # Health & Availability
    # ------------------------------------------------------------------#

    @property
    def is_available(self) -> bool:
        return bool(self._api_key) and self._circuit.can_execute()

    async def health_check(self) -> bool:
        try:
            client = await self._get_http_client()
            resp = await client.get("/models", timeout=10.0)
            return resp.status_code == 200
        except Exception as exc:
            logger.warning(f"NIM health check failed: {exc}")
            return False
