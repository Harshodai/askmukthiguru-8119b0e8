"""LLM Provider Factory implementation."""

from __future__ import annotations

from app.config import settings
from services.llm.base import LLMProvider
from services.llm.ollama_provider import OllamaProvider
from services.llm.sarvam_provider import SarvamProvider
from services.llm_factory import LLMServiceFactory


class LLMProviderFactory:
    """Factory to create LLMProvider strategies wrapping the underlying services."""

    @staticmethod
    def create_provider(provider_name: str | None = None) -> LLMProvider:
        """Create and return an LLMProvider instance based on configuration."""
        name = (provider_name or settings.llm_provider or "sarvam_cloud").lower()

        # Use the existing LLMServiceFactory to create the underlying service
        underlying_service = LLMServiceFactory.create(name)

        if name == "ollama":
            return OllamaProvider(underlying_service)
        elif name in ("sarvam", "sarvam_cloud"):
            return SarvamProvider(underlying_service)
        else:
            raise ValueError(f"Unknown LLM provider strategy: {name}")
