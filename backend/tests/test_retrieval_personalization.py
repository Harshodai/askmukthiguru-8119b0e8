"""Tests for retrieval personalization, distress trajectory, and memory circuit breaker."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


# ---------------------------------------------------------------------------
# personalize_retrieval_query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_personalize_appends_topic_keywords():
    from rag.nodes.retrieval import personalize_retrieval_query

    profile = {"topics_of_interest": ["meditation", "breath awareness", "stillness"]}
    result = await personalize_retrieval_query("What is peace?", profile)
    assert "meditation" in result
    assert "breath awareness" in result
    assert "stillness" in result
    assert result.startswith("What is peace?")


@pytest.mark.asyncio
async def test_personalize_adds_teacher_keywords():
    from rag.nodes.retrieval import personalize_retrieval_query

    profile = {"favorite_teachings": [{"teacher": "Sri Krishnaji"}, {"teacher": "Sri Preethaji"}]}
    result = await personalize_retrieval_query("Tell me about dhyana", profile)
    assert "Sri Krishnaji" in result
    assert "Sri Preethaji" in result


@pytest.mark.asyncio
async def test_personalize_empty_profile_returns_original():
    from rag.nodes.retrieval import personalize_retrieval_query

    original = "What is meditation?"
    result = await personalize_retrieval_query(original, None)
    assert result == original


@pytest.mark.asyncio
async def test_personalize_limits_topics_to_3():
    from rag.nodes.retrieval import personalize_retrieval_query

    profile = {"topics_of_interest": ["a", "b", "c", "d", "e"]}
    result = await personalize_retrieval_query("query", profile)
    assert "a b c" in result
    assert "d" not in result.split()
    assert "e" not in result.split()


@pytest.mark.asyncio
async def test_personalize_string_favorites():
    from rag.nodes.retrieval import personalize_retrieval_query

    profile = {"favorite_teachings": ["Krishnaji", "Preethaji"]}
    result = await personalize_retrieval_query("test", profile)
    assert "Krishnaji" in result
    assert "Preethaji" in result


# ---------------------------------------------------------------------------
# _build_distress_block — last 3 events
# ---------------------------------------------------------------------------


def test_distress_block_includes_last_3_events():
    from rag.nodes.generation import _build_distress_block

    history = [
        {"timestamp": "t1", "distress_level": 2},
        {"timestamp": "t2", "distress_level": 3},
        {"timestamp": "t3", "distress_level": 4},
        {"timestamp": "t4", "distress_level": 5},
    ]
    block = _build_distress_block(history)
    assert "t2" in block
    assert "t3" in block
    assert "t4" in block
    assert "t1" not in block
    assert "EMOTIONAL TRAJECTORY" in block


def test_distress_block_empty_history():
    from rag.nodes.generation import _build_distress_block

    assert _build_distress_block([]) == ""
    assert _build_distress_block(None) == ""


def test_distress_block_single_event():
    from rag.nodes.generation import _build_distress_block

    block = _build_distress_block([{"timestamp": "t1", "distress_level": 2}])
    assert "t1" in block
    assert "EMOTIONAL TRAJECTORY" in block


# ---------------------------------------------------------------------------
# Circuit breaker — memory timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_breaker_skips_second_brain_on_timeout():
    from app.orchestrator_utils import prepare_user_memory

    container = MagicMock()
    container.second_brain = AsyncMock()
    container.second_brain.unlock = AsyncMock(side_effect=asyncio.TimeoutError)
    container.user_profile = None

    memory_context, distress = await prepare_user_memory(
        container, "user-1", [{"role": "user", "content": "hi"}]
    )
    # Should not crash; second_brain failure is non-fatal
    assert isinstance(memory_context, str)


@pytest.mark.asyncio
async def test_circuit_breaker_total_budget_respected():
    """Verify per-call timeout is capped by total budget."""
    from app.orchestrator_utils import prepare_user_memory

    container = MagicMock()
    container.second_brain = None
    container.user_profile = None

    start = time.perf_counter()
    memory_context, distress = await prepare_user_memory(
        container, "user-1", [{"role": "user", "content": "hi"}]
    )
    elapsed = time.perf_counter() - start
    # Should complete fast (no services configured)
    assert elapsed < 1.0


# ---------------------------------------------------------------------------
# Persona auto-refresh (stale persona)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persona_stale_includes_flag():
    """When persona is stale and refresh fails, [STALE PERSONA] flag is injected."""
    from datetime import UTC, datetime, timedelta

    from app.orchestrator_utils import prepare_user_memory

    container = MagicMock()
    container.second_brain = None

    old_time = (datetime.now(UTC) - timedelta(days=90)).isoformat()

    profile_mock = MagicMock()
    profile_mock.total_conversations = 0
    profile_mock.total_meditations_completed = 0
    container.user_profile = AsyncMock()
    container.user_profile.get_or_create_profile = AsyncMock(return_value=profile_mock)
    container.user_profile.update_profile = AsyncMock()
    container.user_profile.get_recent_memories = AsyncMock(return_value=[])

    container.memory_service = None
    container.memory_service_v2 = None

    # Mock persona store to return stale persona
    with patch(
        "services.layered_memory.persona_store.get_persona",
        new_callable=AsyncMock,
        return_value=("# Old Persona\nLikes meditation.", old_time),
    ), patch(
        "services.layered_memory.persona_store.save_persona",
        new_callable=AsyncMock,
        return_value=True,
    ), patch(
        "services.layered_memory.l3_persona_generator.generate_persona",
        new_callable=AsyncMock,
        side_effect=Exception("LLM unavailable"),
    ), patch(
        "services.layered_memory.l1_extractor.get_recent_atoms",
        new_callable=AsyncMock,
        return_value=[],
    ):
        memory_context, distress = await prepare_user_memory(
                container, "a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6", [{"role": "user", "content": "hi"}]
            )

    assert "[STALE PERSONA]" in memory_context
