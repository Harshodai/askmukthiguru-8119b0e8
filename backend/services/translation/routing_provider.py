"""Routing Translation Provider implementation (Strategy Pattern)."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from services.translation.base import TranslationProvider

logger = logging.getLogger(__name__)


class RoutingTranslationProvider(TranslationProvider):
    """Dynamic translation router: Gemini first (when enabled), Sarvam fallback."""

    def __init__(
        self,
        sarvam_provider: TranslationProvider,
        ollama_provider: TranslationProvider | None = None,
        gemini_provider: TranslationProvider | None = None,
    ) -> None:
        # Signature kept backwards-compatible: positional `sarvam_provider` order
        # preserved so existing callers (factory.py) using keyword args still work
        # and old positional `(ollama_provider, sarvam_provider)` callers also work.
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
        """Translate via Gemini first (when enabled + configured), else Sarvam."""
        # Gemini-first path: try, fall back to Sarvam on any failure.
        if settings.gemini_translation_enabled and self._gemini is not None:
            try:
                return await self._gemini.translate_text(
                    text=text, source_lang=source_lang, target_lang=target_lang, **kwargs
                )
            except Exception as gemini_err:
                logger.error(
                    f"Gemini translation failed, falling back to Sarvam: {gemini_err}"
                )
                # Fall through to Sarvam below if it is configured; else raise.
                if not settings.gemini_fallback_to_sarvam:
                    raise

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
                raise

        raise RuntimeError("No translation provider available (Sarvam not configured)")

    async def health_check(self) -> bool:
        """Return True if Gemini or Sarvam is healthy (guarded)."""
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

        return gemini_ok or sarvam_ok
