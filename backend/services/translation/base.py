"""Base Translation Provider interface (Strategy Pattern).

All translation provider strategies must implement this interface to be interchangeable
via the TranslationService Protocol.
"""

from __future__ import annotations

import abc
from typing import Any


class TranslationProvider(abc.ABC):
    """Abstract Base Class for translation providers to ensure proper strategy implementation."""

    @abc.abstractmethod
    async def translate_text(
        self,
        *,
        text: str,
        source_lang: str,
        target_lang: str,
        **kwargs: Any,
    ) -> str:
        """Translate text from source_lang to target_lang."""
        pass

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Return True if the translation service is reachable and healthy."""
        pass
