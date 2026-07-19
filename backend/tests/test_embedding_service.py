import os
from unittest.mock import MagicMock, patch

import pytest


def test_transformers_no_advisory_warnings_set():
    """Verify that TRANSFORMERS_NO_ADVISORY_WARNINGS environment variable is successfully set to true."""
    assert os.environ.get("TRANSFORMERS_NO_ADVISORY_WARNINGS") == "true"


def test_embedding_service_ragatouille_optional_graceful_fallback(monkeypatch):
    """Verify that if ragatouille is not installed, it falls back gracefully with an info log instead of crashing."""
    # Import the EmbeddingService
    from services.embedding_service import EmbeddingService

    # We patch FlagEmbedding and sentence_transformers to avoid loading heavy weights locally
    MagicMock()
    MagicMock()

    # Simulate FlagEmbedding BGEM3FlagModel and sentence_transformers CrossEncoder
    class MockBGEM3FlagModel:
        def __init__(self, *args, **kwargs):
            pass

    class MockCrossEncoder:
        def __init__(self, *args, **kwargs):
            pass

    # Mock the imports of FlagEmbedding and sentence_transformers.
    # monkeypatch.setitem (not a raw sys.modules[...] = ...) so these revert
    # after the test — a bare assignment here previously left a broken
    # FlagEmbedding.BGEM3FlagModel mock (no .encode()) in sys.modules for the
    # rest of the test session, breaking any later test whose EmbeddingService
    # actually loads a real encoder.
    import sys

    fake_flag_embedding = MagicMock()
    fake_flag_embedding.BGEM3FlagModel = MockBGEM3FlagModel
    monkeypatch.setitem(sys.modules, "FlagEmbedding", fake_flag_embedding)

    fake_sentence_transformers = MagicMock()
    fake_sentence_transformers.CrossEncoder = MockCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_sentence_transformers)

    # Mock importing ragatouille to raise an ImportError (as if not installed)
    original_import = __import__

    def import_mock(name, *args, **kwargs):
        if name == "ragatouille":
            raise ImportError("No module named 'ragatouille'")
        return original_import(name, *args, **kwargs)

    service = EmbeddingService()

    with patch("builtins.__import__", side_effect=import_mock):
        service._ensure_models()

    # ColBERT should be set to False (fallback path)
    assert service._colbert is False


def test_ensure_encoder_clears_cache_and_retries_on_load_failure(monkeypatch):
    """A corrupted HF cache on the primary model self-heals via clear+retry instead of falling back.

    Regression test for the 2026-07-16 production incident: bge-m3's cached
    weights were corrupted, load failed, and the service silently fell back
    to a 384-dim model against the 1024-dim Qdrant collection.
    """
    from app.config import settings
    from services.embedding_service import EmbeddingService

    service = EmbeddingService()
    calls = {"load": 0, "cleared": []}

    def fake_load_encoder(self, model_name, device):
        calls["load"] += 1
        if calls["load"] == 1:
            raise OSError("Unable to load weights from pytorch checkpoint file")
        self._encoder = MagicMock()

    monkeypatch.setattr(EmbeddingService, "_load_encoder", fake_load_encoder)
    monkeypatch.setattr(
        EmbeddingService,
        "_clear_hf_cache_for",
        lambda self, model_id: calls["cleared"].append(model_id),
    )
    monkeypatch.setattr(settings, "embedding_model", "BAAI/bge-m3")
    monkeypatch.setattr(settings, "embedding_dimension", 1024)

    service._ensure_encoder()

    assert calls["cleared"] == ["BAAI/bge-m3"]
    assert calls["load"] == 2
    assert settings.embedding_model == "BAAI/bge-m3"


def test_ensure_encoder_refuses_wrong_dimension_fallback(monkeypatch):
    """A fallback model of a different dimension than the Qdrant collection must never be silently accepted."""
    from app.config import settings
    from services.embedding_service import EmbeddingService

    service = EmbeddingService()

    def fake_load_encoder(self, model_name, device):
        if model_name == settings.embedding_model:
            raise OSError("primary model unavailable")
        self._encoder = MagicMock()  # every fallback "loads" fine, but is 384-dim

    monkeypatch.setattr(EmbeddingService, "_load_encoder", fake_load_encoder)
    monkeypatch.setattr(EmbeddingService, "_clear_hf_cache_for", lambda self, model_id: None)
    monkeypatch.setattr(settings, "embedding_model", "BAAI/bge-m3")
    monkeypatch.setattr(settings, "embedding_dimension", 1024)

    with pytest.raises(Exception):
        service._ensure_encoder()

    # Must never silently swap to a wrong-dimension model
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.embedding_dimension == 1024
