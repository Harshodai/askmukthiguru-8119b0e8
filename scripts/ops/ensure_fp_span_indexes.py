#!/usr/bin/env python3
"""Create the missing SPAN_INDEXES payload indexes on a v10 collection (NEW-DQ-1, C-L8).

Additive only. It calls get_collection and create_payload_index. It never writes,
changes or deletes a point. Index removal is data-safe (delete_payload_index).
Without --apply it is a dry run: it lists the missing fields and creates nothing.

Run the read-only audit before and after:
    backend/.venv/bin/python scripts/ops/fp_live_audit.py --skip C-L1 --json before.json
    backend/.venv/bin/python scripts/ops/ensure_fp_span_indexes.py --apply
    backend/.venv/bin/python scripts/ops/fp_live_audit.py --json after.json

Exit code: 0 when no index is missing after the run (or in dry run with none missing),
1 when an index is still missing, 2 on usage or connection errors.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.first_person_context_store import SPAN_INDEXES  # noqa: E402


def ensure_indexes(client: Any, collection: str, *, apply: bool) -> dict[str, Any]:
    """Return a report. Create only the indexes the live schema lacks, and only if ``apply``."""
    points = client.get_collection(collection).points_count
    have = set((client.get_collection(collection).payload_schema or {}).keys())
    missing = [(k, t) for k, t in SPAN_INDEXES if k not in have]
    created: list[str] = []
    failed: dict[str, str] = {}
    if apply:
        for key, schema in missing:
            try:
                client.create_payload_index(
                    collection_name=collection, field_name=key, field_schema=schema, wait=True
                )
                created.append(key)
            except Exception as exc:  # report the type only
                failed[key] = type(exc).__name__
    have_after = set((client.get_collection(collection).payload_schema or {}).keys())
    still = sorted({k for k, _ in SPAN_INDEXES} - have_after)
    return {
        "collection": collection,
        "apply": apply,
        "points_before": points,
        "points_after": client.get_collection(collection).points_count,
        "missing_before": [k for k, _ in missing],
        "created": created,
        "failed": failed,
        "missing_after": still,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--collection", default="first_person_v10")
    ap.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    ap.add_argument("--apply", action="store_true", help="create the indexes (default: dry run)")
    args = ap.parse_args(argv)
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(
            url=args.qdrant_url, api_key=os.environ.get("QDRANT_API_KEY") or None, timeout=60
        )
        report = ensure_indexes(client, args.collection, apply=args.apply)
    except Exception as exc:
        print(f"Index run could not start: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["points_before"] != report["points_after"]:
        print("FAIL: point count changed", file=sys.stderr)
        return 1
    if args.apply and report["missing_after"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
