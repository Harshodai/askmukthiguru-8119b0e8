"""
Unit tests for LangGraph node functions in nodes.py, specifically verifying
reflect_on_answer, verify_answer, and explain_retrieval.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.nodes as nodes
from rag.states import GraphState


def test_strip_cot_removes_reasoning_scaffolding():
    raw = """We are given a conversation history and a knowledge base.

Beloved, the Four Sacred Secrets are spiritual vision, inner truth, universal intelligence, and spiritual right action."""

    cleaned = nodes.strip_cot(raw)

    assert "We are given" not in cleaned
    assert "Four Sacred Secrets" in cleaned


def test_generation_kwargs_bound_by_intent():
    # 1.7 caps: distress=2048, fast/tier2_simple=150, deep/tier3_complex=800, adversarial=600
    assert nodes._generation_kwargs({"intent": "DISTRESS"})["num_predict"] == 2048
    assert nodes._generation_kwargs({"query_tier": "tier2_simple"})["num_predict"] == 150
    assert nodes._generation_kwargs({"intent": "ADVERSARIAL"})["num_predict"] == 600


class MockEmbeddingService:
    def encode_single_full(self, text):
        return {"dense": [0.1] * 384, "sparse": {}}

    def encode_batch(self, texts):
        return {"dense": [[0.1] * 384 for _ in texts]}


@pytest.fixture
def mock_services():
    # Setup mock services
    mock_ollama = AsyncMock()
    mock_ollama.generate.return_value = "Alternative answer content\nQuestion 1\nQuestion 2"
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
    assert "Answer appears valid and consistent" in result["reflection_feedback"]
    assert mock_ld.score_faithfulness.call_count == 1


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
    assert "Faithfulness below threshold" in result["reflection_feedback"]


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
        relevant_docs=[{"text": "Sri Preethaji teaches that the Beautiful State is a state of connection, a state of oneness, a state of peace, a state of love, a state of joy, and a state of compassion. It is not just an absence of suffering, but a positive presence of connection.", "source_url": "url1"}],
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
    assert result["confidence_score"] == 6.32
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


@pytest.mark.asyncio
async def test_intent_router_meditation_step_robustness(mock_services):
    from rag.nodes.intent import intent_router
    
    # Test case 1: meditation_step is a string number
    state = GraphState(
        question="yes",
        chat_history=[],
        intent=None,
        meditation_step="3",
        user_id=None,
        detected_language="en",
        memory_context="",
        ab_model="primary",
    )
    result = await intent_router(state)
    assert result["intent"] == "MEDITATION_CONTINUE"
    assert result["meditation_step"] == 3
    
    # Test case 2: meditation_step is None (TypeError test)
    mock_ollama, _ = mock_services
    mock_ollama.generate.return_value = "INTENT: CASUAL\nCOMPLEXITY: simple"
    state = GraphState(
        question="hello",
        chat_history=[],
        intent=None,
        meditation_step=None,
        user_id=None,
        detected_language="en",
        memory_context="",
        ab_model="primary",
    )
    result = await intent_router(state)
    assert result.get("meditation_step", 0) == 0 or result.get("intent") == "CASUAL"

    # Test case 3: meditation_step is invalid string (ValueError test)
    state = GraphState(
        question="hello",
        chat_history=[],
        intent=None,
        meditation_step="invalid_step_str",
        user_id=None,
        detected_language="en",
        memory_context="",
        ab_model="primary",
    )
    result = await intent_router(state)
    assert result.get("meditation_step", 0) == 0 or result.get("intent") == "CASUAL"

