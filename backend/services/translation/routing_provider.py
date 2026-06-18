"""Routing Translation Provider implementation (Strategy Pattern)."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from services.translation.base import TranslationProvider

logger = logging.getLogger(__name__)


class RoutingTranslationProvider(TranslationProvider):
    """Dynamic translation router that uses Sarvam Cloud when available."""

    def __init__(
        self,
        ollama_provider: TranslationProvider | None,
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
        """Translate text using Sarvam if configured and available."""
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
                    f"Sarvam translation failed: {e}"
                )
                raise

        raise RuntimeError("No translation provider available (Sarvam not configured)")

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
                return False
        return False
