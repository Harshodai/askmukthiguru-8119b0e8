"""Translation Provider Factory implementation."""

from __future__ import annotations

import logging

from services.llm_factory import LLMServiceFactory
from services.translation.base import TranslationProvider
from services.translation.sarvam_provider import SarvamTranslationProvider
from services.translation.routing_provider import RoutingTranslationProvider

logger = logging.getLogger(__name__)


class TranslationProviderFactory:
    """Factory to create TranslationProvider strategies."""

    @staticmethod
    def create_provider(
        ollama_service=None,
        sarvam_service=None,
    ) -> TranslationProvider:
        """Create and return a TranslationProvider instance."""
        if sarvam_service is None:
            sarvam_service = LLMServiceFactory.create("sarvam_cloud")

        sarvam_provider = SarvamTranslationProvider(sarvam_service)

        return RoutingTranslationProvider(
            ollama_provider=None,
            sarvam_provider=sarvam_provider,
        )
