"""Contract tests for the chat request/response schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import AssistantContext, ChatRequest, ChatResponse, MessagePayload


def test_chat_request_valid():
    """A fully populated ChatRequest should validate and expose all fields."""
    request = ChatRequest(
        messages=[MessagePayload(role="user", content="hello")],
        user_message="What is the Beautiful State?",
        session_id="session-123",
        language="en",
        assistant=AssistantContext(
            slug="wisdom-guide",
            system_prompt="You are a wise guide.",
            knowledge_tags=["beautiful-state"],
        ),
    )

    assert request.user_message == "What is the Beautiful State?"
    assert request.session_id == "session-123"
    assert request.language == "en"
    assert request.meditation_step == 0
    assert request.assistant.slug == "wisdom-guide"


def test_chat_request_missing_assistant_is_optional():
    """The assistant field is optional; omitting it must not raise a validation error."""
    request = ChatRequest(
        messages=[MessagePayload(role="user", content="hello")],
        user_message="Tell me about Ekam.",
    )

    assert request.assistant is None


def test_chat_request_oversized_input_fails():
    """A user_message longer than 10,000 characters must fail validation."""
    long_message = "a" * 10001

    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(
            messages=[MessagePayload(role="user", content="hi")],
            user_message=long_message,
        )

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("user_message",) for error in errors)


def test_chat_request_empty_message_fails():
    """An empty user_message must fail the min-length validation."""
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(
            messages=[MessagePayload(role="user", content="hi")],
            user_message="",
        )

    errors = exc_info.value.errors()
    assert any(
        error["loc"] == ("user_message",) and error["type"] == "string_too_short"
        for error in errors
    )


def test_chat_response_serializes_with_defaults():
    """A minimal ChatResponse should serialize with the expected defaults."""
    response = ChatResponse(response="Namaste.")

    assert response.response == "Namaste."
    assert response.blocked is False
    assert response.citations == []
    assert response.meditation_step == 0
    assert response.cache_hit is False


def test_chat_response_includes_optional_fields():
    """Optional observability fields should be preserved in the response model."""
    response = ChatResponse(
        response="Namaste.",
        intent="FACTUAL",
        query_tier="standard",
        trace_id="trace-123",
        latency_ms=1200,
        faithfulness_score=0.92,
    )

    payload = response.model_dump()
    assert payload["intent"] == "FACTUAL"
    assert payload["query_tier"] == "standard"
    assert payload["trace_id"] == "trace-123"
    assert payload["latency_ms"] == 1200
    assert payload["faithfulness_score"] == 0.92
