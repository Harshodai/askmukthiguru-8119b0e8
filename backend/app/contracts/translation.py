"""Translation Service Protocol — defines the contract for translating text.

Design Patterns:
  - Protocol (duck typing): allows swapping Ollama, Sarvam Cloud,
    or future translation providers without changing consumers.
"""

from __future__ import annotations

from typing import Any, Protocol


class TranslationService(Protocol):
    """Unified interface for all translation providers (Ollama, Sarvam Cloud, etc.)."""

    async def translate_text(
        self,
        *,
        text: str,
        source_lang: str,
        target_lang: str,
        **kwargs: Any,
    ) -> str:
        """Translate text from source_lang to target_lang."""
        ...

    async def health_check(self) -> bool:
        """Return True if the translation service is reachable and healthy."""
        ...
