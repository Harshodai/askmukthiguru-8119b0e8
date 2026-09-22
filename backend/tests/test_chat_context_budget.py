from app.config import settings
from services.chat_context_budget import (
    CONTEXT_ERROR_CODE,
    assess_conversation_context,
    max_chat_input_tokens,
)


def test_context_budget_uses_existing_server_settings(monkeypatch):
    monkeypatch.setattr(settings, "context_window_total", 1000)
    monkeypatch.setattr(settings, "context_system_prompt_reserve", 0.20)
    monkeypatch.setattr(settings, "context_history_reserve", 0.10)
    monkeypatch.setattr(settings, "llm_max_tokens_deep", 100)

    assert max_chat_input_tokens() == 600


def test_context_budget_is_script_aware_and_exhausted(monkeypatch):
    monkeypatch.setattr(settings, "context_window_total", 1000)
    monkeypatch.setattr(settings, "context_system_prompt_reserve", 0.20)
    monkeypatch.setattr(settings, "llm_max_tokens_deep", 100)

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


def test_chat_request_accepts_bounded_continuation_summary():
    from app.schemas import ChatRequest

    request = ChatRequest(
        messages=[],
        user_message="continue",
        conversation_summary="A short summary of the previous conversation.",
    )

    assert request.conversation_summary.startswith("A short summary")


def test_context_budget_counts_continuation_summary_and_attachments(monkeypatch):
    monkeypatch.setattr(settings, "context_window_total", 1000)
    monkeypatch.setattr(settings, "context_system_prompt_reserve", 0.20)
    monkeypatch.setattr(settings, "context_history_reserve", 0.10)
    monkeypatch.setattr(settings, "llm_max_tokens_deep", 100)

    result = assess_conversation_context(
        [],
        "hello",
        "en",
        conversation_summary="summary " * 400,
        attachment_context="attachment " * 400,
    )

    assert result.estimated_tokens > 1000
    assert result.exhausted is True


def _exhausted_chat_body(user_message: str):
    """Build a ChatRequest whose history alone exhausts a tiny mocked budget."""
    from app.schemas import ChatRequest

    return ChatRequest(
        messages=[{"role": "user", "content": "x " * 4000}],
        user_message=user_message,
    )


def test_context_limit_gate_blocks_ordinary_exhausted_conversation(monkeypatch):
    """Regression guard for the safe/expected path: a budget-exhausted,
    non-crisis message is still rejected with the stable 409."""
    monkeypatch.setattr(settings, "context_window_total", 1000)
    monkeypatch.setattr(settings, "context_system_prompt_reserve", 0.20)
    monkeypatch.setattr(settings, "llm_max_tokens_deep", 100)

    from app.api.chat import _conversation_context_limit_response

    response = _conversation_context_limit_response(_exhausted_chat_body("y " * 4000))

    assert response is not None
    assert response.status_code == 409


def test_context_limit_gate_never_blocks_crisis_language(monkeypatch):
    """Regression guard: a message carrying acute crisis language must reach
    DistressStage even when the conversation has exhausted its token budget.

    Without this, a long-running conversation that trips the context-limit
    gate on the same turn a user expresses suicidal ideation would return a
    generic "start a new chat" 409 before DistressStage ever ran — silently
    skipping crisis preemption. See lessons.md 2026-09-21 entry.
    """
    monkeypatch.setattr(settings, "context_window_total", 1000)
    monkeypatch.setattr(settings, "context_system_prompt_reserve", 0.20)
    monkeypatch.setattr(settings, "llm_max_tokens_deep", 100)

    from app.api.chat import _conversation_context_limit_response

    response = _conversation_context_limit_response(_exhausted_chat_body("I want to end my life"))

    assert response is None


def test_context_limit_gate_never_blocks_indic_crisis_language(monkeypatch):
    monkeypatch.setattr(settings, "context_window_total", 1000)
    monkeypatch.setattr(settings, "context_system_prompt_reserve", 0.20)
    monkeypatch.setattr(settings, "llm_max_tokens_deep", 100)

    from app.api.chat import _conversation_context_limit_response

    response = _conversation_context_limit_response(_exhausted_chat_body("आत्महत्या"))

    assert response is None
