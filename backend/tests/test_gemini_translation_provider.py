"""Unit tests for GeminiTranslationProvider.

TDD-first: written before the provider implementation. Exercises the
OpenRouter-backed translation path: model selection, error propagation (so the
routing provider can fall back to Sarvam), citation-marker preservation, and
the health check surface.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


def _run(coro):
    """Run a coroutine in a sync test fn (no pytest-asyncio fixture coupling)."""
    return asyncio.get_event_loop().run_until_complete(coro)


def test_translate_text_calls_openrouter_with_gemini_model(monkeypatch):
    """The configured gemini_model must reach OpenRouter via _generate_fast."""
    from app.config import settings as _settings  # noqa: F401  (ensures import)
    from services.translation.gemini_provider import GeminiTranslationProvider

    monkeypatch.setattr(_settings, "gemini_model", "google/gemini-2.5-flash", raising=False)

    fake_or = MagicMock()
    fake_or._generate_fast = AsyncMock(return_value="नमस्ते")
    fake_or.is_available = True

    provider = GeminiTranslationProvider(openrouter_service=fake_or)
    out = _run(
        provider.translate_text(
            text="Hello, world", source_lang="en", target_lang="hi"
        )
    )

    assert out == "नमस्ते"
    fake_or._generate_fast.assert_awaited_once()
    _, kwargs = fake_or._generate_fast.call_args
    assert kwargs.get("model") == "google/gemini-2.5-flash"


def test_translate_text_reraises_on_openrouter_exception(monkeypatch):
    """Gemini provider MUST re-raise so RoutingTranslationProvider falls to Sarvam."""
    from app.config import settings as _settings  # noqa: F401
    from services.translation.gemini_provider import GeminiTranslationProvider

    monkeypatch.setattr(_settings, "gemini_model", "google/gemini-2.5-flash", raising=False)

    fake_or = MagicMock()
    fake_or._generate_fast = AsyncMock(side_effect=RuntimeError("openrouter 503"))
    fake_or.is_available = True

    provider = GeminiTranslationProvider(openrouter_service=fake_or)
    with pytest.raises(RuntimeError, match="503"):
        _run(
            provider.translate_text(
                text="Hello [^1]", source_lang="en", target_lang="hi"
            )
        )


def test_translate_text_preserves_citation_markers_when_or_returns_markers(monkeypatch):
    """If OpenRouter returns markers intact, leave them in place."""
    from app.config import settings as _settings  # noqa: F401
    from services.translation.gemini_provider import GeminiTranslationProvider

    monkeypatch.setattr(_settings, "gemini_model", "google/gemini-2.5-flash", raising=False)

    fake_or = MagicMock()
    fake_or._generate_fast = AsyncMock(return_value="उत्तर [^1]")
    fake_or.is_available = True

    provider = GeminiTranslationProvider(openrouter_service=fake_or)
    out = _run(
        provider.translate_text(
            text="Answer with citation [^1]", source_lang="en", target_lang="hi"
        )
    )
    assert "[^1]" in out


def test_translate_text_restitches_markers_when_stripped(monkeypatch):
    """If Gemini strips markers from response, re-stitch them from the input."""
    from app.config import settings as _settings  # noqa: F401
    from services.translation.gemini_provider import GeminiTranslationProvider

    monkeypatch.setattr(_settings, "gemini_model", "google/gemini-2.5-flash", raising=False)

    fake_or = MagicMock()
    # Gemini dropped [^1] from the translation.
    fake_or._generate_fast = AsyncMock(return_value="यह एक उत्तर है")
    fake_or.is_available = True

    provider = GeminiTranslationProvider(openrouter_service=fake_or)
    out = _run(
        provider.translate_text(
            text="This is an answer [^1] and [^2]", source_lang="en", target_lang="hi"
        )
    )
    # Best-effort: at least one marker recovered from the original must be present.
    assert "[^1]" in out or "[^2]" in out


def test_health_check_false_when_openrouter_unavailable():
    """is_available is a property on OpenRouterService → health_check returns bool."""
    from services.translation.gemini_provider import GeminiTranslationProvider

    fake_or = MagicMock()
    fake_or.is_available = False

    provider = GeminiTranslationProvider(openrouter_service=fake_or)
    out = _run(provider.health_check())
    assert out is False


def test_health_check_true_when_openrouter_available():
    from services.translation.gemini_provider import GeminiTranslationProvider

    fake_or = MagicMock()
    fake_or.is_available = True

    provider = GeminiTranslationProvider(openrouter_service=fake_or)
    assert _run(provider.health_check()) is True
