"""
Mukthi Guru — LLM Provider Factory (Abstract Factory + Registry Pattern)

Creates the appropriate LLM service based on configuration.
Uses a registry so new providers can be added without modifying existing code.

Design Patterns:
  - Abstract Factory: LLMServiceFactory.create(provider)
  - Registry Pattern: Internal _ProviderRegistry
  - Open/Closed: New providers register themselves without touching factory code
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


class _ProviderRegistry:
    """Internal registry for LLM provider constructors."""

    def __init__(self) -> None:
        self._constructors: dict[str, Callable] = {}

    def register(self, name: str, constructor: Callable) -> None:
        """Register an LLM provider constructor."""
        key = name.lower()
        self._constructors[key] = constructor
        logger.info(f"Registered LLM provider: {name}")

    def get(self, name: str) -> Callable:
        """Get an LLM provider constructor by name."""
        key = name.lower()
        if key not in self._constructors:
            available = ", ".join(self._constructors.keys())
            raise ValueError(f"Unknown LLM provider '{name}'. Available: {available}")
        return self._constructors[key]

    def list_providers(self) -> list[str]:
        """Return a list of all registered provider names."""
        return list(self._constructors.keys())


# Global singleton registry
_registry = _ProviderRegistry()


class LLMServiceFactory:
    """
    Abstract Factory for creating LLM service instances.

    Usage:
        factory = LLMServiceFactory()
        ollama = factory.create("ollama")
        sarvam = factory.create("sarvam_cloud")
    """

    @classmethod
    def register_provider(cls, name: str, constructor: Callable) -> None:
        """Register a new LLM provider at runtime."""
        _registry.register(name, constructor)

    @classmethod
    def create(cls, provider: str):
        """Create an LLM service instance for the given provider."""
        constructor = _registry.get(provider)
        instance = constructor()
        logger.info(f"Created LLM service for provider: {provider}")
        return instance

    @classmethod
    def list_providers(cls) -> list[str]:
        """Return a list of all registered provider names."""
        return _registry.list_providers()


def _register_default_providers() -> None:
    """Auto-register built-in providers to keep the module self-contained."""
    try:
        from services.ollama_service import OllamaService
        _registry.register("ollama", OllamaService)
    except ImportError as exc:
        logger.warning(f"Could not register Ollama provider: {exc}")

    try:
        from services.sarvam_service import SarvamCloudService
        _registry.register("sarvam_cloud", SarvamCloudService)
    except ImportError as exc:
        logger.warning(f"Could not register Sarvam Cloud provider: {exc}")


_register_default_providers()
