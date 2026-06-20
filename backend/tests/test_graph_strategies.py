"""
Unit tests for rag/graph_strategies.py.

Focuses on the fail-closed lightweight_verify node and graph wiring helpers.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rag.graph_strategies import lightweight_verify, route_after_intent
from rag.states import GraphState


def _make_state(
    *,
    query_tier: str = "standard",
    answer: str = "The Beautiful State is a state of inner connection.",
    context: list[dict] | None = None,
    question: str = "What is the Beautiful State?",
) -> GraphState:
    """Build a minimal GraphState for lightweight_verify tests."""
    return GraphState(
        question=question,
        chat_history=[],
        request_id="test-req-123",
        intent="FACTUAL",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=context
        if context is not None
        else [
            {
                "content": "Sri Preethaji teaches that the Beautiful State is a state of connection and oneness.",
                "source_url": "url1",
            }
        ],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=[],
        is_complex=False,
        selected_clusters=[],
        hints=[],
        answer=answer,
        citations=[],
        is_faithful=None,
        needs_correction=False,
        reflection_feedback=None,
        verification=None,
        confidence_score=None,
        input_blocked=False,
        output_blocked=False,
        block_reason=None,
        meditation_step=0,
        meditation_response=None,
        final_answer=None,
        error=None,
        context_layers=None,
        citation_reasoning={},
        metrics={},
        user_id=None,
        detected_language="en",
        memory_context="",
        ab_model="primary",
        query_tier=query_tier,
    )


@pytest.fixture
def mock_lettuce(monkeypatch):
    """Patch LettuceDetectService and DI container for lightweight_verify."""
    container = MagicMock()
    container.embedding = MagicMock()
    monkeypatch.setattr("app.dependencies.get_container", lambda: container)

    score_faithfulness_mock = MagicMock(
        return_value={
            "is_faithful": True,
            "score": 0.9,
            "details": "Grounded.",
            "unsupported_sentences": [],
        }
    )

    class FakeLettuceDetectService:
        def __init__(self, embedder=None):
            self.embedder = embedder
            self.score_faithfulness = score_faithfulness_mock

    monkeypatch.setattr(
        "services.lettuce_detect_service.LettuceDetectService", FakeLettuceDetectService
    )
    return score_faithfulness_mock


@pytest.mark.asyncio
async def test_lightweight_verify_skips_fast_tier():
    state = _make_state(query_tier="fast")
    result = await lightweight_verify(state)
    assert result["is_faithful"] is True
    assert result["verification"]["skipped"] is True


@pytest.mark.asyncio
async def test_lightweight_verify_skips_tier2_simple():
    state = _make_state(query_tier="tier2_simple")
    result = await lightweight_verify(state)
    assert result["is_faithful"] is True
    assert result["verification"]["skipped"] is True


@pytest.mark.asyncio
async def test_lightweight_verify_fails_closed_on_empty_answer():
    state = _make_state(answer="")
    result = await lightweight_verify(state)
    assert result["is_faithful"] is False
    assert result["verification"]["reason"] == "empty answer or context"


@pytest.mark.asyncio
async def test_lightweight_verify_fails_closed_on_empty_context():
    state = _make_state(context=[])
    result = await lightweight_verify(state)
    assert result["is_faithful"] is False
    assert result["verification"]["reason"] == "empty answer or context"


@pytest.mark.asyncio
async def test_lightweight_verify_fails_closed_when_lettuce_returns_unfaithful(mock_lettuce):
    mock_lettuce.return_value = {
        "is_faithful": False,
        "score": 0.18,
        "details": "Hallucination detected.",
        "unsupported_sentences": ["Unsupported claim."],
    }

    state = _make_state()
    result = await lightweight_verify(state)

    assert result["is_faithful"] is False
    assert result["verification"]["score"] == 0.18
    assert result["verification"]["unsupported_sentences"] == ["Unsupported claim."]


@pytest.mark.asyncio
async def test_lightweight_verify_passes_when_lettuce_returns_faithful(mock_lettuce):
    state = _make_state()
    result = await lightweight_verify(state)

    assert result["is_faithful"] is True
    assert result["verification"]["score"] == 0.9


@pytest.mark.asyncio
async def test_lightweight_verify_threshold_overrides_faithful_flag(mock_lettuce):
    # Lettuce claims faithful but score is below the configured threshold.
    mock_lettuce.return_value = {
        "is_faithful": True,
        "score": 0.1,
        "details": "Low score.",
        "unsupported_sentences": [],
    }

    state = _make_state()
    result = await lightweight_verify(state)

    assert result["is_faithful"] is False
    assert result["verification"]["score"] == 0.1


@pytest.mark.asyncio
async def test_lightweight_verify_fails_closed_on_missing_result_keys(mock_lettuce):
    # Simulate a malformed result with no is_faithful or score keys.
    mock_lettuce.return_value = {"details": "unknown"}

    state = _make_state()
    result = await lightweight_verify(state)

    assert result["is_faithful"] is False
    assert result["verification"]["score"] == 0.0


@pytest.mark.asyncio
async def test_lightweight_verify_fails_closed_on_exception(mock_lettuce):
    mock_lettuce.side_effect = RuntimeError("model exploded")

    state = _make_state()
    result = await lightweight_verify(state)

    assert result["is_faithful"] is False
    assert result["confidence_score"] == 0.0
    assert "model exploded" in result["verification"]["error"]


@pytest.mark.asyncio
async def test_lightweight_verify_no_doctrine_auto_pass_heuristic(mock_lettuce):
    # Even with doctrine keywords, a bad score must remain unfaithful.
    mock_lettuce.return_value = {
        "is_faithful": False,
        "score": 0.1,
        "details": "Low semantic overlap.",
        "unsupported_sentences": [],
    }

    state = _make_state(
        answer=(
            "Deeksha, meditation, and the Four Sacred Secrets are all about consciousness, "
            "but unsupported claims remain unsupported."
        )
    )
    result = await lightweight_verify(state)

    assert result["is_faithful"] is False


def test_route_after_intent_routes_distress():
    state = GraphState(
        question="I feel anxious",
        chat_history=[],
        request_id="r1",
        intent="DISTRESS",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=[],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=[],
        is_complex=False,
        selected_clusters=[],
        hints=[],
        answer=None,
        citations=[],
        is_faithful=None,
        needs_correction=False,
        reflection_feedback=None,
        verification=None,
        confidence_score=None,
        input_blocked=False,
        output_blocked=False,
        block_reason=None,
        meditation_step=0,
        meditation_response=None,
        final_answer=None,
        error=None,
        context_layers=None,
        citation_reasoning={},
        metrics={},
        user_id=None,
        detected_language="en",
        memory_context="",
        ab_model="primary",
    )
    assert route_after_intent(state) == "distress"
