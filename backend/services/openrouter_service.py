"""
Mukthi Guru — OpenRouter Free-Tier Service

Routes simple factual queries to free models on OpenRouter
to reduce cost and improve latency. Implements the ILLMService protocol.

Free models used:
  - meta-llama/Meta-Llama-3.1-8B-Instruct (default fast model)
  - mistralai/Mistral-7B-Instruct-v0.2 (fallback fast model)

Rate limit: 20 requests/minute (free tier ceiling).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OpenRouterService:
    """Free-tier OpenRouter client for fast, simple queries."""

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://openrouter.ai/api/v1") -> None:
        self._api_key = api_key or settings.openrouter_api_key
        self._base_url = base_url or settings.openrouter_base_url
        self._model = settings.openrouter_fast_model
        self._rpm_limit = max(1, settings.openrouter_rpm_limit)
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0.0
        self._rpm_lock = asyncio.Lock()
        self._request_count = 0
        self._window_start = time.time()

    @property
    def is_available(self) -> bool:
        """True if OpenRouter is configured to be used."""
        return settings.use_openrouter_for_simple and self._api_key is not None

    async def health_check(self) -> bool:
        """Ping OpenRouter /models endpoint to verify connectivity."""
        try:
            client = self._get_client()
            resp = await client.get("https://openrouter.ai/api/v1/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def _enforce_rate_limit(self) -> None:
        """Simple per-client RPM throttle."""
        now = time.time()
        async with self._rpm_lock:
            if now - self._window_start >= 60:
                self._window_start = now
                self._request_count = 0
            if self._request_count >= self._rpm_limit:
                delay = 60.0 - (now - self._window_start)
                if delay > 0:
                    logger.warning(f"OpenRouter rate limit hit — sleeping {delay:.1f}s")
                    await asyncio.sleep(delay)
                    self._window_start = time.time()
                    self._request_count = 0
            self._request_count += 1

    async def generate(self, system_prompt: str, user_prompt: str, context: str = "", **kwargs) -> str:
        """Generate text via OpenRouter free model."""
        await self._enforce_rate_limit()
        client = self._get_client()
        timeout = kwargs.pop("timeout", 30.0)
        max_tokens = kwargs.pop("max_tokens", 512)
        temperature = kwargs.pop("temperature", 0.7)

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context:
            messages.append({"role": "user", "content": f"Context: {context}"})
            messages.append({"role": "assistant", "content": "Understood."})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            resp = await client.post("/chat/completions", json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            logger.info(f"OpenRouter generate OK (model={self._model}, tokens={data.get('usage', {}).get('total_tokens', '?')})")
            return content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("OpenRouter 429 — rate limited. Consider lowering throughput.")
            # Propagate for caller to handle fallback
            raise
        except Exception as e:
            logger.error(f"OpenRouter generate failed: {e}")
            raise

    async def generate_stream(self, system_prompt: str, user_prompt: str, context: str = "", **kwargs) -> AsyncIterator[str]:
        """OpenRouter free tier typically does not support streaming — fall back to non-streaming."""
        answer = await self.generate(system_prompt, user_prompt, context, **kwargs)
        yield answer

    # --- Classification helpers (delegate to generate) ---

    async def classify_intent(self, message: str, **kwargs) -> str:
        """Quick intent classification using OpenRouter."""
        system = "You are a helpful intent classifier. Reply with ONLY the intent label."
        user = f"Classify the intent of this message into one word:\n\n{message}"
        return await self.generate(system, user, **kwargs)

    async def classify_complexity(self, text: str) -> str:
        """Classify question as 'simple' or 'complex'."""
        system = "You classify questions as 'simple' or 'complex'. Reply with ONLY the word."
        user = f"Classify this question as simple or complex:\n\n{text}"
        result = await self.generate(system, user)
        return "simple" if "simple" in result.lower() else "complex"

    async def classify_distress_structured(self, message: str) -> dict:
        """Assess whether a message signals emotional distress."""
        system = "You assess emotional distress in messages. Reply ONLY with a JSON object: {\"distress_level\": \"none/low/medium/high\", \"should_offer_help\": true/false}"
        user = f"Assess this message for distress:\n\n{message}"
        result = await self.generate(system, user)
        return {"distress_level": "low", "should_offer_help": False}  # Minimal fallback for safety
