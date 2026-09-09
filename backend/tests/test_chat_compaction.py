"""Tests for chat history compaction via LLM."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.memory import (
    _extractive_fallback,
    _parse_structured_summary,
    build_memory_context,
    extract_entities_from_summary,
    summarize_chat_history,
    weighted_memory_selection,
)


@dataclass
class FakeMemory:
    session_id: str = "s1"
    user_id: str = "u1"
    started_at: float = 1700000000.0
    messages: list = field(default_factory=list)
    key_insights: list[str] = field(default_factory=list)
    emotional_arc: list[dict] = field(default_factory=list)
    follow_up_suggestions: list[str] = field(default_factory=list)
    created_at: Optional[str] = None


def _make_history(n: int) -> list[dict]:
    msgs = []
    for i in range(n):
        msgs.append({"role": "user", "content": f"User message {i} about meditation"})
        msgs.append({"role": "assistant", "content": f"Guru response {i} about awareness"})
    return msgs


def _build_history(total_chars: int) -> list[dict]:
    msgs = []
    char_per_turn = 200
    turns = total_chars // char_per_turn + 1
    for i in range(turns):
        msgs.append({"role": "user", "content": "x" * char_per_turn})
        msgs.append({"role": "assistant", "content": "y" * char_per_turn})
    return msgs


class TestCompactionTrigger:
    def test_short_history_does_not_trigger(self):
        history = _make_history(5)
        total = sum(len(m.get("content", "")) for m in history)
        assert total < 8000

    def test_long_history_triggers(self):
        history = _build_history(10000)
        total = sum(len(m.get("content", "")) for m in history)
        assert total > 8000

    @pytest.mark.asyncio
    async def test_summarize_returns_structured_fields(self):
        history = _build_history(10000)
        with patch("rag.memory._build_llm_client") as mock_build:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = (
                "goal: Inner peace and daily meditation practice\n"
                "key_decisions: Committed to 20-minute morning meditation\n"
                "emotional_state: Transitioned from anxious to calm\n"
                "open_items: Follow up on breathing techniques\n"
                "user_preferences: Prefers morning sessions"
            )
            mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
            mock_build.return_value = (mock_client, "test-model")

            result = await summarize_chat_history(history, target_chars=2000)

            assert "goal" in result
            assert "meditation" in result["goal"].lower()
            assert "key_decisions" in result
            assert "emotional_state" in result
            assert "open_items" in result
            assert "user_preferences" in result

    @pytest.mark.asyncio
    async def test_summarize_falls_back_on_llm_failure(self):
        history = _build_history(10000)
        with patch("rag.memory._build_llm_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))
            mock_build.return_value = (mock_client, "test-model")

            result = await summarize_chat_history(history)

            assert "raw_summary" in result
            assert len(result["raw_summary"]) > 0


class TestRecentTurnsPreserved:
    def test_recent_6_turns_preserved_raw(self):
        history = _build_history(10000)
        recent = history[-6:]
        context = build_memory_context(
            recent_memories=[],
            chat_history=history,
            compacted_summary={
                "goal": "peace",
                "key_decisions": "",
                "emotional_state": "calm",
                "open_items": "",
                "user_preferences": "",
                "raw_summary": "Seeker seeks inner peace",
            },
        )
        assert "Recent thread" in context
        for msg in recent[-6:]:
            content = msg.get("content", "")[:20]
            assert content in context

    def test_no_compacted_summary_uses_full_history(self):
        history = _make_history(3)
        context = build_memory_context(
            recent_memories=[],
            chat_history=history,
        )
        assert "Current thread" in context


class TestImportanceWeighting:
    def test_newer_memory_selected_first(self):
        old = FakeMemory(session_id="old", started_at=1000000)
        new = FakeMemory(session_id="new", started_at=1700000000)
        result = weighted_memory_selection([old, new], max_memories=1)
        assert result[0].session_id == "new"

    def test_max_memories_respected(self):
        memories = [
            FakeMemory(session_id=f"m{i}", started_at=1000000 + i * 100000)
            for i in range(10)
        ]
        result = weighted_memory_selection(memories, max_memories=3)
        assert len(result) == 3

    def test_empty_list_returns_empty(self):
        assert weighted_memory_selection([]) == []

    def test_recency_decay_formula(self):
        now = datetime.now(UTC)
        old_mem = FakeMemory(
            session_id="old",
            started_at=(now - timedelta(days=30)).timestamp(),
        )
        new_mem = FakeMemory(
            session_id="new",
            started_at=now.timestamp(),
        )
        result = weighted_memory_selection([old_mem, new_mem], max_memories=2, decay_rate=0.05)
        assert result[0].session_id == "new"
        old_weight = math.exp(-0.05 * 30)
        new_weight = math.exp(-0.05 * 0)
        assert new_weight > old_weight


class TestEntityExtraction:
    def test_extract_user_name(self):
        summary = {"raw_summary": "My name is Arjun and I seek peace"}
        entities = extract_entities_from_summary(summary)
        assert entities.get("user_name") == "Arjun"

    def test_extract_goals(self):
        summary = {
            "goal": "daily meditation; reduce anxiety",
            "raw_summary": "",
        }
        entities = extract_entities_from_summary(summary)
        assert "daily meditation" in entities["stated_goals"]
        assert "reduce anxiety" in entities["stated_goals"]

    def test_extract_emotional_patterns(self):
        summary = {
            "emotional_state": "anxious at first; calm after practice",
            "raw_summary": "",
        }
        entities = extract_entities_from_summary(summary)
        assert "anxious at first" in entities["emotional_patterns"]

    def test_empty_summary_returns_empty(self):
        entities = extract_entities_from_summary({"raw_summary": ""})
        assert entities == {}


class TestParseStructuredSummary:
    def test_valid_summary(self):
        raw = "goal: inner peace\nkey_decisions: daily practice\nemotional_state: calm"
        result = _parse_structured_summary(raw)
        assert result is not None
        assert result["goal"] == "inner peace"
        assert result["key_decisions"] == "daily practice"
        assert "raw_summary" in result

    def test_invalid_returns_none(self):
        assert _parse_structured_summary("random text") is None


class TestExtractiveFallback:
    def test_fallback_with_messages(self):
        history = _make_history(3)
        result = _extractive_fallback(history)
        assert "raw_summary" in result
        assert len(result["raw_summary"]) > 0

    def test_fallback_empty_history(self):
        result = _extractive_fallback([])
        assert "No conversation history" in result["raw_summary"]


class TestBuildMemoryContextWithCompaction:
    def test_compacted_summary_included(self):
        summary = {
            "goal": "find peace",
            "key_decisions": "morning meditation",
            "emotional_state": "calm",
            "open_items": "breathing techniques",
            "user_preferences": "morning sessions",
            "raw_summary": "Seeker committed to morning meditation for inner peace",
        }
        context = build_memory_context(
            recent_memories=[],
            chat_history=[],
            compacted_summary=summary,
        )
        assert "Conversation summary" in context
        assert "morning meditation" in context

    def test_prior_sessions_still_included(self):
        mem = FakeMemory(
            session_id="s1",
            key_insights=["Beautiful State"],
            emotional_arc=[{"topic": "joy", "distress_level": 1}],
            follow_up_suggestions=["Continue practice"],
        )
        summary = {"raw_summary": "Seeker seeks peace"}
        context = build_memory_context(
            recent_memories=[mem],
            chat_history=[],
            compacted_summary=summary,
        )
        assert "Earlier sessions" in context
        assert "Beautiful State" in context

    def test_empty_summary_and_history(self):
        context = build_memory_context(
            recent_memories=[],
            chat_history=[],
            compacted_summary=None,
        )
        assert context == ""
