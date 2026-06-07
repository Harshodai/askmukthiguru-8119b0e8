"""
Mukthi Guru — LLM Service Protocols

SOLID Principles Applied:
  - Interface Segregation: Small, focused protocols instead of a single fat interface.
  - Dependency Inversion: All consumers depend on these protocols, not concrete classes.

This module defines the contract that every LLM service implementation must follow.
By programming against these abstractions, the rest of the codebase stays decoupled
from specific providers (Ollama, Sarvam, OpenRouter, etc.).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class IGenerator(Protocol):
    """Protocol for synchronous and streaming text generation."""

    async def generate(self, system_prompt: str, user_prompt: str, context: str = "", **kwargs) -> str:
        """Generate a complete text response."""
        ...

    async def generate_stream(self, system_prompt: str, user_prompt: str, context: str = "", **kwargs) -> AsyncIterator[str]:
        """Generate a streaming text response, yielding tokens as they arrive."""
        ...


class IClassifier(Protocol):
    """Protocol for LLM-powered classification tasks."""

    async def classify_intent(self, message: str, **kwargs) -> str:
        """Classify a user message into an intent category."""
        ...

    async def classify_complexity(self, text: str) -> str:
        """Classify a user question as 'simple' or 'complex'."""
        ...

    async def classify_distress_structured(self, message: str) -> dict:
        """Assess whether a message signals emotional distress, returning structured data."""
        ...


class IAvailable(Protocol):
    """Protocol for health/availability checks."""

    async def health_check(self) -> bool:
        """Return True if the service is currently healthy."""
        ...

    @property
    def is_available(self) -> bool:
        """Property indicating if the service is available for use."""
        ...


class ILLMService(IGenerator, IClassifier, IAvailable, Protocol):
    """
    Unified protocol that combines generation, classification, and availability.

    Any concrete LLM service (OllamaService, SarvamCloudService, etc.)
    is expected to satisfy this protocol.
    """
    pass
