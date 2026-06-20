"""Regression tests for reranking fail-safes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rag.nodes import reranking as reranking_module
from rag.states import GraphState


def _make_state(web_count: int = 5, db_count: int = 2) -> GraphState:
    web_docs = [
        {
            "text": f"web doc {i}",
            "content_type": "web_search",
            "source_url": f"https://example.com/{i}",
        }
        for i in range(web_count)
    ]
    db_docs = [
        {
            "text": f"db doc {i}",
            "content_type": "transcript",
            "source_url": f"https://source.com/{i}",
        }
        for i in range(db_count)
    ]
    return {
        "question": "test question",
        "chat_history": [],
        "meditation_step": 0,
        "intent": "FACTUAL",
        "query_tier": "standard",
        "reranked_docs": web_docs + db_docs,
        "documents": web_docs + db_docs,
        "relevant_docs": [],
        "grading_reasons": [],
        "rewrite_count": 0,
        "rewritten_query": None,
        "sub_queries": [],
        "is_complex": False,
        "sub_query": None,
        "sub_results": [],
        "selected_clusters": [],
        "hints": [],
        "answer": None,
        "citations": [],
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


@pytest.fixture
def mock_services(monkeypatch):
    mock_ollama = AsyncMock()
    mock_embedder = SimpleNamespace(_reranker=None)
    mock_qdrant = SimpleNamespace()
    monkeypatch.setattr(reranking_module._services, "_ollama", mock_ollama)
    monkeypatch.setattr(reranking_module._services, "_embedder", mock_embedder)
    monkeypatch.setattr(reranking_module._services, "_qdrant", mock_qdrant)
    return mock_ollama, mock_embedder, mock_qdrant


@pytest.mark.asyncio
async def test_grade_documents_web_grading_failure_keeps_top_three(
    mock_services, monkeypatch
):
    """If web-doc grading raises, only the top-3 reranked web docs are kept."""
    mock_ollama, _, _ = mock_services

    fake_settings = SimpleNamespace(
        rerank_min_score=0.2,
        rerank_floor=0.1,
    )
    monkeypatch.setattr(reranking_module, "settings", fake_settings)

    web_docs = [
        {
            "text": f"web doc {i}",
            "content_type": "web_search",
            "source_url": f"https://example.com/{i}",
        }
        for i in range(5)
    ]
    db_docs = [
        {
            "text": f"db doc {i}",
            "content_type": "transcript",
            "source_url": f"https://source.com/{i}",
        }
        for i in range(2)
    ]

    state = _make_state()
    state["reranked_docs"] = web_docs + db_docs
    state["documents"] = web_docs + db_docs

    # Web grading raises; DB grading marks both DB docs irrelevant.
    mock_ollama.grade_relevance.side_effect = [
        Exception("ollama web grading exploded"),
        [{"relevant": False, "reason": "irrelevant"} for _ in db_docs],
    ]

    result = await reranking_module.grade_documents(state, config=None)

    relevant = result["relevant_docs"]
    assert len(relevant) == 3
    assert all(doc.get("content_type") == "web_search" for doc in relevant)
    assert [doc["text"] for doc in relevant] == [
        "web doc 0",
        "web doc 1",
        "web doc 2",
    ]
