"""Backup/restore must not silently truncate long sources.

Both paths previously issued a single `scroll(limit=1000)`. Because
restore_from_backup deleted the live copy before reading the backup, that
truncation destroyed every chunk past the first page instead of merely
copying fewer of them.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.qdrant.indexer import QdrantIndexer

TOTAL_POINTS = 2500
PAGE = 1000


def _point(idx: int) -> MagicMock:
    p = MagicMock()
    p.id = idx
    p.vector = [0.0, 0.1]
    p.payload = {"source_url": "https://example.test/long", "chunk_index": idx}
    return p


def _paginating_client(total: int = TOTAL_POINTS) -> MagicMock:
    """A client whose scroll honours limit+offset, like a real Qdrant."""
    points = [_point(i) for i in range(total)]

    def scroll(**kwargs):
        limit = kwargs.get("limit", PAGE)
        offset = kwargs.get("offset") or 0
        page = points[offset : offset + limit]
        next_offset = offset + limit if offset + limit < total else None
        return page, next_offset

    client = MagicMock()
    client.scroll.side_effect = scroll
    client.get_collections.return_value.collections = []
    return client


def _indexer(client: MagicMock) -> QdrantIndexer:
    ix = QdrantIndexer.__new__(QdrantIndexer)
    ix._client = client
    ix._collection = "main"
    return ix


def test_backup_copies_every_point_past_the_first_page():
    client = _paginating_client()
    ix = _indexer(client)

    assert ix.backup_source("https://example.test/long", "backup") is True

    upserted = client.upsert.call_args.kwargs["points"]
    assert (
        len(upserted) == TOTAL_POINTS
    ), f"backup truncated to {len(upserted)} of {TOTAL_POINTS} points"


def test_restore_returns_every_point_past_the_first_page():
    client = _paginating_client()
    ix = _indexer(client)
    ix.delete_by_source = MagicMock()

    assert ix.restore_from_backup("https://example.test/long", "backup") is True

    restored = client.upsert.call_args.kwargs["points"]
    assert len(restored) == TOTAL_POINTS, (
        f"restore truncated to {len(restored)} of {TOTAL_POINTS} points — "
        "the remainder was deleted and never restored"
    )


def test_restore_does_not_delete_when_backup_is_empty():
    """An absent backup must leave the live copy alone, not erase it."""
    client = _paginating_client(total=0)
    ix = _indexer(client)
    ix.delete_by_source = MagicMock()

    assert ix.restore_from_backup("https://example.test/missing", "backup") is False
    ix.delete_by_source.assert_not_called()


def test_restore_reads_backup_before_deleting_live_copy():
    """Ordering guard: the destructive delete must follow a successful read."""
    client = _paginating_client(total=10)
    ix = _indexer(client)

    calls: list[str] = []

    def _scroll(**_kwargs):
        calls.append("scroll")
        return [_point(0)], None

    client.scroll.side_effect = _scroll
    ix.delete_by_source = MagicMock(side_effect=lambda *_: calls.append("delete"))

    ix.restore_from_backup("https://example.test/x", "backup")

    assert calls.index("scroll") < calls.index("delete")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
