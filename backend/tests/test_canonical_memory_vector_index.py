"""Tests for canonical memory vector index — Phase 7 of Adaptive Memory System.

Unit tests using mocked Qdrant and Supabase clients.  Verifies:
- collection creation with correct schema
- upsert writes correct payload
- search enforces user_id filter server-side
- delete is scoped to user_id
- delete_all_user removes all user points
- rebuild_from_canonical pulls from Postgres and upserts vectors
- detect_orphans finds vectors without Postgres rows
- repair deletes orphans and adds missing vectors
- health_check reports collection status

Run: cd backend && .venv/bin/pytest tests/test_canonical_memory_vector_index.py -v
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.models import Distance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _make_point(point_id: str | None = None, user_id: str = "", **extra: Any) -> MagicMock:
    """Create a mock Qdrant PointStruct-like object."""
    p = MagicMock()
    p.id = point_id or _uid()
    p.score = extra.pop("score", 0.9)
    p.payload = {
        "user_id": user_id,
        "memory_type": extra.pop("memory_type", "PREFERENCE"),
        "status": extra.pop("status", "active"),
        "memory_id": extra.pop("memory_id", p.id),
    }
    p.vector = extra.pop("vector", [0.1] * 1024)
    return p


def _make_collection_info(points_count: int = 0) -> MagicMock:
    """Create a mock Qdrant collection info object."""
    info = MagicMock()
    info.points_count = points_count
    info.config.params.vectors.size = 1024
    info.config.params.vectors.distance = "Cosine"
    return info


def _make_pg_memory(user_id: str, memory_id: str | None = None, **overrides: Any) -> dict[str, Any]:
    """Create a realistic canonical_memories row dict."""
    mid = memory_id or _uid()
    row = {
        "id": mid,
        "user_id": user_id,
        "memory_type": "PREFERENCE",
        "statement": "User prefers concise answers",
        "status": "active",
        "confidence": 0.85,
        "importance": 0.6,
        "sensitivity": "normal",
        "version": 1,
    }
    row.update(overrides)
    return row


_UNSET = object()


def _build_index(
    qdrant_client: Any | None = _UNSET,
    supabase_client: Any | None = _UNSET,
) -> Any:
    """Build a CanonicalMemoryVectorIndex with injected clients.

    A sentinel default (not None) so callers can pass an explicit None to build
    an index WITHOUT that client. `x or MagicMock()` swallowed the None and
    handed back a mock, so rebuild_from_canonical's "supabase_client required"
    guard could never be reached from a test.
    """
    from services.canonical_memory.vector_index import CanonicalMemoryVectorIndex

    qc = MagicMock() if qdrant_client is _UNSET else qdrant_client
    sc = MagicMock() if supabase_client is _UNSET else supabase_client
    return CanonicalMemoryVectorIndex(
        qdrant_client=qc,
        supabase_client=sc,
    )


# ---------------------------------------------------------------------------
# Mock scroll result
# ---------------------------------------------------------------------------

class _ScrollResult(tuple):
    """Mimics Qdrant's (points, next_offset) tuple from scroll().

    Subclasses tuple so `vector_results[0]` works: qdrant-client returns a real
    tuple and the production code indexes it. The previous plain class exposed
    only .points/.next_offset and raised
    "'_ScrollResult' object is not subscriptable" against correct code.
    """

    def __new__(cls, points: list[MagicMock]):
        return super().__new__(cls, (points, None))

    @property
    def points(self) -> list[MagicMock]:
        return self[0]

    @property
    def next_offset(self):
        return self[1]


# ---------------------------------------------------------------------------
# Tests: ensure_collection
# ---------------------------------------------------------------------------

class TestEnsureCollection:
    def test_creates_collection_with_correct_params(self) -> None:
        qc = MagicMock()
        qc.get_collections.return_value.collections = []
        idx = _build_index(qdrant_client=qc)

        idx.ensure_collection()

        qc.create_collection.assert_called_once()
        call_kwargs = qc.create_collection.call_args
        assert call_kwargs.kwargs["collection_name"] == "canonical_memory_vectors"
        assert call_kwargs.kwargs["vectors_config"].size == 1024
        assert call_kwargs.kwargs["vectors_config"].distance == Distance.COSINE

    def test_skips_creation_when_collection_exists(self) -> None:
        qc = MagicMock()
        mock_col = MagicMock()
        mock_col.name = "canonical_memory_vectors"
        qc.get_collections.return_value.collections = [mock_col]
        idx = _build_index(qdrant_client=qc)

        idx.ensure_collection()

        qc.create_collection.assert_not_called()

    def test_creates_three_payload_indexes(self) -> None:
        qc = MagicMock()
        qc.get_collections.return_value.collections = []
        idx = _build_index(qdrant_client=qc)

        idx.ensure_collection()

        assert qc.create_payload_index.call_count == 3
        field_names = [
            call.kwargs["field_name"]
            for call in qc.create_payload_index.call_args_list
        ]
        assert "user_id" in field_names
        assert "memory_type" in field_names
        assert "status" in field_names

    def test_ignores_already_exists_error(self) -> None:
        qc = MagicMock()
        qc.get_collections.return_value.collections = []
        qc.create_collection.side_effect = Exception("already exists")
        idx = _build_index(qdrant_client=qc)

        # Should not raise
        idx.ensure_collection()

    def test_raises_on_unexpected_error(self) -> None:
        qc = MagicMock()
        qc.get_collections.return_value.collections = []
        qc.create_collection.side_effect = Exception("network error")
        idx = _build_index(qdrant_client=qc)

        with pytest.raises(Exception, match="network error"):
            idx.ensure_collection()


# ---------------------------------------------------------------------------
# Tests: upsert
# ---------------------------------------------------------------------------

class TestUpsert:
    def test_upsert_calls_client_with_correct_point(self) -> None:
        qc = MagicMock()
        idx = _build_index(qdrant_client=qc)
        user_id = _uid()
        memory_id = _uid()
        vector = [0.1] * 1024

        import asyncio
        asyncio.run(idx.upsert(user_id, memory_id, vector, "PREFERENCE", "active"))

        qc.upsert.assert_called_once()
        point = qc.upsert.call_args.kwargs["points"][0]
        assert point.id == memory_id
        assert point.payload["user_id"] == user_id
        assert point.payload["memory_type"] == "PREFERENCE"
        assert point.payload["status"] == "active"

    def test_upsert_with_custom_status(self) -> None:
        qc = MagicMock()
        idx = _build_index(qdrant_client=qc)
        user_id = _uid()
        memory_id = _uid()

        import asyncio
        asyncio.run(idx.upsert(user_id, memory_id, [0.2] * 1024, "PROFILE", "superseded"))

        point = qc.upsert.call_args.kwargs["points"][0]
        assert point.payload["status"] == "superseded"


# ---------------------------------------------------------------------------
# Tests: search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_applies_user_id_filter(self) -> None:
        qc = MagicMock()
        qc.query_points.return_value.points = []
        idx = _build_index(qdrant_client=qc)
        user_id = _uid()

        import asyncio
        asyncio.run(idx.search(user_id, [0.3] * 1024, limit=5))

        call_kwargs = qc.query_points.call_args.kwargs
        search_filter = call_kwargs["query_filter"]
        assert len(search_filter.must) == 1
        assert search_filter.must[0].key == "user_id"

    def test_search_with_memory_type_filter(self) -> None:
        qc = MagicMock()
        qc.query_points.return_value.points = []
        idx = _build_index(qdrant_client=qc)

        import asyncio
        asyncio.run(idx.search(_uid(), [0.3] * 1024, limit=5, memory_type="GOAL"))

        call_kwargs = qc.query_points.call_args.kwargs
        search_filter = call_kwargs["query_filter"]
        assert len(search_filter.must) == 2
        keys = {f.key for f in search_filter.must}
        assert "memory_type" in keys

    def test_search_returns_parsed_results(self) -> None:
        qc = MagicMock()
        point = _make_point(user_id="u1", score=0.92, memory_type="INTEREST")
        qc.query_points.return_value.points = [point]
        idx = _build_index(qdrant_client=qc)

        import asyncio
        results = asyncio.run(idx.search("u1", [0.3] * 1024, limit=5))

        assert len(results) == 1
        assert results[0]["score"] == 0.92
        assert results[0]["memory_type"] == "INTEREST"
        assert results[0]["id"] == point.id

    def test_search_empty_results(self) -> None:
        qc = MagicMock()
        qc.query_points.return_value.points = []
        idx = _build_index(qdrant_client=qc)

        import asyncio
        results = asyncio.run(idx.search(_uid(), [0.3] * 1024, limit=10))

        assert results == []


# ---------------------------------------------------------------------------
# Tests: delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_scoped_to_user(self) -> None:
        qc = MagicMock()
        idx = _build_index(qdrant_client=qc)
        user_id = _uid()
        memory_id = _uid()

        import asyncio
        asyncio.run(idx.delete(user_id, memory_id))

        qc.delete.assert_called_once()
        delete_filter = qc.delete.call_args.kwargs["points_selector"]
        assert len(delete_filter.must) == 2
        user_condition = delete_filter.must[0]
        id_condition = delete_filter.must[1]
        assert user_condition.key == "user_id"
        assert id_condition.has_id == [memory_id]


# ---------------------------------------------------------------------------
# Tests: delete_all_user
# ---------------------------------------------------------------------------

class TestDeleteAllUser:
    def test_delete_all_user_scoped_and_returns_count(self) -> None:
        qc = MagicMock()
        qc.count.return_value.count = 5
        idx = _build_index(qdrant_client=qc)
        user_id = _uid()

        import asyncio
        deleted = asyncio.run(idx.delete_all_user(user_id))

        assert deleted == 5
        qc.delete.assert_called_once()
        delete_filter = qc.delete.call_args.kwargs["points_selector"]
        assert len(delete_filter.must) == 1
        assert delete_filter.must[0].key == "user_id"

    def test_delete_all_user_zero_count(self) -> None:
        qc = MagicMock()
        qc.count.return_value.count = 0
        idx = _build_index(qdrant_client=qc)

        import asyncio
        deleted = asyncio.run(idx.delete_all_user(_uid()))

        assert deleted == 0


# ---------------------------------------------------------------------------
# Tests: rebuild_from_canonical
# ---------------------------------------------------------------------------

class TestRebuildFromCanonical:
    def test_rebuild_embeds_and_upserts(self) -> None:
        user_id = _uid()
        mem = _make_pg_memory(user_id)
        sc = MagicMock()
        sc.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            mem
        ]
        qc = MagicMock()
        idx = _build_index(qdrant_client=qc, supabase_client=sc)

        async def embed_fn(text: str) -> list[float]:
            return [0.5] * 1024

        import asyncio
        count = asyncio.run(idx.rebuild_from_canonical(user_id, embed_fn))

        assert count == 1
        qc.upsert.assert_called_once()
        point = qc.upsert.call_args.kwargs["points"][0]
        assert point.id == mem["id"]
        assert point.payload["user_id"] == user_id

    def test_rebuild_empty_user(self) -> None:
        sc = MagicMock()
        sc.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        idx = _build_index(supabase_client=sc)

        import asyncio
        count = asyncio.run(idx.rebuild_from_canonical(_uid(), lambda t: [0.0] * 1024))

        assert count == 0

    def test_rebuild_requires_supabase(self) -> None:
        idx = _build_index(supabase_client=None)

        import asyncio
        with pytest.raises(RuntimeError, match="supabase_client required"):
            asyncio.run(idx.rebuild_from_canonical(_uid(), lambda t: [0.0] * 1024))


# ---------------------------------------------------------------------------
# Tests: detect_orphans
# ---------------------------------------------------------------------------

class TestDetectOrphans:
    def test_detects_orphans(self) -> None:
        user_id = _uid()
        orphan_id = _uid()
        valid_id = _uid()

        # Vector has orphan_id and valid_id
        orphan_point = _make_point(point_id=orphan_id, user_id=user_id, memory_id=orphan_id)
        valid_point = _make_point(point_id=valid_id, user_id=user_id, memory_id=valid_id)
        qc = MagicMock()
        qc.scroll.return_value = _ScrollResult([orphan_point, valid_point])

        # Postgres only has valid_id
        sc = MagicMock()
        sc.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": valid_id}
        ]
        idx = _build_index(qdrant_client=qc, supabase_client=sc)

        import asyncio
        orphans = asyncio.run(idx.detect_orphans(user_id))

        assert orphan_id in orphans
        assert valid_id not in orphans

    def test_no_orphans(self) -> None:
        user_id = _uid()
        mem_id = _uid()
        point = _make_point(point_id=mem_id, user_id=user_id, memory_id=mem_id)
        qc = MagicMock()
        qc.scroll.return_value = _ScrollResult([point])

        sc = MagicMock()
        sc.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": mem_id}
        ]
        idx = _build_index(qdrant_client=qc, supabase_client=sc)

        import asyncio
        orphans = asyncio.run(idx.detect_orphans(user_id))

        assert orphans == []

    def test_empty_vectors_no_orphans(self) -> None:
        qc = MagicMock()
        qc.scroll.return_value = _ScrollResult([])
        idx = _build_index(qdrant_client=qc)

        import asyncio
        orphans = asyncio.run(idx.detect_orphans(_uid()))

        assert orphans == []


# ---------------------------------------------------------------------------
# Tests: repair
# ---------------------------------------------------------------------------

class TestRepair:
    def test_repair_deletes_orphans_and_adds_missing(self) -> None:
        user_id = _uid()
        orphan_id = _uid()
        existing_id = _uid()
        missing_id = _uid()

        # Vectors: orphan_id (orphan) + existing_id (valid)
        orphan_point = _make_point(point_id=orphan_id, user_id=user_id, memory_id=orphan_id)
        existing_point = _make_point(point_id=existing_id, user_id=user_id, memory_id=existing_id)
        qc = MagicMock()
        # scroll called twice: once for orphans, once for missing
        qc.scroll.side_effect = [
            _ScrollResult([orphan_point, existing_point]),
            _ScrollResult([existing_point]),
        ]

        # Postgres: existing_id + missing_id (missing from vectors)
        sc = MagicMock()
        sc.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": orphan_id},  # orphan
            {"id": existing_id},  # already has vector
        ]
        # For phase 2 (missing detection)
        sc.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": existing_id, "memory_type": "PROFILE", "statement": "test"},
        ]

        idx = _build_index(qdrant_client=qc, supabase_client=sc)

        async def embed_fn(text: str) -> list[float]:
            return [0.4] * 1024

        import asyncio
        result = asyncio.run(idx.repair(user_id, embed_fn))

        # Orphan was deleted
        assert result["orphans_deleted"] == 1


# ---------------------------------------------------------------------------
# Tests: health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_healthy_collection(self) -> None:
        qc = MagicMock()
        mock_col = MagicMock()
        mock_col.name = "canonical_memory_vectors"
        qc.get_collections.return_value.collections = [mock_col]
        qc.get_collection.return_value = _make_collection_info(points_count=42)
        idx = _build_index(qdrant_client=qc)

        import asyncio
        health = asyncio.run(idx.health_check())

        assert health["healthy"] is True
        assert health["exists"] is True
        assert health["points_count"] == 42
        assert health["expected_dimension"] == 1024

    def test_missing_collection(self) -> None:
        qc = MagicMock()
        qc.get_collections.return_value.collections = []
        idx = _build_index(qdrant_client=qc)

        import asyncio
        health = asyncio.run(idx.health_check())

        assert health["healthy"] is False
        assert health["exists"] is False
        assert "error" in health

    def test_dimension_mismatch(self) -> None:
        qc = MagicMock()
        mock_col = MagicMock()
        mock_col.name = "canonical_memory_vectors"
        qc.get_collections.return_value.collections = [mock_col]
        info = _make_collection_info()
        info.config.params.vectors.size = 384  # wrong
        qc.get_collection.return_value = info
        idx = _build_index(qdrant_client=qc)

        import asyncio
        health = asyncio.run(idx.health_check())

        assert health["healthy"] is False
        assert "dimension mismatch" in health["error"]


# ---------------------------------------------------------------------------
# Tests: upsert_batch
# ---------------------------------------------------------------------------

class TestUpsertBatch:
    def test_upsert_batch_calls_client(self) -> None:
        qc = MagicMock()
        idx = _build_index(qdrant_client=qc)
        points = [_make_point(user_id="u1"), _make_point(user_id="u1")]

        import asyncio
        asyncio.run(idx.upsert_batch(points))

        qc.upsert.assert_called_once()
        assert len(qc.upsert.call_args.kwargs["points"]) == 2

    def test_upsert_batch_empty(self) -> None:
        qc = MagicMock()
        idx = _build_index(qdrant_client=qc)

        import asyncio
        asyncio.run(idx.upsert_batch([]))

        qc.upsert.assert_not_called()


if __name__ == "__main__":
    # Quick self-check
    from services.canonical_memory.vector_index import CanonicalMemoryVectorIndex
    assert callable(CanonicalMemoryVectorIndex)
    print("test_canonical_memory_vector_index self-check: OK")
