"""
Unit tests for LangGraph node functions in nodes.py, specifically verifying
reflect_on_answer, verify_answer, and explain_retrieval.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.nodes as nodes
from rag.states import GraphState


class MockEmbeddingService:
    def encode_single_full(self, text):
        return {"dense": [0.1] * 384, "sparse": {}}

    def encode_batch(self, texts):
        return {"dense": [[0.1] * 384 for _ in texts]}


@pytest.fixture
def mock_services():
    # Setup mock services
    mock_ollama = AsyncMock()
    mock_embedder = MockEmbeddingService()
    mock_qdrant = MagicMock()
    mock_lightrag = MagicMock()

    # Initialize nodes with mocked services
    nodes.init_services(
        ollama=mock_ollama, embedder=mock_embedder, qdrant=mock_qdrant, lightrag=mock_lightrag
    )

    # Override LettuceDetect with a mock
    mock_ld = MagicMock()
    nodes._lettuce_detect = mock_ld

    yield mock_ollama, mock_ld


@pytest.mark.asyncio
async def test_reflect_on_answer_faithful(mock_services):
    mock_ollama, mock_ld = mock_services

    # Configure mock LettuceDetect to return faithful
    mock_ld.score_faithfulness.return_value = {
        "is_faithful": True,
        "score": 0.9,
        "details": "All sentences successfully grounded in context.",
        "unsupported_sentences": [],
    }

    state = GraphState(
        question="What is the Beautiful State?",
        chat_history=[],
        request_id="test-req-123",
        intent="FACTUAL",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=[{"text": "Sri Preethaji teaches...", "source_url": "url1"}],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=["What is the Beautiful State?"],
        is_complex=False,
        selected_clusters=[],
        hints=[],
        answer="The Beautiful State is a state of inner connection.",
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

    result = await nodes.reflect_on_answer(state)

    assert result["needs_correction"] is False
    assert result["reflection_feedback"] is None
    mock_ld.score_faithfulness.assert_called_once()


@pytest.mark.asyncio
async def test_reflect_on_answer_hallucinated(mock_services):
    mock_ollama, mock_ld = mock_services

    # Configure mock LettuceDetect to return hallucinated
    mock_ld.score_faithfulness.return_value = {
        "is_faithful": False,
        "score": 0.2,
        "details": "Hallucination detected in sentence...",
        "unsupported_sentences": ["Sri Preethaji teaches you will win 10 million dollars."],
    }

    state = GraphState(
        question="What is the Beautiful State?",
        chat_history=[],
        request_id="test-req-123",
        intent="FACTUAL",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=[{"text": "Sri Preethaji teaches...", "source_url": "url1"}],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=["What is the Beautiful State?"],
        is_complex=False,
        selected_clusters=[],
        hints=[],
        answer="Sri Preethaji teaches you will win 10 million dollars.",
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

    result = await nodes.reflect_on_answer(state)

    assert result["needs_correction"] is True
    assert "Hallucination detected" in result["reflection_feedback"]


@pytest.mark.asyncio
async def test_verify_answer_node(mock_services):
    mock_ollama, mock_ld = mock_services

    mock_ld.score_faithfulness.return_value = {
        "is_faithful": True,
        "score": 0.85,
        "details": "Grounded.",
        "unsupported_sentences": [],
    }

    state = GraphState(
        question="What is the Beautiful State?",
        chat_history=[],
        request_id="test-req-123",
        intent="FACTUAL",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=[{"text": "Sri Preethaji teaches...", "source_url": "url1"}],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=["What is the Beautiful State?"],
        is_complex=False,
        selected_clusters=[],
        hints=[],
        answer="The Beautiful State is a state of inner connection.",
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

    result = await nodes.verify_answer(state)

    assert result["is_faithful"] is True
    assert result["verification"]["passed"] is True
    assert result["confidence_score"] == 8.5
    assert result["faithfulness_score"] == 0.85


@pytest.mark.asyncio
async def test_explain_retrieval_node(mock_services):
    mock_ollama, mock_ld = mock_services

    # Configure mock Ollama generate method
    mock_ollama.generate.return_value = "This document describes the Beautiful State."

    state = GraphState(
        question="What is the Beautiful State?",
        chat_history=[],
        request_id="test-req-123",
        intent="FACTUAL",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=[
            {"text": "Doc 1 text...", "source_url": "url1"},
            {"text": "Doc 2 text...", "source_url": "url2"},
        ],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=["What is the Beautiful State?"],
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

    result = await nodes.explain_retrieval(state)

    assert "url1" in result["citation_reasoning"]
    assert "url2" in result["citation_reasoning"]
    assert result["citation_reasoning"]["url1"] == "This document describes the Beautiful State."
    assert mock_ollama.generate.call_count == 2
