"""Regression tests for QdrantClientManager._verify_collection_dimension (handoff.md P1).

2026-07-16 incident: an embedding encoder silently resolved to a different
dimension than the Qdrant collection it was created with, so every dense
search 400'd while the app looked healthy. This guards the fail-loud check
added at startup to catch that class of drift immediately.
"""
from unittest.mock import MagicMock

import pytest

from services.qdrant.client import QdrantClientManager


def _manager_with_dimension(dim: int) -> QdrantClientManager:
    manager = QdrantClientManager.__new__(QdrantClientManager)
    manager._client = MagicMock()
    manager._collection = "spiritual_wisdom"
    manager._dimension = dim
    return manager


def test_verify_collection_dimension_passes_on_match():
    manager = _manager_with_dimension(1024)
    collection_info = MagicMock()
    collection_info.config.params.vectors = {"dense": MagicMock(size=1024)}
    manager._client.get_collection.return_value = collection_info

    manager._verify_collection_dimension()  # must not raise


def test_verify_collection_dimension_raises_on_mismatch():
    """A 384-dim encoder against a 1024-dim collection must fail loud, not degrade silently."""
    manager = _manager_with_dimension(1024)
    collection_info = MagicMock()
    collection_info.config.params.vectors = {"dense": MagicMock(size=384)}
    manager._client.get_collection.return_value = collection_info

    with pytest.raises(RuntimeError, match="1024-dim"):
        manager._verify_collection_dimension()


def test_verify_collection_dimension_skips_on_unexpected_shape():
    """A returned config missing the 'dense' key (SDK/config shape surprise) must warn, not crash."""
    manager = _manager_with_dimension(1024)
    collection_info = MagicMock()
    collection_info.config.params.vectors = {}  # named-vector dict present but no "dense" entry
    manager._client.get_collection.return_value = collection_info

    manager._verify_collection_dimension()  # must not raise


def test_verify_collection_dimension_passes_on_unnamed_vector_match():
    """Unnamed single-vector collections (vectors is a bare VectorParams, not a dict) must be handled."""
    manager = _manager_with_dimension(1024)
    collection_info = MagicMock()
    collection_info.config.params.vectors = MagicMock(size=1024)
    manager._client.get_collection.return_value = collection_info

    manager._verify_collection_dimension()  # must not raise


def test_verify_collection_dimension_raises_on_unnamed_vector_mismatch():
    """An unnamed-vector collection at the wrong dimension must still fail loud."""
    manager = _manager_with_dimension(1024)
    collection_info = MagicMock()
    collection_info.config.params.vectors = MagicMock(size=384)
    manager._client.get_collection.return_value = collection_info

    with pytest.raises(RuntimeError, match="1024-dim"):
        manager._verify_collection_dimension()


def test_verify_collection_dimension_propagates_operational_error():
    """A real Qdrant transport/auth/server failure must propagate, not be swallowed as a shape surprise.

    get_collections() already succeeded earlier in init_collection() by the time
    this runs, so an error here is a genuine problem the caller's own
    try/except should see and re-raise — never silently downgrade it to a
    skipped check the way a shape surprise is.
    """
    manager = _manager_with_dimension(1024)
    manager._client.get_collection.side_effect = ConnectionError("qdrant unreachable")

    with pytest.raises(ConnectionError, match="qdrant unreachable"):
        manager._verify_collection_dimension()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
