"""P0-3: _okf_match must reuse the shared pipeline embedder, not instantiate EmbeddingService per call."""
from unittest.mock import MagicMock, patch

import rag.nodes.retrieval as retrieval_mod


def _seed_okf(monkeypatch):
    monkeypatch.setattr(retrieval_mod, "_OKF_CACHE", [
        {"title": "karma", "body": "law of cause and effect", "embedding": [1.0] + [0.0] * 1023},
    ])


def test_okf_match_reuses_shared_embedder(monkeypatch):
    """Calling _okf_match twice must NOT instantiate EmbeddingService either time."""
    _seed_okf(monkeypatch)

    shared = MagicMock()
    shared.encode.return_value = [[0.5] * 1024]
    monkeypatch.setattr(retrieval_mod._services, "_embedder", shared)

    with patch(
        "services.embedding_service.EmbeddingService"
    ) as MockEmbeddingService:
        # If _okf_match falls back to EmbeddingService(), this constructor would be called.
        MockEmbeddingService.return_value = MagicMock(encode=MagicMock(return_value=[[0.5] * 1024]))
        retrieval_mod._okf_match("what is karma", limit=1)
        retrieval_mod._okf_match("what is dharma", limit=1)
        assert MockEmbeddingService.call_count == 0, (
            "EmbeddingService was instantiated — shared embedder not reused"
        )

    assert shared.encode.call_count == 2


def test_okf_match_uses_same_embedder_identity(monkeypatch):
    """The embedder used by _okf_match must be the exact object on _services._embedder."""
    _seed_okf(monkeypatch)

    shared = MagicMock()
    shared.encode.return_value = [[0.5] * 1024]
    monkeypatch.setattr(retrieval_mod._services, "_embedder", shared)

    retrieval_mod._okf_match("karma", limit=1)
    assert shared.encode.called


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
