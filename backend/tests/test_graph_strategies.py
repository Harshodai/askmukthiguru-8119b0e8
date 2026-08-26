"""
Unit tests for rag/graph_strategies.py.

Focuses on the deep contradiction gate and graph wiring helpers.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rag.graph_strategies import route_after_intent
from rag.states import GraphState


@pytest.mark.asyncio
async def test_deep_graph_adds_contradiction_gate_for_tier4_deep():
    """DeepGraphStrategy must wire an extra contradiction gate for tier4_deep."""
    from rag.graph_strategies import DeepGraphStrategy

    strategy = DeepGraphStrategy()
    graph = strategy.build(
        ollama_service=MagicMock(),
        embedding_service=MagicMock(),
        qdrant_service=MagicMock(),
        lightrag_service=MagicMock(),
    )
    assert "deep_contradiction_gate" in graph.nodes


@pytest.mark.asyncio
async def test_deep_contradiction_gate_fail_closed_no_services():
    """deep_contradiction_gate must fail closed when no gateway or lettuce is available."""
    from rag.graph_strategies import deep_contradiction_gate
    from rag.states import GraphState

    state = GraphState(
        question="q",
        chat_history=[],
        request_id="r1",
        intent="FACTUAL",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=[{"content": "x" * 300, "source_url": "url1"}],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=[],
        is_complex=False,
        selected_clusters=[],
        hints=[],
        answer="answer text",
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
        query_tier="tier4_deep",
    )
    result = await deep_contradiction_gate(state)
    assert result["needs_correction"] is True


@pytest.mark.asyncio
async def test_deep_gate_reuses_strict_standard_verification(monkeypatch):
    from rag import graph_strategies

    gateway = MagicMock()
    gateway.verify_answer = MagicMock(side_effect=AssertionError("duplicate verifier call"))
    lettuce = MagicMock()
    lettuce.score_faithfulness = MagicMock(side_effect=AssertionError("duplicate scorer call"))
    from rag.nodes import _services

    monkeypatch.setattr(_services, "_llm_gateway", gateway)
    monkeypatch.setattr(_services, "_lettuce_detect", lettuce)
    state = GraphState(
        question="Compare two teachings",
        chat_history=[],
        request_id="r2",
        intent="FACTUAL",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=[{"content": "x" * 300, "source_url": "url1"}],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=[],
        is_complex=True,
        selected_clusters=[],
        hints=[],
        answer="A grounded answer with evidence.",
        citations=[],
        is_faithful=True,
        needs_correction=False,
        reflection_feedback=None,
        verification={"passed": True, "details": "strict standard pass"},
        faithfulness_score=0.91,
        confidence_score=9.1,
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
        query_tier="tier4_deep",
    )
    result = await graph_strategies.deep_contradiction_gate(state)
    assert result["needs_correction"] is False
    assert "reused strict standard" in result["reflection_feedback"]
    gateway.verify_answer.assert_not_called()
    lettuce.score_faithfulness.assert_not_called()


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
    assert route_after_intent(state) == "query"
    from rag.graph_strategies import route_after_intent_fast

    assert route_after_intent_fast(state) == "distress"
