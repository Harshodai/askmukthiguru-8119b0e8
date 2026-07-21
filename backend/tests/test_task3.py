"""Tests for Task 3: LITM reordering and true BM25 sparse retrieval."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.nodes as nodes
from rag.nodes import reranking as reranking_module
from rag.nodes import retrieval as retrieval_module
from rag.states import GraphState


class _MockEmbeddingService:
    def encode_single_full(self, text):
        return {"dense": [0.1] * 384, "sparse": {"1": 0.5}}

    def encode_batch(self, texts):
        return {
            "dense": [[0.1] * 384 for _ in texts],
            "sparse": [{"1": 0.5} for _ in texts],
        }

    def cascaded_rerank(self, question, docs, colbert_top_k, cross_top_k, min_score):
        return docs


@pytest.fixture
def mock_retrieval_services(monkeypatch):
    mock_ollama = AsyncMock()
    mock_ollama._generate_fast = AsyncMock(return_value="what is meditation")
    mock_embedder = _MockEmbeddingService()
    mock_qdrant = MagicMock()
    mock_lightrag = MagicMock()
    monkeypatch.setattr(nodes, "_ollama", mock_ollama)
    monkeypatch.setattr(nodes, "_embedder", mock_embedder)
    monkeypatch.setattr(nodes, "_qdrant", mock_qdrant)
    monkeypatch.setattr(nodes, "_lightrag", mock_lightrag)
    return mock_ollama, mock_embedder, mock_qdrant, mock_lightrag


@pytest.fixture
def mock_rerank_services(monkeypatch):
    monkeypatch.setattr(reranking_module._services, "_ollama", AsyncMock())
    monkeypatch.setattr(reranking_module._services, "_embedder", _MockEmbeddingService())
    monkeypatch.setattr(reranking_module._services, "_qdrant", SimpleNamespace())
    fake_settings = SimpleNamespace(
        use_flashrank=False,
        rerank_min_score=0.0,
        rerank_threshold_complex=0.0,
        rerank_threshold_simple=0.0,
        rag_top_k_rerank=10,
        rag_top_k_retrieval=10,
        rerank_score_delta_enabled=False,
        important_kwd_boost_enabled=False,
        crag_skip_confidence=0.0,
        crag_score_delta_ratio=0.0,
        rag_context_compression_enabled=False,
    )
    monkeypatch.setattr(reranking_module, "settings", fake_settings)


def _make_rerank_state(docs: list[dict]) -> GraphState:
    return {
        "question": "test question",
        "rewritten_query": None,
        "reranked_docs": docs,
        "documents": docs,
        "chat_history": [],
        "intent": "FACTUAL",
        "query_tier": "standard",
        "relevant_docs": [],
        "grading_reasons": [],
        "rewrite_count": 0,
        "sub_queries": [],
        "is_complex": False,
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
        "meditation_step": 0,
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
async def test_litm_reordering_places_top_two_at_edges(mock_rerank_services):
    """For K>=6, top-2 reranked docs must be placed at positions 0 and K-1."""
    docs = [{"text": f"doc {i}", "rerank_score": 1.0 - i * 0.1} for i in range(8)]
    state = _make_rerank_state(docs)

    result = await reranking_module.rerank_documents(state, config=None)
    reranked = result["reranked_docs"]

    assert len(reranked) == 8
    assert reranked[0]["text"] == "doc 0"
    assert reranked[-1]["text"] == "doc 1"


@pytest.mark.asyncio
async def test_litm_reordering_noop_for_small_k(mock_rerank_services):
    """For K<6, LITM must not alter the already-sorted order."""
    docs = [{"text": f"doc {i}", "rerank_score": 1.0 - i * 0.1} for i in range(5)]
    state = _make_rerank_state(docs)

    result = await reranking_module.rerank_documents(state, config=None)
    reranked = result["reranked_docs"]

    assert [d["text"] for d in reranked] == ["doc 0", "doc 1", "doc 2", "doc 3", "doc 4"]


@pytest.mark.asyncio
async def test_retrieval_bm25_uses_native_sparse_vector(mock_retrieval_services, monkeypatch):
    """BM25 path must call Qdrant with a sparse vector instead of word-overlap scoring."""
    from app.config import settings

    monkeypatch.setattr(settings, "bm25_retrieval_enabled", True)
    monkeypatch.setattr(settings, "bm25_result_limit", 5)
    monkeypatch.setattr(settings, "rag_skip_retrieval_expansions", True)
    monkeypatch.setattr(settings, "rag_okf_injection_enabled", False)
    monkeypatch.setattr(settings, "retrieval_score_delta_enabled", False)
    monkeypatch.setattr(settings, "retrieval_deduplication_enabled", False)
    monkeypatch.setattr(settings, "rag_context_compression_enabled", False)
    monkeypatch.setattr(settings, "knowledge_graph_query_enabled", False)
    monkeypatch.setattr(settings, "graphrag_fusion_enabled", False)
    monkeypatch.setattr(settings, "rag_top_k_retrieval", 20)
    monkeypatch.setattr(settings, "rag_top_k_retrieval_after_cutoff", 20)
    monkeypatch.setattr(settings, "rag_mmr_lambda", 0.5)
    monkeypatch.setattr(settings, "web_search_coverage_threshold", 0.0)

    _, mock_embedder, mock_qdrant, _ = mock_retrieval_services

    def fake_search(*args, **kwargs):
        return [{"text": "hybrid result", "score": 0.9}]

    def fake_scroll_content(query, limit, filter_cond=None):
        return []

    captured = {}

    def fake_bm25_sparse_search(query, embedder, qdrant, limit):
        captured["query"] = query
        captured["limit"] = limit
        return [{"text": "bm25 sparse result", "score": 0.7, "source": "bm25"}]

    monkeypatch.setattr(mock_qdrant, "search", fake_search)
    monkeypatch.setattr(mock_qdrant, "scroll_content", fake_scroll_content)
    monkeypatch.setattr(retrieval_module, "_bm25_sparse_search", fake_bm25_sparse_search)

    state = {
        "question": "meditation practice",
        "chat_history": [],
        "rewritten_query": None,
        "sub_queries": ["meditation practice"],
        "selected_clusters": [],
        "hyde_text": None,
        "intent": "FACTUAL",
        "knowledge_tags": [],
    }
    result = await retrieval_module.retrieve_documents(state, config=None)

    assert captured.get("query") == "meditation practice"
    assert captured.get("limit") == 5
    assert any(doc.get("source") == "bm25" for doc in result["documents"])


def test_bm25_sparse_search_uses_qdrant_sparse_query():
    """_bm25_sparse_search should encode the query and query Qdrant sparse vector."""
    from rag.nodes.retrieval import _bm25_sparse_search
    from unittest.mock import MagicMock

    mock_embedder = MagicMock()
    mock_embedder.encode_single_full.return_value = {"dense": [0.1] * 384, "sparse": {"1": 0.5}}

    mock_qdrant = MagicMock()
    mock_qdrant.search.return_value = [
        {"text": "sparse hit", "score": 0.85, "source_url": "url1"}
    ]

    results = _bm25_sparse_search("meditation", mock_embedder, mock_qdrant, limit=3)

    mock_embedder.encode_single_full.assert_called_once_with("meditation")
    mock_qdrant.search.assert_called_once()
    call_kwargs = mock_qdrant.search.call_args.kwargs
    assert call_kwargs["sparse_vector"] == {"1": 0.5}
    assert call_kwargs.get("raptor_level") == 0
    assert len(results) == 1
    assert results[0]["text"] == "sparse hit"
    assert results[0].get("source") == "bm25_sparse"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
