"""
Cross-provider failover for Sarvam Cloud.
Falls back to Krutrim API when Sarvam provider is unavailable.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

from services.krutrim_service import KrutrimService

logger = logging.getLogger(__name__)


class SarvamFailoverService:
    """
    Wraps a primary LLM service (e.g. SarvamCloudService) with Krutrim fallback.

    If the primary service raises an exception during generate() or generate_stream(),
    falls through to KrutrimService. If Krutrim also fails, raises the last error.
    """

    def __init__(self, primary_service, krutrim: Optional[KrutrimService] = None):
        self._primary = primary_service
        self._krutrim = krutrim

    async def generate(self, system_prompt: str, user_prompt: str, context: str = "", **kwargs) -> str:
        try:
            return await self._primary.generate(system_prompt, user_prompt, context, **kwargs)
        except Exception as exc:
            logger.warning(f"Primary LLM service failed: {exc}. Trying Krutrim fallback...")
            if self._krutrim:
                return await self._krutrim.generate(system_prompt, user_prompt, **kwargs)
            raise

    async def generate_stream(self, system_prompt: str, user_prompt: str, context: str = "", **kwargs) -> AsyncIterator[str]:
        try:
            async for token in self._primary.generate_stream(system_prompt, user_prompt, context, **kwargs):
                yield token
        except Exception as exc:
            logger.warning(f"Primary LLM streaming failed: {exc}. Trying Krutrim non-streaming fallback...")
            if self._krutrim:
                result = await self._krutrim.generate(system_prompt, user_prompt, **kwargs)
                yield result
            else:
                raise

    async def health_check(self) -> bool:
        primary_ok = await self._primary.health_check()
        if not primary_ok and self._krutrim:
            return await self._krutrim.health_check()
        return primary_ok

    @property
    def circuit_breaker_registry(self):
        return getattr(self._primary, '_circuit', None)