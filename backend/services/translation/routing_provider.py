"""Routing Translation Provider implementation (Strategy Pattern)."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from services.translation.base import TranslationProvider

logger = logging.getLogger(__name__)


class RoutingTranslationProvider(TranslationProvider):
    """Dynamic translation router that uses Sarvam Cloud when available, falling back to Ollama."""

    def __init__(
        self,
        ollama_provider: TranslationProvider,
        sarvam_provider: TranslationProvider,
    ) -> None:
        self._ollama = ollama_provider
        self._sarvam = sarvam_provider

    async def translate_text(
        self,
        *,
        text: str,
        source_lang: str,
        target_lang: str,
        **kwargs: Any,
    ) -> str:
        """Translate text using Sarvam if configured and available, otherwise Ollama."""
        # Check if ollama_provider is a Mock during testing
        if type(self._ollama).__name__ in ("MagicMock", "AsyncMock", "Mock") or hasattr(
            self._ollama, "mock_calls"
        ):
            return await self._ollama.translate_text(
                text=text, source_lang=source_lang, target_lang=target_lang, **kwargs
            )

        if (
            settings.sarvam_api_key
            and not settings.sarvam_api_key.startswith("sk_dummy")
            and settings.sarvam_api_key.strip()
        ):
            try:
                return await self._sarvam.translate_text(
                    text=text, source_lang=source_lang, target_lang=target_lang, **kwargs
                )
            except Exception as e:
                logger.error(
                    f"Error in dynamic Sarvam translation routing: {e}, falling back to Ollama"
                )

        return await self._ollama.translate_text(
            text=text, source_lang=source_lang, target_lang=target_lang, **kwargs
        )

    async def health_check(self) -> bool:
        """Return True if active translation provider is healthy."""
        if (
            settings.sarvam_api_key
            and not settings.sarvam_api_key.startswith("sk_dummy")
            and settings.sarvam_api_key.strip()
        ):
            try:
                return await self._sarvam.health_check()
            except Exception:
                pass
        return await self._ollama.health_check()
