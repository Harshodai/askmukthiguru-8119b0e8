"""
Unit Tests for Adaptive Chunking Service
"""

from unittest.mock import MagicMock

import numpy as np

from services.adaptive_chunking_service import AdaptiveChunkingService


def test_score_chunks_empty():
    """
    Test that _score_chunks returns 0.0 for empty chunk list.
    """
    embedder = MagicMock()
    service = AdaptiveChunkingService(embedder)
    assert service._score_chunks([]) == 0.0


def test_score_chunks_size_compliance():
    """
    Test that size compliance influences the score as expected.
    """
    embedder = MagicMock()
    # Mock embedding encode to return simple arrays
    embedder.encode = MagicMock(return_value=[np.array([1.0, 0.0])])

    service = AdaptiveChunkingService(embedder)

    # Standard chunk sizes within [200, 1200] should score higher than tiny/huge chunks
    chunks_ideal = ["a" * 800, "b" * 600, "c" * 1000]
    score_ideal = service._score_chunks(chunks_ideal)

    chunks_bad = ["a" * 10, "b" * 5000]
    score_bad = service._score_chunks(chunks_bad)

    assert score_ideal > score_bad


def test_intrachunk_cohesion():
    """
    Test intrachunk cohesion scoring using mocked embeddings.
    """
    embedder = MagicMock()

    # We mock encode to return deterministic unit vectors
    def mock_encode(texts):
        # Return mock embeddings where adjacent sentences have high cosine similarity (almost same vector)
        # and non-adjacent have lower similarity.
        embeddings = []
        for text in texts:
            if "spiritual" in text:
                embeddings.append(np.array([1.0, 0.0]))
            else:
                embeddings.append(np.array([0.0, 1.0]))
        return embeddings

    embedder.encode = mock_encode

    service = AdaptiveChunkingService(embedder)

    # 1. High cohesion chunk (sentences are very similar, e.g. all contain "spiritual")
    high_cohesion_chunk = "This is a spiritual teaching. We discuss spiritual freedom. Meditation is a spiritual path."

    # 2. Low cohesion chunk (sentences have different topics, some contain "spiritual", some don't)
    low_cohesion_chunk = (
        "This is a spiritual teaching. I bought a red apple. The server runs on port 8000."
    )

    score_high = service._score_chunks([high_cohesion_chunk])
    score_low = service._score_chunks([low_cohesion_chunk])

    assert score_high >= score_low


def test_chunk_document_routing():
    """
    Test that chunk_document correctly selects the highest scoring chunking candidate.
    """
    embedder = MagicMock()
    service = AdaptiveChunkingService(embedder)

    doc_text = (
        "This is a long spiritual document about self-realization and freedom from suffering."
    )

    # Mock split methods to return predictable lists
    service._split_recursively = MagicMock(return_value=["Chunk 1", "Chunk 2", "Chunk 3"])
    service._split_semantically = MagicMock(
        return_value=["Huge chunk that takes up almost the whole text", "tiny"]
    )

    # Mock _score_chunks to favor recursive candidate
    def mock_score(chunks):
        if "Chunk 1" in chunks:
            return 0.95
        return 0.20

    service._score_chunks = MagicMock(side_effect=mock_score)

    chosen_chunks = service.chunk_document(doc_text)

    # Recursive splitter should have been chosen because score is 0.95 vs 0.20
    assert len(chosen_chunks) == 3
    assert chosen_chunks == ["Chunk 1", "Chunk 2", "Chunk 3"]
