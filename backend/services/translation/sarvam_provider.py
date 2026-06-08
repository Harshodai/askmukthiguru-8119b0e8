"""Sarvam Cloud Translation Provider strategy implementation."""

from __future__ import annotations

from typing import Any

from services.translation.base import TranslationProvider
from services.sarvam_service import SarvamCloudService


class SarvamTranslationProvider(TranslationProvider):
    """Adapter strategy wrapping SarvamCloudService to match the TranslationProvider contract."""

    def __init__(self, service: SarvamCloudService) -> None:
        self._service = service

    async def translate_text(
        self,
        *,
        text: str,
        source_lang: str,
        target_lang: str,
        **kwargs: Any,
    ) -> str:
        return await self._service.translate_text(text, source_lang, target_lang)

    async def health_check(self) -> bool:
        return await self._service.health_check()
