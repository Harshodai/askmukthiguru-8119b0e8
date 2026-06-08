"""Translation Provider Factory implementation."""

from __future__ import annotations

from services.translation.base import TranslationProvider
from services.translation.ollama_provider import OllamaTranslationProvider
from services.translation.sarvam_provider import SarvamTranslationProvider
from services.translation.routing_provider import RoutingTranslationProvider
from services.llm_factory import LLMServiceFactory


class TranslationProviderFactory:
    """Factory to create TranslationProvider strategies."""

    @staticmethod
    def create_provider(
        ollama_service=None,
        sarvam_service=None,
    ) -> TranslationProvider:
        """Create and return a TranslationProvider instance."""
        if ollama_service is None:
            ollama_service = LLMServiceFactory.create("ollama")
        if sarvam_service is None:
            sarvam_service = LLMServiceFactory.create("sarvam_cloud")

        ollama_provider = OllamaTranslationProvider(ollama_service)
        sarvam_provider = SarvamTranslationProvider(sarvam_service)

        return RoutingTranslationProvider(
            ollama_provider=ollama_provider,
            sarvam_provider=sarvam_provider,
        )
