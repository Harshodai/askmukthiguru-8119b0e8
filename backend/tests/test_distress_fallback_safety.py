"""P0-3: Distress Path Deterministic Safe Fallback & HELPLINE Guarantee.

Tests that handle_distress and serene_mind.get_response NEVER return empty strings,
never fall back to 'The Guru is unable to answer this question', and guarantee
compassionate grounding instructions and crisis helplines.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.nodes.intent import handle_distress
from rag.states import GraphState
from services.serene_mind_engine import (
    DISTRESS_RESPONSES,
    DistressAssessment,
    DistressLevel,
    SereneMindEngine,
)


def test_serene_mind_get_response_none_level():
    """get_response with DistressLevel.NONE returns a non-empty grounding response."""
    engine = SereneMindEngine()
    assessment = DistressAssessment(level=DistressLevel.NONE, confidence=0.0)
    response = engine.get_response(assessment)

    assert response, "Response must not be empty for DistressLevel.NONE"
    assert response == DISTRESS_RESPONSES[DistressLevel.MILD]
    assert "grounding technique" in response.lower() or "breath" in response.lower()
    assert "The Guru is unable to answer" not in response


def test_serene_mind_get_response_none_assessment():
    """get_response with None assessment gracefully returns default response."""
    engine = SereneMindEngine()
    response = engine.get_response(None)

    assert response, "Response must not be empty when assessment is None"
    assert response == DISTRESS_RESPONSES[DistressLevel.MILD]


@pytest.mark.asyncio
async def test_handle_distress_zero_docs_none_assessment():
    """handle_distress with 0 docs and NONE level returns safe grounding response."""
    mock_retrieve = AsyncMock(return_value={"documents": []})
    mock_rerank = AsyncMock(return_value={"reranked_docs": []})
    mock_grade = AsyncMock(return_value={"relevant_docs": []})

    serene_mock = MagicMock()
    serene_mock.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.NONE, confidence=0.0)
    )
    serene_mock.get_response = MagicMock(
        return_value=DISTRESS_RESPONSES[DistressLevel.MILD]
    )

    state = GraphState(
        question="I feel overwhelmed and lost",
        chat_history=[],
        relevant_docs=[],
    )

    with (
        patch("rag.nodes.retrieval.retrieve_documents", mock_retrieve),
        patch("rag.nodes.reranking.rerank_documents", mock_rerank),
        patch("rag.nodes.reranking.grade_documents", mock_grade),
        patch("rag.nodes.intent._services._serene_mind", serene_mock),
        patch("rag.nodes.intent._services._ollama", None),
    ):
        result = await handle_distress(state, config={})

    assert isinstance(result, dict)
    final_answer = result.get("final_answer", "")
    assert final_answer, "final_answer must not be empty"
    assert "The Guru is unable to answer" not in final_answer
    assert "breath" in final_answer.lower() or "grounding" in final_answer.lower()
    assert result.get("intent") == "DISTRESS"


@pytest.mark.asyncio
async def test_handle_distress_llm_empty_generation_fallback():
    """handle_distress falls back to safe template if LLM returns empty string."""
    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(return_value="")

    serene_mock = MagicMock()
    serene_mock.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.MODERATE, confidence=0.7)
    )
    serene_mock.get_response = MagicMock(
        return_value=DISTRESS_RESPONSES[DistressLevel.MODERATE]
    )

    state = GraphState(
        question="I am feeling deeply anxious",
        chat_history=[],
        relevant_docs=[{"title": "Calmness", "text": "Inner peace is always within you"}],
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", serene_mock),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    final_answer = result.get("final_answer", "")
    assert final_answer, "final_answer must not be empty"
    assert "The Guru is unable to answer" not in final_answer
    assert "breathing" in final_answer.lower() or "serene mind" in final_answer.lower()


@pytest.mark.asyncio
async def test_handle_distress_llm_exception_fallback():
    """handle_distress falls back to safe template if LLM raises exception."""
    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(side_effect=RuntimeError("LLM service unavailable"))

    serene_mock = MagicMock()
    serene_mock.async_assess_distress = AsyncMock(
        return_value=DistressAssessment(level=DistressLevel.MODERATE, confidence=0.7)
    )
    serene_mock.get_response = MagicMock(
        return_value=DISTRESS_RESPONSES[DistressLevel.MODERATE]
    )

    state = GraphState(
        question="I am struggling with panic",
        chat_history=[],
        relevant_docs=[{"title": "Peace", "text": "Observe without judgment"}],
    )

    with (
        patch("rag.nodes.intent._services._serene_mind", serene_mock),
        patch("rag.nodes.intent._services._ollama", mock_ollama),
    ):
        result = await handle_distress(state, config={})

    final_answer = result.get("final_answer", "")
    assert final_answer, "final_answer must not be empty"
    assert "The Guru is unable to answer" not in final_answer


@pytest.mark.asyncio
async def test_handle_distress_serene_mind_none_service_fallback():
    """handle_distress falls back to get_distress_response if serene_mind is None."""
    mock_retrieve = AsyncMock(return_value={"documents": []})
    mock_rerank = AsyncMock(return_value={"reranked_docs": []})
    mock_grade = AsyncMock(return_value={"relevant_docs": []})

    state = GraphState(
        question="I am feeling lost",
        chat_history=[],
        relevant_docs=[],
    )

    with (
        patch("rag.nodes.retrieval.retrieve_documents", mock_retrieve),
        patch("rag.nodes.reranking.rerank_documents", mock_rerank),
        patch("rag.nodes.reranking.grade_documents", mock_grade),
        patch("rag.nodes.intent._services._serene_mind", None),
        patch("rag.nodes.intent._services._ollama", None),
    ):
        result = await handle_distress(state, config={})

    final_answer = result.get("final_answer", "")
    assert final_answer, "final_answer must not be empty"
    assert "The Guru is unable to answer" not in final_answer
    assert "Serene Mind meditation" in final_answer
