import pytest
from unittest.mock import MagicMock
import sys

def test_embedding_no_double_prefix(monkeypatch):
    """Verify that encode_single_full does not double-prefix the input query."""
    # Mock models to avoid heavy downloads
    class MockBGEM3FlagModel:
        def __init__(self, *args, **kwargs):
            pass
        def encode(self, texts, **kwargs):
            # Record the exact texts encoded
            self.encoded_texts = texts
            # Return dummy vectors
            import numpy as np
            return {
                "dense_vecs": np.zeros((len(texts), 1024)),
                "lexical_weights": [{"1": 0.5} for _ in texts]
            }

    class MockCrossEncoder:
        def __init__(self, *args, **kwargs):
            pass

    # Mock imports
    sys.modules["FlagEmbedding"] = MagicMock()
    sys.modules["FlagEmbedding"].BGEM3FlagModel = MockBGEM3FlagModel
    sys.modules["sentence_transformers"] = MagicMock()
    sys.modules["sentence_transformers"].CrossEncoder = MockCrossEncoder

    # Avoid cache hit by creating a clean service instance
    from app.config import settings
    monkeypatch.setattr(settings, "embedding_model", "BAAI/bge-m3")

    from services.embedding_service import EmbeddingService
    service = EmbeddingService()
    service._ensure_models()

    # Test encode_single_full
    query = "What is Deeksha?"
    service.encode_single_full(query)
    
    encoded_query_texts = service._encoder.encoded_texts
    expected_prefix = "Given a spiritual teaching, retrieve relevant passages: "
    
    assert len(encoded_query_texts) == 1
    assert encoded_query_texts[0] == f"{expected_prefix}{query}"
    
    # Test encode_batch directly with the same query
    service.encode_batch([query])
    encoded_batch_texts = service._encoder.encoded_texts
    
    assert len(encoded_batch_texts) == 1
    assert encoded_batch_texts[0] == f"{expected_prefix}{query}"
    
    # Assert they are identical
    assert encoded_query_texts[0] == encoded_batch_texts[0]
