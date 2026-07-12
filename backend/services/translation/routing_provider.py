"""Routing Translation Provider implementation (Strategy Pattern)."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from services.translation.base import TranslationProvider

logger = logging.getLogger(__name__)


class RoutingTranslationProvider(TranslationProvider):
    """Dynamic translation router: Gemini first (when enabled), Sarvam fallback, Ollama last resort."""

    def __init__(
        self,
        ollama_provider: TranslationProvider | None = None,
        sarvam_provider: TranslationProvider | None = None,
        gemini_provider: TranslationProvider | None = None,
    ) -> None:
        # Legacy positional order preserved: (ollama_provider, sarvam_provider).
        # Keyword args (gemini_provider=..., sarvam_provider=..., ollama_provider=...) also work.
        self._ollama = ollama_provider
        self._sarvam = sarvam_provider
        self._gemini = gemini_provider

    async def translate_text(
        self,
        *,
        text: str,
        source_lang: str,
        target_lang: str,
        **kwargs: Any,
    ) -> str:
        """Translate via Gemini first (when enabled + configured), else Sarvam, else Ollama."""
        # Gemini-first path: try, fall back to Sarvam on any failure.
        if settings.gemini_translation_enabled and self._gemini is not None:
            try:
                return await self._gemini.translate_text(
                    text=text, source_lang=source_lang, target_lang=target_lang, **kwargs
                )
            except Exception as gemini_err:
                if settings.gemini_fallback_to_sarvam:
                    logger.error(
                        f"Gemini translation failed, falling back to Sarvam: {gemini_err}"
                    )
                else:
                    logger.error(
                        f"Gemini translation failed, no fallback configured: {gemini_err}"
                    )
                    raise
                # Fall through to Sarvam below if it is configured; else raise.

        # Sarvam fallback path (existing gate preserved).
        if (
            settings.sarvam_api_key
            and not settings.sarvam_api_key.startswith("sk_dummy")
            and settings.sarvam_api_key.strip()
        ):
            try:
                return await self._sarvam.translate_text(
                    text=text, source_lang=source_lang, target_lang=target_lang, **kwargs
                )
            except Exception as sarvam_err:
                logger.error(f"Sarvam translation failed: {sarvam_err}")
                # Fall through to Ollama if available.
                pass

        # Ollama fallback if Sarvam unavailable/failed and Ollama configured.
        if self._ollama is not None:
            try:
                return await self._ollama.translate_text(
                    text=text, source_lang=source_lang, target_lang=target_lang, **kwargs
                )
            except Exception as ollama_err:
                logger.error(f"Ollama translation failed: {ollama_err}")
                raise

        raise RuntimeError("No translation provider available (Sarvam/Ollama not configured)")

    async def health_check(self) -> bool:
        """Return True if any provider in the chain is healthy."""
        gemini_ok = False
        if settings.gemini_translation_enabled and self._gemini is not None:
            try:
                gemini_ok = await self._gemini.health_check()
            except Exception as e:
                logger.warning(f"Gemini health_check errored: {e}")
                gemini_ok = False

        sarvam_ok = False
        if (
            settings.sarvam_api_key
            and not settings.sarvam_api_key.startswith("sk_dummy")
            and settings.sarvam_api_key.strip()
        ):
            try:
                sarvam_ok = await self._sarvam.health_check()
            except Exception:
                sarvam_ok = False

        ollama_ok = False
        if self._ollama is not None:
            try:
                ollama_ok = await self._ollama.health_check()
            except Exception:
                ollama_ok = False

        return gemini_ok or sarvam_ok or ollama_ok
