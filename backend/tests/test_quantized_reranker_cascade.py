"""
Tests for Two-Stage Cascade Quantized Reranker and ColBERT Decommissioning.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from rag.nodes.reranking import _limit_rerank_candidates


def test_limit_rerank_candidates_with_quantized_reranker(monkeypatch):
    monkeypatch.setattr(settings, "rag_quantized_reranker_enabled", True)
    monkeypatch.setattr(settings, "reranker_backend", "onnx_int8")
    monkeypatch.setattr(settings, "rag_stage1_candidate_pool", 40)

    docs = [{"id": f"doc_{i}", "text": f"Text {i}"} for i in range(50)]
    capped = _limit_rerank_candidates(docs, query_tier="standard")

    # With quantized ONNX reranker, pool expands to 40 instead of previous 10
    assert len(capped) == 40
    assert capped[0]["id"] == "doc_0"
    assert capped[39]["id"] == "doc_39"


def test_limit_rerank_candidates_legacy_fallback(monkeypatch):
    monkeypatch.setattr(settings, "rag_quantized_reranker_enabled", False)
    monkeypatch.setattr(settings, "reranker_backend", "flagembedding")

    docs = [{"id": f"doc_{i}", "text": f"Text {i}"} for i in range(30)]
    capped_simple = _limit_rerank_candidates(docs, query_tier="tier2_simple")
    capped_standard = _limit_rerank_candidates(docs, query_tier="standard")

    assert len(capped_simple) == 8
    assert len(capped_standard) == 10


@pytest.mark.asyncio
async def test_cascaded_rerank_bypasses_colbert(monkeypatch):
    from services.embedding_service import EmbeddingService

    service = EmbeddingService.__new__(EmbeddingService)
    service.rerank = AsyncMock(return_value=[{"text": "result", "score": 0.9}])

    docs = [{"text": f"doc {i}"} for i in range(15)]
    res = await service.cascaded_rerank("test query", docs, cross_top_k=5)

    assert len(res) == 1
    # Confirms rerank() was called directly without invoking ColBERT
    service.rerank.assert_called_once_with("test query", docs, top_k=5, min_score=None)


def test_reranker_service_loads_onnx_directly(monkeypatch):
    from services.reranker_service import RerankerService

    monkeypatch.setattr(settings, "reranker_backend", "onnx_int8")
    monkeypatch.setattr(settings, "use_flashrank", True)

    service = RerankerService()
    mock_load_fallback = MagicMock()
    service._load_fallback = mock_load_fallback

    service._ensure_model()
    # Confirms _load_fallback was invoked directly without needing flashrank
    mock_load_fallback.assert_called_once()
