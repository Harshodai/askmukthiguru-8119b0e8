"""The live provider (openrouter) must get a real translator, and it must never raise.

Until 2026-09-28 LLM_PROVIDER=openrouter fell to _NoopTranslationProvider, so every
"translate to English / back to the seeker's language" call silently returned its
input. Several stage call sites translate without a try/except, so the wired chain
must degrade to the source text rather than raise.
"""

import asyncio

from app.config import settings


class _FakeOpenRouter:
    def __init__(self, gemini_fails: bool, fallback_fails: bool):
        self.gemini_fails = gemini_fails
        self.fallback_fails = fallback_fails

    async def generate_raw(self, *args, **kwargs):  # the Gemini provider's call
        if self.gemini_fails:
            raise RuntimeError("gemini down")
        return "GEMINI:" + kwargs.get("user_prompt", "")[-5:]

    async def translate_text(self, text, source_language_code, target_language_code):
        # Mirrors OpenRouterService.translate_text: returns the source text on failure.
        return text if self.fallback_fails else f"FALLBACK:{text}"


def _build(monkeypatch, service):
    import app.container as container_mod
    from services.llm.openrouter_provider import OpenRouterProvider

    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    monkeypatch.setattr(settings, "sarvam_api_key", "")
    monkeypatch.setattr(settings, "gemini_translation_enabled", True)
    monkeypatch.setattr(container_mod, "_create_llm_service", lambda: OpenRouterProvider(service))
    container = container_mod.ServiceContainer.__new__(container_mod.ServiceContainer)
    container.krutrim = None
    container._build_llm_services()
    return container.translation


def test_openrouter_gets_a_real_translator_not_the_noop(monkeypatch):
    from app.container import _NoopTranslationProvider
    from services.translation.routing_provider import RoutingTranslationProvider

    translation = _build(monkeypatch, _FakeOpenRouter(gemini_fails=False, fallback_fails=False))
    assert isinstance(translation, RoutingTranslationProvider)
    assert not isinstance(translation, _NoopTranslationProvider)


def test_gemini_failure_falls_back_to_openrouter_translate(monkeypatch):
    translation = _build(monkeypatch, _FakeOpenRouter(gemini_fails=True, fallback_fails=False))
    out = asyncio.run(translation.translate_text(text="नमस्ते", source_lang="hi", target_lang="en"))
    assert out == "FALLBACK:नमस्ते"


def test_total_failure_returns_source_text_and_never_raises(monkeypatch):
    translation = _build(monkeypatch, _FakeOpenRouter(gemini_fails=True, fallback_fails=True))
    out = asyncio.run(translation.translate_text(text="नमस्ते", source_lang="hi", target_lang="en"))
    assert out == "नमस्ते"
