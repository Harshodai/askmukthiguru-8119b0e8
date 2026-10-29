"""Tests for Anti-Entropy and Orphan Reconciliation (DE-1.4, DE-1.5).

Verifies:
  - diff_point_ids correctly identifies orphans, missing, and matched sets
  - reconcile_source_orphans detects extra (orphan) points and deletes them
  - dry_run safety guarantees that no points are deleted in dry-run mode
  - CORPUS_ORPHAN_POINTS_TOTAL metric increments on deletion
  - reindex_corpus batch orchestration with --plan-only and --dry-run
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.metrics import CORPUS_ORPHAN_POINTS_TOTAL
from scripts.ops.reconcile_orphans import diff_point_ids, reconcile_source_orphans
from scripts.ops.reindex_corpus import orchestrate_reindex
from services.qdrant.client import QdrantClientManager


def _collection_info(points_count: int, *, dim: int = 1024, with_sparse: bool = True):
    """Minimal stand-in for qdrant get_collection() shaped like the real response."""
    vectors = {"dense": SimpleNamespace(size=dim)}
    sparse = {"sparse": SimpleNamespace()} if with_sparse else None
    payload_schema = {name: SimpleNamespace() for name, _ in QdrantClientManager._PAYLOAD_INDEXES}
    return SimpleNamespace(
        points_count=points_count,
        config=SimpleNamespace(params=SimpleNamespace(vectors=vectors, sparse_vectors=sparse)),
        payload_schema=payload_schema,
    )


def test_diff_point_ids():
    expected = {"p1", "p2", "p3"}
    stored = {"p2", "p3", "orphan_1", "orphan_2"}

    diff = diff_point_ids(expected, stored)
    assert diff["orphans"] == {"orphan_1", "orphan_2"}
    assert diff["missing"] == {"p1"}
    assert diff["matched"] == {"p2", "p3"}


def test_reconcile_source_orphans_deletes_extra_points():
    client = MagicMock()
    mock_p1 = MagicMock(id="p1")
    mock_p2 = MagicMock(id="p2")
    mock_orphan = MagicMock(id="p_orphan")

    # Mock indexer scroll to return stored points
    client.scroll.return_value = ([mock_p1, mock_p2, mock_orphan], None)

    init_orphans = CORPUS_ORPHAN_POINTS_TOTAL._value.get()

    report = reconcile_source_orphans(
        source_url="https://example.com/test",
        expected_point_ids=["p1", "p2"],
        client=client,
        collection="test_col",
        dry_run=False,
    )

    assert report["stored_count"] == 3
    assert report["expected_count"] == 2
    assert report["orphan_count"] == 1
    assert report["orphan_ids"] == ["p_orphan"]
    assert report["deleted_count"] == 1
    assert report["dry_run"] is False

    client.delete.assert_called_once_with(
        collection_name="test_col",
        points_selector=["p_orphan"],
    )
    assert CORPUS_ORPHAN_POINTS_TOTAL._value.get() == init_orphans + 1


def test_reconcile_source_orphans_dry_run_safety():
    client = MagicMock()
    mock_p1 = MagicMock(id="p1")
    mock_orphan = MagicMock(id="p_orphan")
    client.scroll.return_value = ([mock_p1, mock_orphan], None)

    init_orphans = CORPUS_ORPHAN_POINTS_TOTAL._value.get()

    report = reconcile_source_orphans(
        source_url="https://example.com/test",
        expected_point_ids=["p1"],
        client=client,
        collection="test_col",
        dry_run=True,
    )

    assert report["orphan_count"] == 1
    assert report["deleted_count"] == 0
    assert report["dry_run"] is True

    # Critical safety invariant: delete must never be called on dry-run
    client.delete.assert_not_called()
    assert CORPUS_ORPHAN_POINTS_TOTAL._value.get() == init_orphans


def test_reindex_batch_job_plan_only():
    client = MagicMock()
    mock_aliases = MagicMock(aliases=[])
    client.get_aliases.return_value = mock_aliases

    res = orchestrate_reindex(
        alias="test_alias",
        target_version=2,
        plan_only=True,
        client=client,
    )

    assert res["status"] == "planned"
    assert res["plan_only"] is True
    plan = res["plan"]
    assert plan["alias"] == "test_alias"
    assert plan["new_collection"] == "test_alias_v2"
    assert "expected_fingerprint" in plan
    # Did not mutate collections
    client.create_collection.assert_not_called()


def test_reindex_batch_job_dry_run():
    client = MagicMock()
    mock_aliases = MagicMock(aliases=[])
    client.get_aliases.return_value = mock_aliases
    client.get_collection.return_value = _collection_info(100)
    client.scroll.return_value = ([], None)

    res = orchestrate_reindex(
        alias="test_alias",
        target_version=2,
        min_points=10,
        dry_run=True,
        client=client,
    )

    assert res["status"] == "dry_run_success"
    assert res["dry_run"] is True
    assert res["swapped"] is False
    # Swap must not be called in dry run mode
    client.update_collection_aliases.assert_not_called()


def test_reindex_refuses_empty_target_collection():
    """P0-1: an empty built collection must never pass validation."""
    client = MagicMock()
    client.get_aliases.return_value = MagicMock(aliases=[])
    client.get_collection.side_effect = [
        _collection_info(5000),  # live baseline read
        _collection_info(5000),  # build_collection existence probe
        _collection_info(0),  # validate_collection read of the empty target
    ]
    client.scroll.return_value = ([], None)

    res = orchestrate_reindex(
        alias="live_alias",
        target_collection="live_alias_v2",
        target_version=2,
        confirm=True,
        client=client,
    )

    assert res["status"] == "validation_failed"
    assert res["validation"]["count_valid"] is False
    client.update_collection_aliases.assert_not_called()


def test_reindex_refuses_swap_when_target_smaller_than_live():
    """P0-1: the floor is the live collection's point count, not just --min-points."""
    client = MagicMock()
    client.get_aliases.return_value = MagicMock(aliases=[])
    live_info = _collection_info(5000)
    empty_info = _collection_info(12)
    client.get_collection.side_effect = [
        _collection_info(5000),  # plan/live baseline read
        empty_info,  # build_collection existence probe
        empty_info,  # validate_collection read
    ]
    client.scroll.return_value = ([], None)

    res = orchestrate_reindex(
        alias="live_alias",
        target_collection="live_alias_v2",
        target_version=2,
        confirm=True,
        client=client,
    )

    assert res["status"] == "validation_failed"
    assert res["validation"]["baseline_points"] == 5000
    assert res["validation"]["count_valid"] is False
    client.update_collection_aliases.assert_not_called()
    assert live_info.points_count == 5000


def test_reindex_refuses_swap_without_confirmation():
    """P0-1: the alias swap requires an explicit --yes."""
    client = MagicMock()
    client.get_aliases.return_value = MagicMock(aliases=[])
    client.get_collection.return_value = _collection_info(1000)
    client.scroll.return_value = ([], None)

    res = orchestrate_reindex(
        alias="live_alias",
        target_collection="live_alias_v2",
        target_version=2,
        client=client,
    )

    assert res["status"] == "confirmation_required"
    assert res["swapped"] is False
    client.update_collection_aliases.assert_not_called()


def test_reindex_refuses_when_target_is_live_collection():
    """P0-1: never treat the serving collection as the rebuild target."""
    client = MagicMock()
    client.get_aliases.return_value = MagicMock(
        aliases=[SimpleNamespace(alias_name="live_alias", collection_name="live_col")]
    )

    res = orchestrate_reindex(
        alias="live_alias",
        target_collection="live_col",
        target_version=2,
        confirm=True,
        client=client,
    )

    assert res["status"] == "refused"
    client.update_collection_aliases.assert_not_called()


def test_reindex_rejects_collection_without_named_vectors():
    """P0-1: named-vector shape is validated, not just point count."""
    client = MagicMock()
    client.get_aliases.return_value = MagicMock(aliases=[])
    bad = _collection_info(1000)
    bad.config.params.vectors = SimpleNamespace(size=1024)  # unnamed
    client.get_collection.return_value = bad
    client.scroll.return_value = ([], None)

    res = orchestrate_reindex(
        alias="live_alias",
        target_collection="live_alias_v2",
        target_version=2,
        confirm=True,
        client=client,
    )

    assert res["status"] == "validation_failed"
    assert res["validation"]["vectors_valid"] is False
    client.update_collection_aliases.assert_not_called()


def test_reindex_reports_missing_payload_indexes():
    client = MagicMock()
    client.get_aliases.return_value = MagicMock(aliases=[])
    partial = _collection_info(1000)
    partial.payload_schema = {"source_url": SimpleNamespace()}
    client.get_collection.return_value = partial
    client.scroll.return_value = ([], None)

    res = orchestrate_reindex(
        alias="live_alias",
        target_collection="live_alias_v2",
        target_version=2,
        confirm=True,
        client=client,
    )

    assert res["status"] == "validation_failed"
    assert res["validation"]["indexes_valid"] is False
    assert "raptor_level" in res["validation"]["missing_indexes"]
    client.update_collection_aliases.assert_not_called()


def test_reconcile_refuses_empty_expected_ids():
    """P0-2: an empty expected set would classify every stored point as an orphan."""
    client = MagicMock()
    client.scroll.return_value = ([MagicMock(id="p1")], None)

    with pytest.raises(ValueError, match="expected_point_ids is empty"):
        reconcile_source_orphans(
            source_url="https://example.com/test",
            expected_point_ids=[],
            client=client,
            collection="test_col",
            dry_run=False,
        )

    client.delete.assert_not_called()


def test_reconcile_refuses_disjoint_full_purge():
    """P0-2: a mismatched ids file must not purge the whole source."""
    client = MagicMock()
    client.scroll.return_value = ([MagicMock(id="p1"), MagicMock(id="p2")], None)

    with pytest.raises(ValueError, match="refusing to delete all"):
        reconcile_source_orphans(
            source_url="https://example.com/test",
            expected_point_ids=["something-else"],
            client=client,
            collection="test_col",
            dry_run=False,
        )

    client.delete.assert_not_called()


def test_reconcile_is_dry_run_by_default():
    """P0-2: deletion is opt-in, not opt-out."""
    client = MagicMock()
    client.scroll.return_value = ([MagicMock(id="p1"), MagicMock(id="p_orphan")], None)

    report = reconcile_source_orphans(
        source_url="https://example.com/test",
        expected_point_ids=["p1"],
        client=client,
        collection="test_col",
    )

    assert report["dry_run"] is True
    assert report["deleted_count"] == 0
    client.delete.assert_not_called()


def test_reconcile_full_purge_requires_explicit_flag():
    client = MagicMock()
    client.scroll.return_value = ([MagicMock(id="p1"), MagicMock(id="p2")], None)

    report = reconcile_source_orphans(
        source_url="https://example.com/test",
        expected_point_ids=["x"],
        client=client,
        collection="test_col",
        dry_run=True,
        allow_full_purge=True,
    )

    assert report["full_purge"] is True
    client.delete.assert_not_called()
