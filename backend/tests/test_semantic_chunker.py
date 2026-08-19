"""Unit tests for SemanticChunker (semantic embedding-distance topic-shift chunking)."""

from unittest.mock import MagicMock

import pytest

from ingest.semantic_chunker import SemanticChunker


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    # Mock encode_batch returning 3 distinct clusters of 1024d vectors
    v1 = [1.0] + [0.0] * 1023
    v2 = [0.9] + [0.1] + [0.0] * 1022
    v3 = [0.0, 1.0] + [0.0] * 1022

    embedder.encode_batch.return_value = {
        "dense": [v1, v1, v2, v3, v3],
    }
    return embedder


def test_semantic_chunker_fallback_on_none_embedder():
    chunker = SemanticChunker(embedding_service=None)
    text = "Short text. Another sentence. Third sentence."
    chunks = chunker.split(text)
    assert isinstance(chunks, list)
    assert len(chunks) > 0


def test_semantic_chunker_topic_shift_boundary_detection(mock_embedder):
    chunker = SemanticChunker(
        embedding_service=mock_embedder,
        min_chunk_chars=10,
        max_chunk_chars=1000,
        distance_percentile_threshold=50.0,
    )

    sentences = [
        "First topic sentence one.",
        "First topic sentence two.",
        "First topic sentence three.",
        "Second completely different topic sentence four.",
        "Second completely different topic sentence five.",
    ]
    text = " ".join(sentences)
    chunks = chunker.split(text)

    assert len(chunks) >= 2
    assert "First topic" in chunks[0]
    assert "Second completely different" in chunks[-1]
