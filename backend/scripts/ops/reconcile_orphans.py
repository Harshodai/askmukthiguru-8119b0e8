#!/usr/bin/env python3
"""Orphan point reconciliation helper (DE-1.4).

Diffs expected deterministic point ID set vs stored point IDs for a source URL.
Deletes extra points from Qdrant and updates metric CORPUS_ORPHAN_POINTS_TOTAL.
Supports --dry-run to audit without modifying Qdrant.

Usage:
    python -m scripts.ops.reconcile_orphans --source-url "https://example.com/video" --dry-run
    python -m scripts.ops.reconcile_orphans --source-url "The_Four_Sacred_Secrets.pdf"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve()
if (_HERE.parents[2] / "backend").is_dir():
    _BACKEND = _HERE.parents[2] / "backend"
else:
    _BACKEND = _HERE.parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import settings
from app.metrics import CORPUS_ORPHAN_POINTS_TOTAL
from services.qdrant.client import QdrantClientManager
from services.qdrant.indexer import QdrantIndexer

logger = logging.getLogger(__name__)


def diff_point_ids(
    expected_ids: Iterable[str | int],
    stored_ids: Iterable[str | int],
) -> dict[str, set[str | int]]:
    """Compute set difference between expected and stored point IDs."""
    expected = set(expected_ids)
    stored = set(stored_ids)
    orphans = stored - expected
    missing = expected - stored
    matched = expected & stored
    return {
        "orphans": orphans,
        "missing": missing,
        "matched": matched,
    }


def reconcile_source_orphans(
    source_url: str,
    expected_point_ids: Iterable[str | int],
    client: Any = None,
    collection: Optional[str] = None,
    dry_run: bool = True,
    allow_full_purge: bool = False,
) -> dict[str, Any]:
    """Diff expected deterministic ID set vs stored point IDs for a source URL.

    Deletes extra (orphan) points from Qdrant only when `dry_run=False`.
    Updates metric CORPUS_ORPHAN_POINTS_TOTAL when points are deleted.

    Safety: an empty expected set is refused outright (it would make every
    stored point an orphan), and a diff that would delete *all* stored points
    for the source requires `allow_full_purge=True`. Without those guards a
    missing or mismatched ids file silently purges the whole source.
    """
    col = collection or getattr(settings, "qdrant_collection", "spiritual_wisdom_contextual")
    if client is None:
        client_mgr = QdrantClientManager(collection=col)
        client = client_mgr.client
    indexer = QdrantIndexer(client, collection=col)

    expected_set = {str(x) for x in expected_point_ids}
    if not expected_set:
        raise ValueError(
            "expected_point_ids is empty — refusing to reconcile: every stored point "
            "would be classified as an orphan and deleted"
        )

    stored_ids = indexer._source_point_ids(source_url)
    diff = diff_point_ids(expected_set, stored_ids)
    orphans = diff["orphans"]
    missing = diff["missing"]

    full_purge = bool(stored_ids) and len(orphans) == len(set(stored_ids))
    if full_purge and not allow_full_purge:
        raise ValueError(
            f"refusing to delete all {len(orphans)} stored points for {source_url!r}; "
            "the expected-id set and the stored set are disjoint, which usually means "
            "the wrong ids file. Re-run with --allow-full-purge to intend it."
        )

    deleted_count = 0
    if orphans and not dry_run:
        client.delete(
            collection_name=col,
            points_selector=list(orphans),
        )
        deleted_count = len(orphans)
        try:
            CORPUS_ORPHAN_POINTS_TOTAL.inc(deleted_count)
        except Exception as exc:
            logger.warning("Failed to increment CORPUS_ORPHAN_POINTS_TOTAL: %s", exc)

    return {
        "source_url": source_url,
        "collection": col,
        "stored_count": len(stored_ids),
        "expected_count": len(expected_set),
        "matched_count": len(diff["matched"]),
        "orphan_count": len(orphans),
        "orphan_ids": sorted(list(orphans), key=str),
        "missing_count": len(missing),
        "missing_ids": sorted(list(missing), key=str),
        "dry_run": dry_run,
        "full_purge": full_purge,
        "deleted_count": deleted_count,
    }


def _load_expected_ids(path: Path, source_url: str) -> list[str]:
    """Load the expected point-id list; raise on anything unusable."""
    if not path.is_file():
        raise ValueError(f"expected-ids file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        ids = [str(x) for x in data]
    elif isinstance(data, dict):
        ids = [str(x) for x in data.get(source_url, [])]
    else:
        raise ValueError(
            f"expected-ids file must contain a list or a {{source_url: [ids]}} map, got {type(data).__name__}"
        )
    if not ids:
        raise ValueError(f"expected-ids file {path} contains no ids for {source_url!r}")
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile orphan Qdrant points (DE-1.4)")
    parser.add_argument("--source-url", required=True, help="Canonical source URL or identifier")
    parser.add_argument(
        "--expected-ids-file",
        required=True,
        help="JSON file with the expected deterministic point IDs (list, or {source_url: [ids]})",
    )
    parser.add_argument("--collection", default=None, help="Target Qdrant collection name")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete orphan points; without it the run reports only",
    )
    parser.add_argument(
        "--allow-full-purge",
        action="store_true",
        help="permit deleting every stored point for the source (disjoint id sets)",
    )
    args = parser.parse_args()

    try:
        expected_ids = _load_expected_ids(Path(args.expected_ids_file), args.source_url)
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}, indent=2))
        return 2

    try:
        report = reconcile_source_orphans(
            source_url=args.source_url,
            expected_point_ids=expected_ids,
            collection=args.collection,
            dry_run=not args.apply,
            allow_full_purge=args.allow_full_purge,
        )
    except ValueError as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}, indent=2))
        return 2

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
