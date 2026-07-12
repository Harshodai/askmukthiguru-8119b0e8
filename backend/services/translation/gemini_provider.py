"""Gemini Translation Provider strategy (via OpenRouter).

Layers Gemini ahead of Sarvam in the translation chain. Builds on
`OpenRouterService` without modifying it: OpenRouter's public `translate_text`
swallows exceptions (returns the original text), which would hide failures from
the routing provider's fallback logic. So we re-issue the same translation
prompt `OpenRouterService.translate_text` uses (lines 725-731 of
openrouter_service.py) and call `_generate_fast(..., model=settings.gemini_model)`
directly — `_generate_fast` honors `kwargs.pop("model", ...)` and re-raises on
failure, which is exactly the contract `RoutingTranslationProvider` needs to
fall through to Sarvam.

Ponytail: thin, lazy, degrades gracefully. Top-level imports kept minimal —
`OpenRouterService` is imported lazily inside `__init__` to avoid import-time
side effects (HTTP clients, circuit breakers, env reads).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

from app.config import settings
from services.translation.base import TranslationProvider

logger = logging.getLogger(__name__)

# Matches Markdown footnote-style citation markers: [^1], [^42], etc.
# Preserve these across translation — answer prose carries them; the front-end
# citation linker consumes them downstream.
_CITATION_RE = re.compile(r"\[\^(\d+)\]")


class GeminiTranslationProvider(TranslationProvider):
    """Adapter strategy: Gemini-via-OpenRouter for translation."""

    def __init__(self, openrouter_service: Optional[Any] = None) -> None:
        # Lazy import — keep module top-level free of side effects.
        if openrouter_service is None:
            from services.openrouter_service import OpenRouterService

            openrouter_service = OpenRouterService()
        self._openrouter = openrouter_service

    async def translate_text(
        self,
        *,
        text: str,
        source_lang: str,
        target_lang: str,
        **kwargs: Any,
    ) -> str:
        """Translate text via Gemini through OpenRouter; re-raise on failure."""
        if not text.strip():
            return ""

        src_code = source_lang.lower().split("-")[0]
        tgt_code = target_lang.lower().split("-")[0]
        if src_code == tgt_code:
            return text

        # Snapshot citation markers from the input before translation. If Gemini
        # strips them from its output, we re-stitch at the original positions
        # (best-effort — wrapped in try/except, never raises).
        original_markers = _CITATION_RE.findall(text)

        prompt = (
            f"You are a professional translator. Translate the following text from "
            f"language code '{src_code}' to language code '{tgt_code}'. "
            f"Provide ONLY the final translation. Do not include any notes, "
            f"explanations, or quotes. Preserve any [^N] citation markers verbatim "
            f"in their original positions.\n\nText to translate:\n{text}"
        )

        try:
            translated = await self._openrouter._generate_fast(
                system_prompt="You are a professional translator. Output only the translated text.",
                user_prompt=prompt,
                model=settings.gemini_model,
            )
        except Exception as e:
            logger.error(f"Gemini (OpenRouter) translation failed: {e}")
            raise

        translated = (translated or "").strip()

        # Best-effort re-stitch: if markers are missing from Gemini's output but
        # present in the original, append them at the end in order. Never crash.
        try:
            if original_markers:
                missing = [m for m in original_markers if f"[^{m}]" not in translated]
                if missing:
                    suffix = " " + " ".join(f"[^{m}]" for m in missing)
                    translated = translated.rstrip() + suffix
        except Exception as stitch_err:  # pragma: no cover — defensive
            logger.warning(f"Citation marker re-stitch skipped: {stitch_err}")

        return translated

    async def health_check(self) -> bool:
        """Return True if the OpenRouter gateway is configured (is_available property)."""
        try:
            return bool(self._openrouter.is_available)
        except Exception:
            return False


if __name__ == "__main__":
    # House-convention self-check — runnable directly with `python gemini_provider.py`.
    async def _selfcheck() -> None:
        if not settings.openrouter_api_key:
            print("skipped: no OPENROUTER_API_KEY configured")
            return
        from services.openrouter_service import OpenRouterService

        or_service = OpenRouterService()
        provider = GeminiTranslationProvider(openrouter_service=or_service)
        result = await provider.translate_text(
            text="Hello, world", source_lang="en", target_lang="hi"
        )
        print(f"Translated 'Hello, world' → {result!r}")
        print(f"health_check: {await provider.health_check()}")

    asyncio.run(_selfcheck())
