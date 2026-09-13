"""C4 body-bound guard (Task 8): chat request bodies must be bounded.

Root cause: `ChatRequest.user_message` (10k) and `attachment_context` (8k) are
bounded but `MessagePayload.content` has no max_length and `messages` has no
length cap, so a single turn can carry an unbounded history payload into the
pipeline, blowing context, cost and latency budgets.
"""

import pytest
from pydantic import ValidationError

from app.schemas import ChatRequest, MessagePayload

_MESSAGE_MAX = 10_000
_HISTORY_MAX = 50


def _max_len(field) -> int | None:
    # Pydantic v2 stores Field(max_length=...) as annotated_types.MaxLen in metadata.
    for m in field.metadata:
        if hasattr(m, "max_length"):
            return m.max_length
    return None


def test_message_content_has_max_length():
    cap = _max_len(MessagePayload.model_fields["content"])
    assert cap is not None, "MessagePayload.content is unbounded"
    assert cap <= _MESSAGE_MAX


def test_messages_list_is_bounded():
    cap = _max_len(ChatRequest.model_fields["messages"])
    assert cap is not None, "ChatRequest.messages is unbounded"
    assert cap <= _HISTORY_MAX


def test_oversized_content_rejected():
    with pytest.raises(ValidationError):
        MessagePayload(role="user", content="x" * (_MESSAGE_MAX + 1))


def test_oversized_history_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(
            messages=[
                {"role": "user", "content": "hi"} for _ in range(_HISTORY_MAX + 1)
            ],
            user_message="hi",
        )
