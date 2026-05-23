import os
from unittest.mock import MagicMock, patch


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

    # Mock the imports of FlagEmbedding and sentence_transformers
    import sys

    sys.modules["FlagEmbedding"] = MagicMock()
    sys.modules["FlagEmbedding"].BGEM3FlagModel = MockBGEM3FlagModel
    sys.modules["sentence_transformers"] = MagicMock()
    sys.modules["sentence_transformers"].CrossEncoder = MockCrossEncoder

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
