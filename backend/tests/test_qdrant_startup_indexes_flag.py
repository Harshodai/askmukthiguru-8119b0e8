"""A read-only Qdrant serving token must not trigger the startup payload-index write."""

from unittest.mock import MagicMock

import pytest

from services.qdrant import client as qdrant_client_module
from services.qdrant.client import QdrantClientManager


def _manager_with_existing_collection() -> QdrantClientManager:
    manager = QdrantClientManager.__new__(QdrantClientManager)
    manager._client = MagicMock()
    manager._collection = "spiritual_wisdom"
    manager._dimension = 1024
    existing = MagicMock()
    existing.name = "spiritual_wisdom"
    manager._client.get_collections.return_value.collections = [existing]
    manager._verify_collection_dimension = MagicMock()
    manager._ensure_existing_collection_indexes = MagicMock()
    return manager


@pytest.mark.parametrize("flag, expected_calls", [(True, 1), (False, 0)])
def test_index_ensure_follows_flag(monkeypatch, flag, expected_calls):
    monkeypatch.setattr(qdrant_client_module.settings, "qdrant_ensure_indexes_on_startup", flag)
    manager = _manager_with_existing_collection()

    manager.init_collection()

    manager._verify_collection_dimension.assert_called_once()  # dimension check always runs
    assert manager._ensure_existing_collection_indexes.call_count == expected_calls
