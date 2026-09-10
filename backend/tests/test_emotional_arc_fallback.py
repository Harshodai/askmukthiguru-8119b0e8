"""Tests for emotional arc fallback using state_category (Task 7)."""

import uuid
from dataclasses import dataclass, field
from typing import Optional

import pytest

from rag.memory import build_memory_context
from services.user_profile_service import ConversationMemory


@dataclass
class _EpisodicMemory:
    """Minimal stand-in for an EpisodicMemoryDetail with state_category."""

    id: str
    user_id: str
    session_id: str = ""
    content: str = ""
    insight: str = ""
    state_category: Optional[str] = None
    created_at: float = 0.0
    emotional_arc: list = field(default_factory=list)
    key_insights: list = field(default_factory=list)
    follow_up_suggestions: list = field(default_factory=list)


class TestEmotionalArcFallback:
    """When emotional_arc is empty, derive distress from state_category."""

    def test_empty_arc_with_suffering_state_derives_distress_2(self):
        mem = _EpisodicMemory(
            id="ep1",
            user_id="u1",
            session_id="s1",
            content="I feel anxious",
            insight="anxiety",
            state_category="Suffering State",
            emotional_arc=[],
            key_insights=["anxiety"],
            follow_up_suggestions=[],
        )
        context = build_memory_context(
            recent_memories=[mem],
            chat_history=[{"role": "user", "content": "I feel anxious"}],
        )
        assert "distress 2" in context
        assert "Suffering State" in context

    def test_empty_arc_with_destructive_state_derives_distress_3(self):
        mem = _EpisodicMemory(
            id="ep2",
            user_id="u1",
            state_category="Destructive Self",
            emotional_arc=[],
        )
        context = build_memory_context(
            recent_memories=[mem],
            chat_history=[{"role": "user", "content": "help"}],
        )
        assert "distress 3" in context

    def test_empty_arc_with_beautiful_state_derives_distress_0(self):
        mem = _EpisodicMemory(
            id="ep3",
            user_id="u1",
            state_category="Beautiful State",
            emotional_arc=[],
        )
        context = build_memory_context(
            recent_memories=[mem],
            chat_history=[{"role": "user", "content": "I feel peaceful"}],
        )
        assert "distress 0" in context
        assert "Beautiful State" in context

    def test_nonempty_arc_preserved_as_before(self):
        """Existing emotional_arc entries are not overridden by state_category."""
        mem = _EpisodicMemory(
            id="ep4",
            user_id="u1",
            state_category="Suffering State",
            emotional_arc=[{"topic": "grief", "distress_level": 3}],
        )
        context = build_memory_context(
            recent_memories=[mem],
            chat_history=[{"role": "user", "content": "grief"}],
        )
        assert "grief" in context
        assert "distress 3" in context

    def test_no_state_category_no_arc_no_emotional_signal(self):
        mem = _EpisodicMemory(
            id="ep5",
            user_id="u1",
            state_category=None,
            emotional_arc=[],
        )
        context = build_memory_context(
            recent_memories=[mem],
            chat_history=[{"role": "user", "content": "hello"}],
        )
        assert "emotional signal" not in context


class TestLegacyConversationMemory:
    """Legacy ConversationMemory objects still work with the original path."""

    def test_legacy_emotional_arc_used_directly(self):
        mem = ConversationMemory(
            session_id=str(uuid.uuid4()),
            user_id="u1",
            started_at=1700000000,
            messages=[],
            key_insights=["peace"],
            emotional_arc=[{"topic": "calm", "distress_level": 0}],
            follow_up_suggestions=[],
        )
        context = build_memory_context(
            recent_memories=[mem],
            chat_history=[{"role": "user", "content": "peace"}],
        )
        assert "calm" in context
        assert "distress 0" in context
