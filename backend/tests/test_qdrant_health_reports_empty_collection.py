"""An empty or missing collection must not report healthy.

init_collection() creates the configured collection when absent, so a deploy
that never ran the ingestion backfill produced a green /api/health while every
query abstained for want of documents. Reachability was being read as readiness.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.qdrant.client import QdrantClientManager

COLLECTION = "spiritual_wisdom_contextual"


def _manager(existing: list[str], points: int | None) -> QdrantClientManager:
    mgr = QdrantClientManager.__new__(QdrantClientManager)
    mgr._collection = COLLECTION

    def _collection_ref(collection_name: str) -> MagicMock:
        # `name` is consumed by the MagicMock constructor itself, so it has to
        # be assigned afterwards to become a readable attribute.
        ref = MagicMock()
        ref.name = collection_name
        return ref

    client = MagicMock()
    client.get_collections.return_value.collections = [_collection_ref(n) for n in existing]
    client.get_collection.return_value.points_count = points
    mgr._client = client
    return mgr


def test_populated_collection_is_healthy():
    assert _manager([COLLECTION], points=12345).health_check() is True


def test_empty_collection_is_not_healthy():
    assert _manager([COLLECTION], points=0).health_check() is False


def test_missing_points_count_is_not_healthy():
    assert _manager([COLLECTION], points=None).health_check() is False


def test_missing_collection_is_not_healthy():
    assert _manager(["some_other_collection"], points=999).health_check() is False


def test_unreachable_qdrant_is_not_healthy():
    mgr = QdrantClientManager.__new__(QdrantClientManager)
    mgr._collection = COLLECTION
    mgr._client = MagicMock()
    mgr._client.get_collections.side_effect = ConnectionError("refused")
    assert mgr.health_check() is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
