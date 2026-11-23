"""Tests for hybrid search independent channel observability and score retention."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from services.qdrant.searcher import QdrantSearcher


def test_hybrid_channel_observability_fields():
    """Verify that fused_score, dense_score, sparse_score, and hybrid_channel are retained."""
    hit = MagicMock()
    hit.score = 0.825
    hit.dense_score = 0.88
    hit.sparse_score = 0.76
    hit.dense_rank = 1
    hit.sparse_rank = 3
    hit.payload = {
        "text": "Living in the present dissolves suffering.",
        "source_url": "https://youtube.com/watch?v=test",
        "title": "Present Moment",
        "provenance": "verbatim_speech",
    }

    client = MagicMock()
    client.query_points.return_value = MagicMock(points=[hit])
    searcher = QdrantSearcher(client, "test_collection")

    with patch("services.qdrant.source_policy.filter_by_release", return_value=([hit], 1)):
        # 1. Hybrid search with sparse vector
        results = searcher.search(
            query_vector=[0.1] * 8,
            sparse_vector={1: 0.5, 2: 0.5},
            limit=5,
        )

        assert len(results) == 1
        doc = results[0]
        assert doc["score"] == 0.825
        assert doc["fused_score"] == 0.825
        assert doc["dense_score"] == 0.88
        assert doc["sparse_score"] == 0.76
        assert doc["dense_rank"] == 1
        assert doc["sparse_rank"] == 3
        assert doc["hybrid_channel"] == "hybrid_fused"

        # 2. Dense-only search without sparse vector
        results_dense = searcher.search(
            query_vector=[0.1] * 8,
            sparse_vector=None,
            limit=5,
        )
        assert len(results_dense) == 1
        assert results_dense[0]["hybrid_channel"] == "dense_only"


def test_empty_sparse_vector_degrades_to_dense():
    """Verify that an empty sparse vector degrades gracefully to dense without raising."""
    hit = MagicMock()
    hit.score = 0.75
    hit.payload = {"text": "Calmness in action."}

    client = MagicMock()
    client.query_points.return_value = MagicMock(points=[hit])
    searcher = QdrantSearcher(client, "test_collection")

    with patch("services.qdrant.source_policy.filter_by_release", return_value=([hit], 1)):
        # Empty dictionary or empty indices/values
        results = searcher.search(
            query_vector=[0.1] * 8,
            sparse_vector={},
            limit=5,
        )
        assert len(results) == 1
        assert results[0]["hybrid_channel"] == "dense_only"
