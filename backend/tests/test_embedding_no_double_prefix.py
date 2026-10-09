import sys
from unittest.mock import MagicMock


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
                "lexical_weights": [{"1": 0.5} for _ in texts],
            }

    class MockCrossEncoder:
        def __init__(self, *args, **kwargs):
            pass

    # Mock imports
    # monkeypatch.setitem restores sys.modules after the test; a bare
    # assignment replaced the real sentence_transformers for the whole run.
    flag_mod = MagicMock()
    flag_mod.BGEM3FlagModel = MockBGEM3FlagModel
    st_mod = MagicMock()
    st_mod.CrossEncoder = MockCrossEncoder
    monkeypatch.setitem(sys.modules, "FlagEmbedding", flag_mod)
    monkeypatch.setitem(sys.modules, "sentence_transformers", st_mod)

    # Avoid cache hit by creating a clean service instance
    from app.config import settings

    monkeypatch.setattr(settings, "embedding_model", "BAAI/bge-m3")
    monkeypatch.setattr(settings, "embedding_backend", "flagembedding")

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
