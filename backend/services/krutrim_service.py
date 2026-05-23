"""Krutrim AI integration as alternative/fallback LLM provider."""

import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class KrutrimService:
    """
    Krutrim Pro integration — supports 22 Indian languages.
    Used as:
    - Primary for certain languages Krutrim handles better
    - Fallback if Sarvam is unavailable
    - A/B testing alternative
    """

    def __init__(self):
        self._api_key = settings.krutrim_api_key or ""
        self._base_url = "https://api.krutrim.com/v1"
        self._model = "krutrim-pro-v1"
        # Connection pooling: Create a singleton httpx.AsyncClient with pool limits
        self._http_client = None
        self._http_client_lock = asyncio.Lock()

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
                self._http_client = httpx.AsyncClient(
                    timeout=getattr(settings, "llm_timeout", 60), limits=limits
                )
                logger.info(
                    f"Krutrim HTTP client initialized with pool limits: "
                    f"max_connections={limits.max_connections}, "
                    f"max_keepalive_connections={limits.max_keepalive_connections}"
                )
            return self._http_client

    async def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        if not self._api_key:
            raise ValueError("Krutrim API key not configured")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }

        client = await self._get_http_client()
        resp = await client.post(
            f"{self._base_url}/chat/completions",
            headers=headers,
            json=payload,
        )

        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            raise Exception(f"Krutrim API error: {resp.status_code} — {resp.text[:200]}")

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        async with self._http_client_lock:
            if self._http_client is not None:
                await self._http_client.aclose()
                self._http_client = None
                logger.info("Krutrim HTTP client closed")
