"""
Unit 25 — Model Failover (Priority-Chain Registry)

Implements a priority-ordered failover chain for LLM generation:
  1. Primary: Ollama local (gemma3:12b / sarvam-2b / as configured)
  2. Fallback 1: Ollama llama3.2:3b (lighter, faster)
  3. Fallback 2: Krutrim API (cloud, 22 Indian languages)

On ``ModelUnavailableError`` from the primary, automatically falls over
to the next provider. Each provider is tried in order until one succeeds.

Usage::

    from services.model_registry import ModelRegistry

    registry = ModelRegistry(ollama_service, krutrim_service)
    answer = await registry.generate_with_failover(system, user, context)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Optional

from services.ollama_service import ModelUnavailableError, OllamaService
from services.krutrim_service import KrutrimService
from app.config import settings

logger = logging.getLogger(__name__)


_FALLBACK_OLLAMA_MODEL = "llama3.2:3b"
_FAILOVER_LOG_PREFIX = "[unit25-failover]"


class ModelRegistry:
    """Priority-chain LLM failover gateway.

    Tries providers in order:
      1. Primary Ollama (configured model)
      2. Fallback Ollama (llama3.2:3b — smaller, faster)
      3. Krutrim API (cloud fallback)

    Falls over on ``ModelUnavailableError`` or any transient error from
    the primary. Permanent errors (e.g., bad prompt) are NOT retried.
    """

    def __init__(
        self,
        ollama_service: OllamaService,
        krutrim_service: Optional[KrutrimService] = None,
    ) -> None:
        self._ollama = ollama_service
        self._krutrim = krutrim_service

        # Build a lightweight fallback Ollama client for llama3.2:3b
        try:
            from langchain_ollama import ChatOllama

            self._fallback_llm = ChatOllama(
                base_url=settings.ollama_base_url,
                model=_FALLBACK_OLLAMA_MODEL,
                temperature=0.1,
                num_predict=1024,
                timeout=45,
            )
            logger.info(f"ModelRegistry: fallback model ready ({_FALLBACK_OLLAMA_MODEL})")
        except Exception as exc:
            logger.warning(f"ModelRegistry: could not init fallback Ollama model: {exc}")
            self._fallback_llm = None

    async def generate_with_failover(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> str:
        """Generate a response, falling over to backup providers on failure.

        Returns:
            Generated text string.

        Raises:
            Exception: If all providers fail.
        """
        # --- Attempt 1: Primary Ollama ---
        try:
            return await self._ollama.generate(system_prompt, user_prompt, context, **kwargs)
        except ModelUnavailableError as exc:
            if not exc.is_transient:
                raise
            logger.warning(
                f"{_FAILOVER_LOG_PREFIX} Primary Ollama unavailable: {exc}. "
                f"Trying fallback Ollama ({_FALLBACK_OLLAMA_MODEL})..."
            )
        except Exception as exc:
            logger.warning(
                f"{_FAILOVER_LOG_PREFIX} Primary Ollama failed unexpectedly: {type(exc).__name__}. "
                f"Trying fallback Ollama ({_FALLBACK_OLLAMA_MODEL})..."
            )

        # --- Attempt 2: Fallback Ollama (llama3.2:3b) ---
        if self._fallback_llm:
            try:
                result = await self._generate_with_fallback_llm(
                    system_prompt, user_prompt, context, **kwargs
                )
                logger.info(
                    f"{_FAILOVER_LOG_PREFIX} Fallback Ollama succeeded "
                    f"(model={_FALLBACK_OLLAMA_MODEL})"
                )
                return result
            except Exception as exc:
                logger.warning(
                    f"{_FAILOVER_LOG_PREFIX} Fallback Ollama also failed: "
                    f"{type(exc).__name__}: {exc}. Trying Krutrim..."
                )

        # --- Attempt 3: Krutrim API ---
        if self._krutrim:
            try:
                result = await self._krutrim.generate(system_prompt, user_prompt, **kwargs)
                logger.info(f"{_FAILOVER_LOG_PREFIX} Krutrim API succeeded.")
                return result
            except Exception as exc:
                logger.error(
                    f"{_FAILOVER_LOG_PREFIX} All providers failed. Krutrim error: "
                    f"{type(exc).__name__}: {exc}"
                )
                raise

        raise RuntimeError(
            f"{_FAILOVER_LOG_PREFIX} All LLM providers exhausted and no Krutrim fallback configured."
        )

    async def _generate_with_fallback_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> str:
        """Direct generation with the fallback ChatOllama instance."""
        import asyncio
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [SystemMessage(content=system_prompt)]
        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion: {user_prompt}"
        else:
            full_prompt = user_prompt
        messages.append(HumanMessage(content=full_prompt))

        timeout = kwargs.pop("timeout", 45)
        response = await asyncio.wait_for(self._fallback_llm.ainvoke(messages), timeout=timeout)
        return response.content.strip()

    async def stream_with_failover(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str = "",
        **kwargs,
    ) -> AsyncIterator[str]:
        """Streaming generation with automatic failover to non-streaming fallback.

        If the primary streaming fails (ModelUnavailableError), falls back to
        generate_with_failover() and yields the entire response as one chunk.
        This preserves the streaming contract for callers while still delivering content.
        """
        from services.streaming_hardening import guarded_stream, StreamInterruptedError

        try:
            async for token in guarded_stream(
                self._ollama.generate_stream(system_prompt, user_prompt, context, **kwargs)
            ):
                yield token
        except (StreamInterruptedError, ModelUnavailableError) as exc:
            logger.warning(
                f"{_FAILOVER_LOG_PREFIX} Streaming failed: {type(exc).__name__}. "
                f"Falling back to non-streaming generate_with_failover..."
            )
            try:
                result = await self.generate_with_failover(
                    system_prompt, user_prompt, context, **kwargs
                )
                yield result
            except Exception as fallback_exc:
                logger.error(
                    f"{_FAILOVER_LOG_PREFIX} Streaming + fallback both failed: {fallback_exc}"
                )
                yield "\n\n[All response providers failed. Please try again later.]"

    @property
    def primary_model(self) -> str:
        """Return the name of the primary Ollama model."""
        return settings.model_for_generation

    @property
    def fallback_model(self) -> str:
        """Return the name of the fallback Ollama model."""
        return _FALLBACK_OLLAMA_MODEL
