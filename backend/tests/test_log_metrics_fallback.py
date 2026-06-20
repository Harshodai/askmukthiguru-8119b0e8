"""Regression tests for the log_metrics decorator fallback."""

from __future__ import annotations

import pytest

from rag.nodes import utils as utils_module
from rag.states import GraphState


def _make_state() -> GraphState:
    return {
        "question": "q",
        "chat_history": [],
        "meditation_step": 0,
        "intent": "FACTUAL",
        "query_tier": "tier2_simple",
        "documents": [{"text": "doc"}],
        "reranked_docs": [{"text": "reranked"}],
        "relevant_docs": [{"text": "existing"}],
        "grading_reasons": [],
        "rewrite_count": 0,
        "rewritten_query": None,
        "sub_queries": [],
        "is_complex": False,
        "sub_query": None,
        "sub_results": [],
        "selected_clusters": [],
        "hints": [],
        "answer": "existing answer",
        "citations": ["https://example.com"],
        "is_faithful": None,
        "needs_correction": False,
        "reflection_feedback": None,
        "verification": None,
        "confidence_score": None,
        "input_blocked": False,
        "output_blocked": False,
        "block_reason": None,
        "meditation_response": None,
        "final_answer": None,
        "error": None,
        "context_layers": None,
        "citation_reasoning": {},
        "metrics": {},
        "user_id": None,
        "detected_language": "en",
        "memory_context": None,
        "ab_model": "primary",
        "model_used": None,
        "model_provider": None,
        "route_decision": None,
        "low_confidence_retrieval": None,
        "needs_web_search": False,
        "web_search_results": [],
        "node_timings": {},
        "evaluation_trace": {},
        "token_budget_remaining": 0,
        "request_id": "test-req",
    }


@pytest.mark.asyncio
async def test_log_metrics_fallback_preserves_graph_state_shape():
    """A wrapped node that raises must return a full fallback shape."""

    @utils_module.log_metrics
    async def failing_node(state: GraphState, config: dict = None) -> dict:
        raise RuntimeError("boom")

    state = _make_state()
    result = await failing_node(state, config=None)

    assert result["error"] == "boom"
    assert result["fallback"] is True
    assert result["node"] == "failing_node"
    assert "node_timings" in result
    # Existing keys must be preserved.
    assert result["answer"] == "existing answer"
    assert result["citations"] == ["https://example.com"]
    assert result["relevant_docs"] == [{"text": "existing"}]
    assert result["documents"] == [{"text": "doc"}]
    # Missing safe-default keys must be present so downstream nodes can access them.
    assert "reranked_docs" in result
    assert "final_answer" in result
