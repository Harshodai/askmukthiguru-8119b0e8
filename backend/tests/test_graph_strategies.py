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


def _reflection_state(**overrides):
    base = dict(
        question="q",
        chat_history=[],
        request_id="r1",
        intent="FACTUAL",
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
        needs_correction=True,
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
    base.update(overrides)
    return GraphState(**base)


def test_route_after_reflection_default_flag_off_goes_straight_to_rewrite(monkeypatch):
    """rag_regenerate_before_rewrite defaults False -- must not change existing behavior."""
    from rag.graph_strategies import _route_after_reflection, settings

    monkeypatch.setattr(settings, "rag_regenerate_before_rewrite", False, raising=False)
    state = _reflection_state(rewrite_count=0)
    assert _route_after_reflection(state) == "rewrite"


def test_route_after_reflection_flag_on_regenerates_on_first_failure(monkeypatch):
    """With the flag on, the FIRST correction attempt regenerates instead of re-retrieving."""
    from rag.graph_strategies import _route_after_reflection, settings

    monkeypatch.setattr(settings, "rag_regenerate_before_rewrite", True, raising=False)
    state = _reflection_state(rewrite_count=0)
    assert _route_after_reflection(state) == "regenerate"


def test_route_after_reflection_flag_on_second_failure_still_rewrites(monkeypatch):
    """A second correction (rewrite_count>=1) always goes to the full rewrite, never regenerate again."""
    from rag.graph_strategies import _route_after_reflection, settings

    monkeypatch.setattr(settings, "rag_regenerate_before_rewrite", True, raising=False)
    monkeypatch.setattr(settings, "rag_max_rewrites", 2, raising=False)
    state = _reflection_state(rewrite_count=1)
    assert _route_after_reflection(state) == "rewrite"


@pytest.mark.asyncio
async def test_regenerate_gate_increments_rewrite_count_and_no_op_otherwise():
    from rag.nodes.short_circuit import regenerate_gate

    state = _reflection_state(rewrite_count=0)
    result = await regenerate_gate(state)
    assert result["rewrite_count"] == 1


def test_standard_graph_wires_regenerate_gate_node():
    from rag.graph_strategies import StandardGraphStrategy

    strategy = StandardGraphStrategy()
    graph = strategy.build(
        ollama_service=MagicMock(),
        embedding_service=MagicMock(),
        qdrant_service=MagicMock(),
        lightrag_service=MagicMock(),
    )
    assert "regenerate_gate" in graph.nodes


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
