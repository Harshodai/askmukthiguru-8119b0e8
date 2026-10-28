"""Tests for Anti-Entropy and Orphan Reconciliation (DE-1.4, DE-1.5).

Verifies:
  - diff_point_ids correctly identifies orphans, missing, and matched sets
  - reconcile_source_orphans detects extra (orphan) points and deletes them
  - dry_run safety guarantees that no points are deleted in dry-run mode
  - CORPUS_ORPHAN_POINTS_TOTAL metric increments on deletion
  - reindex_corpus batch orchestration with --plan-only and --dry-run
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.metrics import CORPUS_ORPHAN_POINTS_TOTAL
from scripts.ops.reconcile_orphans import diff_point_ids, reconcile_source_orphans
from scripts.ops.reindex_corpus import orchestrate_reindex


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
    mock_info = MagicMock(points_count=100)
    client.get_collection.return_value = mock_info
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
