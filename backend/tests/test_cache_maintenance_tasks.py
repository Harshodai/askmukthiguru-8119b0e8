"""The semantic cache's Qdrant vectors have no TTL of their own -- this is
the scheduled sweep that bounds the collection's size for entries the
reactive cleanup in SemanticCacheAdapter.get() never sees (nobody re-queries
them). Found 2026-09-18: the collection had no cleanup path at all before this.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tasks.cache_maintenance_tasks import _prune_once


def test_deletes_stale_points_in_batches():
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True
    page1 = [MagicMock(id="a"), MagicMock(id="b")]
    mock_client.scroll.side_effect = [(page1, None)]

    with patch("qdrant_client.QdrantClient", return_value=mock_client):
        result = _prune_once()

    assert result == {"scanned": 2, "deleted": 2}
    mock_client.delete.assert_called_once()
    _, kwargs = mock_client.delete.call_args
    assert kwargs["points_selector"] == ["a", "b"]


def test_noop_when_collection_does_not_exist():
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = False

    with patch("qdrant_client.QdrantClient", return_value=mock_client):
        result = _prune_once()

    assert result == {"scanned": 0, "deleted": 0}
    mock_client.scroll.assert_not_called()


def test_noop_when_nothing_is_stale():
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = True
    mock_client.scroll.return_value = ([], None)

    with patch("qdrant_client.QdrantClient", return_value=mock_client):
        result = _prune_once()

    assert result == {"scanned": 0, "deleted": 0}
    mock_client.delete.assert_not_called()


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
