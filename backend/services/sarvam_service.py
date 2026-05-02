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

import logging
import os
import re
import time
import asyncio
import json
from typing import Optional, AsyncIterator
from enum import Enum
from dataclasses import dataclass, field

import httpx

from app.config import settings
from rag.prompts import (
    INTENT_CLASSIFICATION_PROMPT,
    GRADE_RELEVANCE_PROMPT,
    FAITHFULNESS_CHECK_PROMPT,
    HINT_EXTRACTION_PROMPT,
    QUERY_REWRITE_PROMPT,
    VERIFICATION_PROMPT,
    SUMMARIZE_PROMPT,
    DECOMPOSE_QUERY_PROMPT,
    HYDE_PROMPT,
    IS_COMPLEX_QUERY_PROMPT,
    BATCH_GRADE_PROMPT,
    COMBINED_VERIFICATION_PROMPT,
)

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """Raised when the Sarvam Cloud API has exceeded its quota/credits."""
    pass


# ---------------------------------------------------------------------------
# Circuit Breaker — fail-fast when API is down, auto-recover
# ---------------------------------------------------------------------------

class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing — reject requests immediately
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreaker:
    """Lightweight circuit breaker for Sarvam API calls."""
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    # Mutable state — use field(default_factory)
    _failures: int = field(default=0, repr=False)
    _last_failure_time: Optional[float] = field(default=None, repr=False)
    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _half_open_calls: int = field(default=0, repr=False)

    def can_execute(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if time.time() - (self._last_failure_time or 0) > self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info("Circuit breaker → HALF_OPEN (testing recovery)")
                return True
            return False
        # HALF_OPEN
        return self._half_open_calls < self.half_open_max_calls

    def record_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                self._state = CircuitState.CLOSED
                self._failures = 0
                logger.info("Circuit breaker → CLOSED (recovered)")
        else:
            self._failures = max(0, self._failures - 1)

    def record_failure(self):
        self._failures += 1
        self._last_failure_time = time.time()
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning("Circuit breaker → OPEN (failed during half-open)")
        elif self._failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker → OPEN (threshold={self.failure_threshold} reached)"
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
        self._api_key = settings.sarvam_api_key
        if not self._api_key:
            raise ValueError(
                "SARVAM_API_KEY is required for Sarvam Cloud API mode. "
                "Set it in your .env file or environment variables."
            )

        self._base_url = getattr(settings, 'sarvam_base_url', 'https://api.sarvam.ai/v1')
        self._gen_model = settings.sarvam_cloud_model
        self._cls_model = settings.sarvam_cloud_classify_model
        self._timeout = getattr(settings, 'llm_timeout', 60)
        self._max_retries = getattr(settings, 'llm_max_retries', 3)
        self._circuit = CircuitBreaker()

        # Also set env for any code that might use langchain-sarvam internally
        os.environ["SARVAM_API_KEY"] = self._api_key

        logger.info(
            f"Sarvam Cloud Service ready — "
            f"gen_model={self._gen_model}, cls_model={self._cls_model}, "
            f"base_url={self._base_url}"
        )

    # -----------------------------------------------------------------------
    # Core HTTP API call — ALL LLM calls go through here
    # -----------------------------------------------------------------------

    async def _call_api(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        stream: bool = False,
        **kwargs,
    ) -> str:
        """
        Direct HTTP POST to Sarvam Chat Completions API.

        Replaces the buggy langchain-sarvam wrapper with reliable httpx calls.
        Includes retry logic, circuit breaker, and detailed error logging.

        Returns: The assistant's response content (stripped of <think> tags).
        """
        if not self._circuit.can_execute():
            raise Exception(
                f"Sarvam API circuit breaker is OPEN — "
                f"failing fast. Will retry after recovery timeout."
            )

        headers = {
            "Content-Type": "application/json",
            "api-subscription-key": self._api_key,
        }

        # Validate messages: Sarvam API rejects empty content fields with HTTP 400
        validated_messages = []
        for msg in messages:
            content = msg.get("content", "") or ""
            if not content.strip():
                # Skip empty messages or replace with a minimal placeholder
                if msg.get("role") == "system":
                    content = "You are a helpful assistant."
                elif msg.get("role") == "user":
                    content = "Please respond."
                else:
                    continue
            validated_messages.append({"role": msg["role"], "content": content})

        if not validated_messages:
            logger.warning("_call_api: No valid messages to send after validation")
            return ""

        payload = {
            "model": model,
            "messages": validated_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        last_error = None
        for attempt in range(1, self._max_retries + 1):
            start_time = time.time()
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )

                latency_ms = (time.time() - start_time) * 1000

                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
                    tokens_used = data.get("usage", {}).get("total_tokens", 0)

                    # Strip <think> tags from reasoning models
                    # Sarvam-30b sometimes puts ALL content inside <think>...</think>,
                    # especially for classification/grading tasks.
                    # Strategy: First check if there's content OUTSIDE think tags.
                    # If not, extract the meaningful output FROM the think tags.
                    think_match = re.search(r"<think>(.*?)</think>", content, flags=re.DOTALL)
                    content_outside_think = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

                    if content_outside_think:
                        # Normal case: real content exists outside think tags
                        content = content_outside_think
                    elif think_match:
                        # Reasoning model put EVERYTHING in think tags
                        # Extract the last non-empty line as the "answer"
                        think_text = think_match.group(1).strip()
                        lines = [l.strip() for l in think_text.splitlines() if l.strip()]
                        if lines:
                            # For classification: use the last line (usually the final answer)
                            content = lines[-1]
                            logger.debug(
                                f"Extracted answer from <think> tags: '{content[:100]}'"
                            )
                        else:
                            content = ""
                    else:
                        content = content.strip()

                    logger.info(
                        f"Sarvam API OK — model={model}, "
                        f"latency={latency_ms:.0f}ms, tokens={tokens_used}, "
                        f"response_len={len(content)}"
                    )

                    # Prometheus instrumentation
                    try:
                        from app.metrics import LLM_LATENCY, LLM_TOKENS
                        LLM_LATENCY.labels(model=model, operation="generate").observe(latency_ms / 1000)
                        if tokens_used:
                            LLM_TOKENS.labels(model=model).inc(tokens_used)
                    except Exception:
                        pass  # Metrics are optional

                    self._circuit.record_success()
                    return content

                # Handle specific error codes
                status = resp.status_code
                body = resp.text[:500]

                if status == 429 or "credits" in body.lower():
                    self._circuit.record_failure()
                    raise QuotaExceededError(
                        f"Sarvam API quota exceeded (HTTP {status}): {body}"
                    )

                if status >= 500:
                    # Server error — retry
                    logger.warning(
                        f"Sarvam API server error (attempt {attempt}/{self._max_retries}): "
                        f"HTTP {status} — {body}"
                    )
                    last_error = Exception(f"HTTP {status}: {body}")
                    await asyncio.sleep(min(2 ** attempt, 8))  # Exponential backoff
                    continue

                # Client error (4xx) — don't retry
                self._circuit.record_failure()
                raise Exception(
                    f"Sarvam API client error: HTTP {status} — {body}"
                )

            except QuotaExceededError:
                raise
            except httpx.TimeoutException:
                latency_ms = (time.time() - start_time) * 1000
                logger.warning(
                    f"Sarvam API timeout (attempt {attempt}/{self._max_retries}): "
                    f"{latency_ms:.0f}ms"
                )
                last_error = Exception(f"Timeout after {latency_ms:.0f}ms")
                await asyncio.sleep(min(2 ** attempt, 8))
            except Exception as e:
                if isinstance(e, QuotaExceededError):
                    raise
                latency_ms = (time.time() - start_time) * 1000
                logger.warning(
                    f"Sarvam API error (attempt {attempt}/{self._max_retries}): {e}"
                )
                last_error = e
                await asyncio.sleep(min(2 ** attempt, 8))

        # All retries exhausted
        self._circuit.record_failure()
        raise last_error or Exception("Sarvam API call failed after all retries")

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
        max_tokens = kwargs.pop("max_tokens", 2048)

        return await self._call_api(
            messages=messages,
            model=self._gen_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

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
        max_tokens = kwargs.pop("max_tokens", 512)

        try:
            return await self._call_api(
                messages=messages,
                model=self._cls_model,
                max_tokens=max_tokens,
                temperature=temperature,
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
            "api-subscription-key": self._api_key,
        }

        payload = {
            "model": self._gen_model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 2048),
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as resp:
                    buffer = ""
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                # Strip think tags from accumulated buffer
                                if buffer:
                                    clean = re.sub(r"<think>.*?</think>", "", buffer, flags=re.DOTALL)
                                    # Already yielded tokens — just log completion
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    buffer += delta
                                    yield delta
                            except json.JSONDecodeError:
                                pass

            self._circuit.record_success()

        except Exception as e:
            logger.error(f"Sarvam Cloud streaming failed: {e}")
            self._circuit.record_failure()
            if "credits" in str(e).lower() or "429" in str(e).lower():
                logger.warning("Quota exceeded for Sarvam Cloud API in streaming.")
                yield "The essence of spiritual practice is compassion and mindfulness. Even in stillness, your presence is heard."
                return
            raise

    # -----------------------------------------------------------------------
    # Domain-specific LLM methods (unchanged public interface)
    # -----------------------------------------------------------------------

    async def classify_intent(self, message: str) -> str:
        """
        Classify user message into one of three intents.

        Returns: 'DISTRESS' | 'QUERY' | 'CASUAL'

        IMPORTANT: If the LLM returns empty/garbage, default to QUERY (not CASUAL)
        so the RAG pipeline still processes the question.
        """
        result = await self._generate_fast(INTENT_CLASSIFICATION_PROMPT, message)

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
        elif "QUERY" in result_upper:
            return "QUERY"
        elif "CASUAL" in result_upper:
            return "CASUAL"
        else:
            # Unrecognized output — default to QUERY (safer than CASUAL)
            logger.warning(
                f"classify_intent got unrecognized output: {result[:100]!r}. "
                "Defaulting to QUERY."
            )
            return "QUERY"

    async def grade_relevance(self, query: str, document: str) -> bool:
        """
        CRAG: Binary relevance grading of a retrieved document.

        Returns True if the document is relevant to the query.
        """
        prompt = f"Question: {query}\n\nDocument: {document}"
        result = await self._generate_fast(GRADE_RELEVANCE_PROMPT, prompt)
        return "yes" in result.lower()

    async def batch_grade_relevance(self, query: str, documents: list[str]) -> list[bool]:
        """
        CRAG: Batch relevance grading of multiple documents in one LLM call.

        Returns: List of booleans, one per document (True = relevant).
        """
        if not documents:
            return []

        # Build numbered document list
        numbered_docs = "\n\n".join(
            f"Document {i+1}:\n{doc[:800]}"  # Truncate individual docs to fit context
            for i, doc in enumerate(documents)
        )

        prompt = f"Question: {query}\n\n{numbered_docs}"
        result = await self._generate_fast(BATCH_GRADE_PROMPT, prompt)

        # Parse "1: yes\n2: no\n3: yes" format
        relevance = [False] * len(documents)
        for line in result.strip().splitlines():
            line = line.strip()
            if ":" in line:
                parts = line.split(":", 1)
                try:
                    idx = int(parts[0].strip()) - 1  # 1-indexed → 0-indexed
                    if 0 <= idx < len(documents):
                        relevance[idx] = "yes" in parts[1].lower()
                except (ValueError, IndexError):
                    continue

        # If parser didn't match or LLM graded everything False,
        # keep the top-5 documents to guarantee context!
        if not any(relevance) and len(documents) > 0:
            logger.warning("Relevance grading returned no docs. Using top documents fallback.")
            for i in range(min(5, len(documents))):
                relevance[i] = True

        return relevance

    async def check_faithfulness(self, answer: str, context: str) -> bool:
        """
        Self-RAG: Check if the generated answer is faithful to the context.

        Returns True if EVERY claim in the answer is supported by the context.
        """
        prompt = f"Context:\n{context}\n\nAnswer:\n{answer}"
        result = await self._generate_fast(FAITHFULNESS_CHECK_PROMPT, prompt)
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

    async def rewrite_query(self, original_query: str) -> str:
        """
        CRAG: Rewrite a query to improve retrieval quality.
        """
        return await self.generate(QUERY_REWRITE_PROMPT, f"Original query: {original_query}")

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
        for line in lines:
            if "CONFIDENCE" in line:
                after = line.split("CONFIDENCE", 1)[-1]
                nums = re.findall(r'\d+', after)
                if nums:
                    try:
                        confidence = float(min(int(nums[0]), 10))
                    except (ValueError, IndexError):
                        pass
                break

        # Both must pass
        final_passed = is_faithful and passed

        if not final_passed:
            logger.info(
                f"Combined verify: faithful={is_faithful}, verdict_pass={passed}, "
                f"confidence={confidence}"
            )

        return {
            "is_faithful": is_faithful,
            "passed": final_passed,
            "confidence": confidence,
            "details": result,
        }

    async def summarize(self, texts: list[str]) -> str:
        """
        Summarize a cluster of text chunks (used by RAPTOR).
        """
        combined = "\n\n".join(texts)
        return await self.generate(SUMMARIZE_PROMPT, combined)

    async def decompose_query(self, query: str) -> list[str]:
        """
        Query Decomposition: Split complex questions into atomic sub-queries.

        Returns: List of 2-3 simpler sub-queries.
        """
        result = await self._generate_fast(DECOMPOSE_QUERY_PROMPT, query)

        sub_queries = []
        for line in result.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                sub_queries.append(line[2:].strip())
            elif line.startswith(("1.", "2.", "3.")):
                sub_queries.append(line[2:].strip())

        return sub_queries if sub_queries else [query]

    async def generate_hypothetical_answer(self, query: str) -> str:
        """
        HyDE (Hypothetical Document Embeddings): Generate a fake answer.
        """
        return await self.generate(HYDE_PROMPT, query)

    async def is_complex_query(self, query: str) -> bool:
        """
        Determine if a query needs decomposition.
        """
        result = await self._generate_fast(IS_COMPLEX_QUERY_PROMPT, query)
        return "complex" in result.lower()

    async def health_check(self) -> bool:
        """Check if Sarvam Cloud API is reachable."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "api-subscription-key": self._api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._gen_model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5,
                    },
                )
            return resp.status_code == 200
        except Exception:
            return False
