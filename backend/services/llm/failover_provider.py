"""Cross-provider failover wrapper for the main generation call.

Wraps container.ollama (the active LLMProvider strategy) so a fully-exhausted
primary provider — e.g. OpenRouter after both its primary and same-provider
fallback models degrade — retries once against a different provider (NIM)
before returning a degraded answer to the user. NIM has its own account,
quota, and rate-limit bucket, entirely independent of OpenRouter's.

Only generate() gets failover behavior; every other LLMProvider method
(classify, grade_relevance, etc.) delegates straight through to the primary
via __getattr__ — those sub-tasks already degrade gracefully within their
own provider and don't produce the user-facing "connection issue" text this
wrapper exists to avoid.
"""

from __future__ import annotations

import logging
from typing import Any

from app.constants import is_graceful_degradation

logger = logging.getLogger(__name__)


class FailoverLLMProvider:
    """Delegates to `primary`; retries `fallback` if generate() degrades."""

    def __init__(self, primary: Any, fallback: Any) -> None:
        self._primary = primary
        self._fallback = fallback

    async def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        try:
            result = await self._primary.generate(system_prompt, user_prompt, **kwargs)
        except Exception as exc:
            logger.warning(f"Primary LLM provider raised during generate — trying fallback: {exc}")
            try:
                return await self._fallback.generate(system_prompt, user_prompt, **kwargs)
            except Exception as fallback_exc:
                logger.warning(f"Fallback LLM provider also raised: {fallback_exc}")
                return "I'm experiencing a temporary connection issue with my backend services."

        if is_graceful_degradation(result):
            logger.warning("Primary LLM provider degraded during generate — trying fallback provider")
            try:
                return await self._fallback.generate(system_prompt, user_prompt, **kwargs)
            except Exception as exc:
                logger.warning(f"Fallback LLM provider also failed: {exc}")
                return result
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._primary, name)


if __name__ == "__main__":
    import asyncio

    class _Degraded:
        async def generate(self, *a, **kw):
            return "I'm experiencing a temporary connection issue with my backend services."

    class _Ok:
        async def generate(self, *a, **kw):
            return "a real answer"

    async def _demo():
        wrapper = FailoverLLMProvider(_Degraded(), _Ok())
        answer = await wrapper.generate("sys", "user")
        assert answer == "a real answer", answer
        print("FailoverLLMProvider self-check OK")

    asyncio.run(_demo())
