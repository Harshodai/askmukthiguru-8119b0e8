"""Translation Provider Factory implementation."""

from __future__ import annotations

import logging

from app.config import settings
from services.llm_factory import LLMServiceFactory
from services.translation.base import TranslationProvider
from services.translation.gemini_provider import GeminiTranslationProvider
from services.translation.routing_provider import RoutingTranslationProvider
from services.translation.sarvam_provider import SarvamTranslationProvider

logger = logging.getLogger(__name__)


class TranslationProviderFactory:
    """Factory to create TranslationProvider strategies."""

    @staticmethod
    def create_provider(
        ollama_service=None,
        sarvam_service=None,
    ) -> TranslationProvider:
        """Create and return a TranslationProvider instance.

        Wires Gemini-via-OpenRouter ahead of Sarvam when enabled + an OpenRouter
        key is present. Gemini becomes the primary; Sarvam is the fallback.
        """
        if sarvam_service is None:
            sarvam_service = LLMServiceFactory.create("sarvam_cloud")

        sarvam_provider = SarvamTranslationProvider(sarvam_service)

        gemini_provider: TranslationProvider | None = None
        if (
            settings.gemini_translation_enabled
            and settings.openrouter_api_key
            and settings.openrouter_api_key.strip()
        ):
            try:
                gemini_provider = GeminiTranslationProvider()
            except Exception as e:
                logger.warning(
                    f"GeminiTranslationProvider unavailable, will use Sarvam only: {e}"
                )
                gemini_provider = None

        return RoutingTranslationProvider(
            gemini_provider=gemini_provider,
            ollama_provider=None,
            sarvam_provider=sarvam_provider,
        )
