"""Unit tests for Gemini-first fallback in RoutingTranslationProvider.

TDD-first: written before the routing change. Verifies Gemini-first → Sarvam
fallback → raise-all contract and the gemini_provider=None no-op (Sarvam-only).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_provider(*, translate: str | Exception | None = None, health: bool = True):
    """Build a minimal TranslationProvider mock."""
    p = MagicMock()
    if translate is not None:
        if isinstance(translate, Exception):
            p.translate_text = AsyncMock(side_effect=translate)
        else:
            p.translate_text = AsyncMock(return_value=translate)
    p.health_check = AsyncMock(return_value=health)
    return p


def test_gemini_success_sarvam_not_called(monkeypatch):
    """Gemini available + succeeds → router returns Gemini text, Sarvam untouched."""
    from app.config import settings as _settings
    from services.translation.routing_provider import RoutingTranslationProvider

    monkeypatch.setattr(_settings, "gemini_translation_enabled", True, raising=False)
    monkeypatch.setattr(
        _settings, "sarvam_api_key", "real-key-not-dummy", raising=False
    )

    gemini = _fake_provider(translate="नमस्ते", health=True)
    sarvam = _fake_provider(translate="hindi", health=True)

    router = RoutingTranslationProvider(gemini_provider=gemini, sarvam_provider=sarvam)
    out = _run(router.translate_text(text="hello", source_lang="en", target_lang="hi"))

    assert out == "नमस्ते"
    gemini.translate_text.assert_awaited_once()
    sarvam.translate_text.assert_not_awaited()


def test_gemini_failure_falls_back_to_sarvam(monkeypatch):
    """Gemini raises → router falls back to Sarvam, returns Sarvam text."""
    from app.config import settings as _settings
    from services.translation.routing_provider import RoutingTranslationProvider

    monkeypatch.setattr(_settings, "gemini_translation_enabled", True, raising=False)
    monkeypatch.setattr(_settings, "sarvam_api_key", "real-key", raising=False)

    gemini = _fake_provider(translate=RuntimeError("gemini 500"), health=True)
    sarvam = _fake_provider(translate="सर्वम् उत्तर", health=True)

    router = RoutingTranslationProvider(gemini_provider=gemini, sarvam_provider=sarvam)
    out = _run(router.translate_text(text="hello", source_lang="en", target_lang="hi"))

    assert out == "सर्वम् उत्तर"
    gemini.translate_text.assert_awaited_once()
    sarvam.translate_text.assert_awaited_once()


def test_both_fail_raises_runtime(monkeypatch):
    """Gemini fails + Sarvam fails → RuntimeError (existing behavior preserved)."""
    from app.config import settings as _settings
    from services.translation.routing_provider import RoutingTranslationProvider

    monkeypatch.setattr(_settings, "gemini_translation_enabled", True, raising=False)
    monkeypatch.setattr(_settings, "sarvam_api_key", "real-key", raising=False)

    gemini = _fake_provider(translate=RuntimeError("gemini down"), health=True)
    sarvam = _fake_provider(translate=RuntimeError("sarvam down"), health=True)

    router = RoutingTranslationProvider(gemini_provider=gemini, sarvam_provider=sarvam)
    with pytest.raises(RuntimeError):
        _run(router.translate_text(text="hello", source_lang="en", target_lang="hi"))


def test_no_gemini_provider_behaves_like_sarvam_only(monkeypatch):
    """gemini_provider=None → Sarvam-only path, matching today's behavior."""
    from app.config import settings as _settings
    from services.translation.routing_provider import RoutingTranslationProvider

    monkeypatch.setattr(_settings, "gemini_translation_enabled", True, raising=False)
    monkeypatch.setattr(_settings, "sarvam_api_key", "real-key", raising=False)

    sarvam = _fake_provider(translate="केवल सर्वम्", health=True)

    router = RoutingTranslationProvider(gemini_provider=None, sarvam_provider=sarvam)
    out = _run(router.translate_text(text="hello", source_lang="en", target_lang="hi"))

    assert out == "केवल सर्वम्"
    sarvam.translate_text.assert_awaited_once()


def test_health_check_ors_gemini_and_sarvam(monkeypatch):
    """health_check must OR Gemini + Sarvam (guarded)."""
    from app.config import settings as _settings
    from services.translation.routing_provider import RoutingTranslationProvider

    monkeypatch.setattr(_settings, "sarvam_api_key", "real-key", raising=False)

    # Gemini healthy, Sarvam healthy → True.
    g_healthy = _fake_provider(health=True)
    s_healthy = _fake_provider(health=True)
    r1 = RoutingTranslationProvider(gemini_provider=g_healthy, sarvam_provider=s_healthy)
    assert _run(r1.health_check()) is True

    # Gemini unhealthy, Sarvam healthy → True (Sarvam still available).
    g_unhealthy = _fake_provider(health=False)
    r2 = RoutingTranslationProvider(gemini_provider=g_unhealthy, sarvam_provider=s_healthy)
    assert _run(r2.health_check()) is True

    # Both unhealthy → False.
    s_unhealthy = _fake_provider(health=False)
    r3 = RoutingTranslationProvider(gemini_provider=g_unhealthy, sarvam_provider=s_unhealthy)
    assert _run(r3.health_check()) is False
