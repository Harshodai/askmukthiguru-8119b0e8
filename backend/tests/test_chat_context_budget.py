import pytest

from app.config import settings
from services.chat_context_budget import (
    CONTEXT_ERROR_CODE,
    assess_conversation_context,
    max_chat_input_tokens,
)


def test_context_budget_uses_existing_server_settings(monkeypatch):
    monkeypatch.setattr(settings, "context_window_total", 1000)
    monkeypatch.setattr(settings, "context_system_prompt_reserve", 0.20)
    monkeypatch.setattr(settings, "max_tokens_per_request", 5000)

    assert max_chat_input_tokens() == 800


def test_context_budget_is_script_aware_and_exhausted(monkeypatch):
    monkeypatch.setattr(settings, "context_window_total", 1000)
    monkeypatch.setattr(settings, "context_system_prompt_reserve", 0.20)
    monkeypatch.setattr(settings, "max_tokens_per_request", 1000)

    result = assess_conversation_context(
        [{"role": "user", "content": "తెలుగు " * 320}],
        "ఇంకా " * 80,
        "te",
    )

    assert result.exhausted is True
    assert result.remaining_tokens == 0
    assert result.warn_at_tokens <= result.max_input_tokens


def test_context_budget_ignores_disallowed_roles():
    result = assess_conversation_context(
        [
            {"role": "system", "content": "x " * 10000},
            {"role": "user", "content": "hello"},
        ],
        "world",
        "en",
    )

    assert result.estimated_tokens == 2


def test_error_code_is_stable():
    assert CONTEXT_ERROR_CODE == "conversation_context_exhausted"
