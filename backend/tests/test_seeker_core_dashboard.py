"""Unit and integration tests for Seeker Core Dashboard (Layer 4 minimal context).

Anthropic research ("The Components of Agent Memory", Nov 2026):
1. Preemptively loaded Layer 4 context must be kept small (<= 120 tokens / ~480 chars).
2. Deep episodic search must be decoupled into intent-gated on-demand queries.
3. Cache fingerprints must include dashboard fingerprint for exact-cache invalidation.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.memory import (
    _SEEKER_DASHBOARD_TOKEN_BUDGET,
    _is_personal_recall_request,
    inject_memory_context,
)
from services.canonical_memory.models import SeekerCoreDashboard


def test_seeker_core_dashboard_token_and_char_limits():
    """Ensure SeekerCoreDashboard adheres to strict Layer 4 budget constraints."""
    dash = SeekerCoreDashboard(
        user_id="user-12345",
        preferred_language="en",
        spiritual_stage="sadhak",
        active_inquiry="Overcoming spiritual loneliness and finding inner stillness amidst daily turmoil",
        active_practices=["Serene Mind", "Three-Question Meditation", "Soul Sync"],
        dominant_themes=["awareness", "surrender", "compassion"],
        key_goals=["attain beautiful state", "deepen meditation"],
        preferences=["gentle tone", "depth: comprehensive"],
    )

    block = dash.to_system_prompt_block()

    # Must start and end with proper fences
    assert block.startswith("<seeker_context>")
    assert block.endswith("</seeker_context>")

    # Character count budget: strictly <= 480 chars (~120 tokens)
    assert len(block) <= 480, f"Dashboard block exceeds char budget: {len(block)} chars"

    # Core contents must be present
    assert "language: en" in block
    assert "stage: sadhak" in block
    assert "inquiry:" in block
    assert "practices:" in block


def test_seeker_core_dashboard_fingerprint_determinism_and_invalidation():
    """Fingerprint must be deterministic and change when state changes."""
    dash1 = SeekerCoreDashboard(
        user_id="user-abc",
        preferred_language="en",
        spiritual_stage="seeker",
        active_inquiry="How to quiet the mind?",
        active_practices=["Serene Mind"],
    )
    fp1 = dash1.compute_fingerprint()

    dash2 = SeekerCoreDashboard(
        user_id="user-abc",
        preferred_language="en",
        spiritual_stage="seeker",
        active_inquiry="How to quiet the mind?",
        active_practices=["Serene Mind"],
    )
    fp2 = dash2.compute_fingerprint()

    # Same state = identical fingerprint
    assert fp1 == fp2

    # Modified state = distinct fingerprint (invalidates exact cache)
    dash3 = SeekerCoreDashboard(
        user_id="user-abc",
        preferred_language="en",
        spiritual_stage="sadhak",  # evolved stage
        active_inquiry="How to quiet the mind?",
        active_practices=["Serene Mind"],
    )
    fp3 = dash3.compute_fingerprint()
    assert fp1 != fp3


def test_is_personal_recall_detection():
    """Verify that personal inquiry queries are detected, while doctrine queries are not."""
    # Personal recall triggers
    assert _is_personal_recall_request("What did I tell you about my meditation practice?") is True
    assert _is_personal_recall_request("Do you remember when I felt anxious?") is True
    assert _is_personal_recall_request("In our last conversation, what did we discuss?") is True
    assert _is_personal_recall_request("What is my preference for language?") is True
    assert _is_personal_recall_request("anything", intent="personal") is True
    assert _is_personal_recall_request("anything", intent="recall") is True

    # Pure spiritual/doctrine queries DO NOT trigger episodic search
    assert _is_personal_recall_request("What is the Beautiful State according to Sri Preethaji?") is False
    assert _is_personal_recall_request("How does Ahankara create suffering?") is False
    assert _is_personal_recall_request("Tell me about the four sacred secrets", intent="knowledge") is False
    assert _is_personal_recall_request("Namaste", intent="casual") is False


@pytest.mark.asyncio
async def test_inject_memory_context_doctrine_query_uses_only_layer_4_dashboard():
    """For general spiritual inquiries, default injection is ONLY the compact dashboard."""
    mock_svc = MagicMock()
    mock_svc.get_core = AsyncMock(
        return_value=[
            {"content": "stage: sadhak"},
            {"content": "practice: Serene Mind"},
            {"content": "inquiry: finding inner stillness"},
        ]
    )
    mock_svc.search_semantic = AsyncMock(return_value=[{"claim": "Episodic detail from 2 weeks ago"}])
    mock_svc.recent_summaries = AsyncMock(return_value=[{"summary": "Earlier session about work stress"}])

    state = {
        "user_id": "11111111-1111-4111-8111-111111111111",
        "question": "How can I cultivate inner stillness today?",
        "intent": "spiritual_inquiry",
    }

    result = await inject_memory_context(state, memory_service=mock_svc)

    assert "memory_context" in result
    ctx = result["memory_context"]

    # Must be the minimal dashboard block
    assert ctx.startswith("<seeker_context>")
    assert ctx.endswith("</seeker_context>")
    assert len(ctx) <= 480

    # Deep episodic memories MUST NOT be in the default context
    assert "Episodic detail" not in ctx
    assert "work stress" not in ctx

    # Trace telemetry
    assert result["evaluation_trace"]["episodic_retrieved"] is False
    assert result["evaluation_trace"]["scd_fingerprint"] != ""
    assert result["evaluation_trace"]["memory_chars"] <= 480

    # Semantic search was NOT called because it was not a personal recall query
    mock_svc.search_semantic.assert_not_called()


@pytest.mark.asyncio
async def test_inject_memory_context_personal_recall_retrieves_episodic():
    """For personal recall questions, episodic memories are retrieved and formatted."""
    mock_svc = MagicMock()
    mock_svc.get_core = AsyncMock(
        return_value=[
            {"claim": "User lives in Bangalore"},
            {"claim": "User practices Serene Mind"},
        ]
    )
    mock_svc.search_semantic = AsyncMock(
        return_value=[{"claim": "User shared feeling restless during meditation"}]
    )
    mock_svc.recent_summaries = AsyncMock(
        return_value=[{"summary": "Discussed overcoming restlessness", "topics": ["peace"]}]
    )

    state = {
        "user_id": "22222222-2222-4222-8222-222222222222",
        "question": "What did I share about feeling restless during meditation?",
        "intent": "personal_inquiry",
    }

    result = await inject_memory_context(state, memory_service=mock_svc)

    assert "memory_context" in result
    ctx = result["memory_context"]

    # Episodic detail should be included for personal recall
    assert "restless during meditation" in ctx
    assert result["evaluation_trace"]["episodic_retrieved"] is True
    mock_svc.search_semantic.assert_called_once()
