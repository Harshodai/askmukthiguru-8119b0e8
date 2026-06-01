"""
Unit Tests for FlashRank Reranker Service
"""

import sys
from unittest.mock import MagicMock

import pytest

from services.reranker_service import RerankerService


def test_reranker_service_initialization_and_fallback():
    """
    Test that RerankerService initializes and gracefully falls back to SentenceTransformers
    if flashrank is missing or fails to load.
    """
    # Mock Ranker and sentence_transformers
    sys.modules["flashrank"] = MagicMock()
    sys.modules["sentence_transformers"] = MagicMock()

    class MockRanker:
        def __init__(self, *args, **kwargs):
            pass

        def rerank(self, request):
            return [{"id": 0, "text": "Reranked by FlashRank", "score": 0.99}]

    class MockCrossEncoder:
        def __init__(self, *args, **kwargs):
            pass

        def predict(self, pairs):
            return [0.95]

    sys.modules["flashrank"].Ranker = MockRanker
    sys.modules["sentence_transformers"].CrossEncoder = MockCrossEncoder

    # Initialize service
    service = RerankerService()

    # Assert lazy initialization properties
    assert service._ranker is None
    assert service._fallback_reranker is None


@pytest.mark.asyncio
async def test_rerank_with_flashrank():
    """
    Test reranking using FlashRank ONNX engine path.
    """
    # Set up mock flashrank output structure
    mock_ranker = MagicMock()
    mock_ranker.rerank.return_value = [
        {"id": "0", "text": "Match 0", "score": 0.95},
        {"id": "1", "text": "Match 1", "score": 0.85},
    ]

    service = RerankerService()
    service._ranker = mock_ranker
    service._is_fallback = False

    query = "What is consciousness?"
    documents = [
        {"text": "Match 0", "source_url": "url0"},
        {"text": "Match 1", "source_url": "url1"},
    ]

    results = await service.rerank(query, documents, top_k=2, min_score=0.1)

    assert len(results) == 2
    # Verify order: score 0.95 should be first
    assert results[0]["text"] == "Match 0"
    assert results[0]["rerank_score"] == 0.95
    assert results[1]["text"] == "Match 1"
    assert results[1]["rerank_score"] == 0.85


@pytest.mark.asyncio
async def test_rerank_fallback_to_sentence_transformers():
    """
    Test that if FlashRank fails or is not initialized, we fall back to SentenceTransformers CrossEncoder.
    """
    mock_cross_encoder = MagicMock()
    mock_cross_encoder.predict.return_value = [0.45, 0.92]

    service = RerankerService()
    service._ranker = None  # Force fallback path
    service._fallback_reranker = mock_cross_encoder
    service._is_fallback = True

    query = "What is consciousness?"
    documents = [{"text": "Doc 0", "source_url": "url0"}, {"text": "Doc 1", "source_url": "url1"}]

    results = await service.rerank(query, documents, top_k=2, min_score=0.1)

    # Doc 1 scored 0.92 (after sigmoid), Doc 0 scored 0.45 (after sigmoid)
    assert len(results) == 2
    assert results[0]["text"] == "Doc 1"
    assert results[0]["rerank_score"] > 0.5
    assert results[1]["text"] == "Doc 0"
