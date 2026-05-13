import uuid

import pytest

from rag.memory import build_memory_context, normalize_session_id
from services.user_profile_service import ConversationMemory, UserProfileService


def test_normalize_session_id_preserves_uuid():
    raw = str(uuid.uuid4())
    assert normalize_session_id(raw, "user-1") == raw


def test_normalize_session_id_maps_local_ids_stably():
    first = normalize_session_id("local-conversation-id", "user-1")
    second = normalize_session_id("local-conversation-id", "user-1")

    assert first == second
    assert str(uuid.UUID(first)) == first


def test_build_memory_context_includes_current_and_prior_signals():
    memory = ConversationMemory(
        session_id=str(uuid.uuid4()),
        user_id="user-1",
        started_at=10,
        messages=[],
        key_insights=["Beautiful State", "inner peace"],
        emotional_arc=[{"topic": "anxiety", "distress_level": 2}],
        follow_up_suggestions=["Continue Serene Mind practice"],
    )

    context = build_memory_context(
        recent_memories=[memory],
        chat_history=[
            {"role": "user", "content": "I felt overwhelmed yesterday."},
            {"role": "assistant", "content": "Let us breathe gently."},
        ],
    )

    assert "Conversation continuity context" in context
    assert "Current thread" in context
    assert "Earlier sessions" in context
    assert "Beautiful State" in context
    assert "distress 2" in context


@pytest.mark.asyncio
async def test_user_profile_memory_falls_back_to_local_cache():
    service = UserProfileService()
    memory = ConversationMemory(
        session_id=str(uuid.uuid4()),
        user_id="user-1",
        started_at=10,
        messages=[],
        key_insights=["awareness"],
        emotional_arc=[],
        follow_up_suggestions=[],
    )

    await service.save_conversation_memory(memory)
    memories = await service.get_recent_memories("user-1")

    assert memories == [memory]
