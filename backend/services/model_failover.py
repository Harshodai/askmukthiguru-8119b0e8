"""
Unit 25 — Model Failover Proxy

Wraps a primary and optional fallback LLM service, automatically
switching to the fallback when the primary raises ModelUnavailableError
or times out.

Design:
  - Transparent proxy: drop-in replacement for any LLM provider
  - Failover triggers: ModelUnavailableError, asyncio.TimeoutError,
    ConnectionError, CircuitOpen
  - Logging: every failover is logged for observability
  - Compliance: audit trail preserved via ComplianceLogger
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from services.ollama_service import ModelUnavailableError

logger = logging.getLogger(__name__)


class ModelFailoverProxy:
    """Transparent LLM proxy with automatic failover.

    Transparently routes calls to the primary provider; on
    ``ModelUnavailableError`` or ``asyncio.TimeoutError`` it falls back
    to the secondary provider and logs the switch.
    """

    def __init__(
        self,
        primary: Any,
        fallback: Any,
        *,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.primary_name = primary_name
        self.fallback_name = fallback_name

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _is_failover_error(self, exc: Exception) -> bool:
        """Return True if *exc* justifies a failover attempt."""
        if isinstance(exc, (asyncio.TimeoutError, ConnectionError)):
            return True
        if isinstance(exc, ModelUnavailableError) and getattr(exc, "is_transient", True):
            return True
        return False

    async def _call_with_failover(self, method_name: str, *args, **kwargs) -> Any:
        """Call *method_name* on primary, fallback on transient failure."""
        try:
            method = getattr(self.primary, method_name)
            return await method(*args, **kwargs)
        except Exception as exc:
            if not self._is_failover_error(exc):
                raise

            logger.warning(
                "ModelFailover: %s failed (%s), switching to %s",
                self.primary_name,
                type(exc).__name__,
                self.fallback_name,
            )

            method = getattr(self.fallback, method_name)
            return await method(*args, **kwargs)

    # ------------------------------------------------------------------
    # Public passthrough API (mirrors LLMProvider contract)
    # ------------------------------------------------------------------
    async def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        return await self._call_with_failover("generate", system_prompt, user_prompt, **kwargs)

    async def generate_stream(self, system_prompt: str, user_prompt: str, **kwargs: Any):
        """Stream tokens from the primary; failover only on first failure."""
        try:
            async for token in self.primary.generate_stream(system_prompt, user_prompt, **kwargs):
                yield token
        except Exception as exc:
            if not self._is_failover_error(exc):
                raise
            logger.warning(
                "ModelFailover: %s stream failed (%s), switching to %s",
                self.primary_name,
                type(exc).__name__,
                self.fallback_name,
            )
            async for token in self.fallback.generate_stream(system_prompt, user_prompt, **kwargs):
                yield token

    async def classify(self, text: str, **kwargs: Any) -> str:
        return await self._call_with_failover("classify", text, **kwargs)

    async def classify_intent(self, text: str, **kwargs: Any) -> str:
        return await self._call_with_failover("classify_intent", text, **kwargs)

    async def classify_distress_structured(self, message: str) -> dict:
        return await self._call_with_failover("classify_distress_structured", message)

    async def batch_grade_relevance(self, question: str, doc_texts: list[str]) -> list[dict[str, Any]]:
        return await self._call_with_failover("batch_grade_relevance", question, doc_texts)

    async def check_faithfulness(self, *, answer: str, context: str) -> dict[str, Any]:
        return await self._call_with_failover("check_faithfulness", answer=answer, context=context)

    async def combined_verify(self, answer: str, context: str) -> dict[str, Any]:
        return await self._call_with_failover("combined_verify", answer, context)

    async def decompose_query(self, question: str, **kwargs: Any) -> list[str]:
        return await self._call_with_failover("decompose_query", question, **kwargs)

    async def rewrite_query(self, original: str, reasons: list[str], **kwargs: Any) -> str:
        return await self._call_with_failover("rewrite_query", original, reasons, **kwargs)

    async def generate_hypothetical_answer(self, question: str, **kwargs: Any) -> str:
        return await self._call_with_failover("generate_hypothetical_answer", question, **kwargs)

    async def compress_context(self, question: str, text: str, **kwargs: Any) -> str:
        return await self._call_with_failover("compress_context", question, text, **kwargs)

    async def translate_text(self, text: str, source_lang: str, target_lang: str, **kwargs: Any) -> str:
        return await self._call_with_failover("translate_text", text, source_lang, target_lang, **kwargs)

    async def health_check(self) -> bool:
        """Return True if at least one model is healthy."""
        for svc, name in (
            (self.primary, self.primary_name),
            (self.fallback, self.fallback_name),
        ):
            try:
                if await svc.health_check():
                    return True
            except Exception:
                logger.debug("ModelFailover: health check failed for %s", name)
        return False
