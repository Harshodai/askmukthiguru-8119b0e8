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
    dry_run: bool = False,
) -> dict[str, Any]:
    """Diff expected deterministic ID set vs stored point IDs for a source URL.

    Deletes extra (orphan) points from Qdrant unless dry_run is True.
    Updates metric CORPUS_ORPHAN_POINTS_TOTAL when points are deleted.
    """
    col = collection or getattr(settings, "qdrant_collection", "spiritual_wisdom_contextual")
    if client is None:
        client_mgr = QdrantClientManager(collection=col)
        client = client_mgr.client
    indexer = QdrantIndexer(client, collection=col)

    stored_ids = indexer._source_point_ids(source_url)
    diff = diff_point_ids(expected_point_ids, stored_ids)
    orphans = diff["orphans"]
    missing = diff["missing"]

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
        "expected_count": len(set(expected_point_ids)),
        "matched_count": len(diff["matched"]),
        "orphan_count": len(orphans),
        "orphan_ids": sorted(list(orphans), key=str),
        "missing_count": len(missing),
        "missing_ids": sorted(list(missing), key=str),
        "dry_run": dry_run,
        "deleted_count": deleted_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile orphan Qdrant points (DE-1.4)")
    parser.add_argument("--source-url", required=True, help="Canonical source URL or identifier")
    parser.add_argument(
        "--expected-ids-file", help="Path to JSON file containing list of expected point IDs"
    )
    parser.add_argument("--collection", default=None, help="Target Qdrant collection name")
    parser.add_argument("--dry-run", action="store_true", help="Report orphans without deleting")
    args = parser.parse_args()

    expected_ids: list[str] = []
    if args.expected_ids_file:
        path = Path(args.expected_ids_file)
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                expected_ids = [str(x) for x in data]
            elif isinstance(data, dict):
                expected_ids = [str(x) for x in data.get(args.source_url, [])]

    report = reconcile_source_orphans(
        source_url=args.source_url,
        expected_point_ids=expected_ids,
        collection=args.collection,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
