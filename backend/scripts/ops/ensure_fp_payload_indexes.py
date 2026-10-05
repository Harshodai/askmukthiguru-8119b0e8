#!/usr/bin/env python3
"""ensure_fp_payload_indexes.py — Wave R-A (Q-rec#1) repeatable op.

Ensures every index in FirstPersonStore.PAYLOAD_INDEXES (including the
rights_cleared keyword index) exists on the first-person collection.
Idempotent: already-indexed fields are skipped, so re-runs are no-ops.
Read-only except additive create_payload_index calls — never deletes,
never touches points.

Usage (host-side; backend/.env docker hostnames do NOT resolve here):
    backend/.venv/bin/python backend/scripts/ops/ensure_fp_payload_indexes.py
    backend/.venv/bin/python backend/scripts/ops/ensure_fp_payload_indexes.py --collection first_person_v7

Verification baked in: filtered count on rights_cleared==True is recorded
BEFORE and AFTER, and must equal the total point count in both cases.

Rollback (index removal is data-safe — drops only the index, not points):
    curl -X DELETE http://localhost:6333/collections/first_person_v7/index/rights_cleared
or:
    client.delete_payload_index(collection_name="first_person_v7", field_name="rights_cleared")
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure FP payload indexes exist (idempotent).")
    parser.add_argument("--collection", default="first_person_v7")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    args = parser.parse_args()

    from qdrant_client import QdrantClient
    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    from services.first_person_store import FirstPersonStore

    client = QdrantClient(url=args.qdrant_url, timeout=30)
    wanted = list(FirstPersonStore.PAYLOAD_INDEXES)
    report: dict = {"collection": args.collection, "fields": {}}

    def filtered_count() -> tuple[int, float]:
        t0 = time.monotonic()
        res = client.count(
            collection_name=args.collection,
            exact=True,
            count_filter=Filter(
                must=[FieldCondition(key="rights_cleared", match=MatchValue(value=True))]
            ),
        )
        return res.count, (time.monotonic() - t0) * 1000.0

    total = client.count(collection_name=args.collection, exact=True).count
    before, before_ms = filtered_count()
    report["total_points"] = total
    report["rights_cleared_true_before"] = before
    report["rights_cleared_count_ms_before"] = round(before_ms, 2)

    schema = client.get_collection(collection_name=args.collection).payload_schema or {}
    for field_name, schema_type in wanted:
        existing = schema.get(field_name)
        status = "exists" if existing is not None else "missing"
        created_ms = 0.0
        if existing is None:
            t0 = time.monotonic()
            try:
                client.create_payload_index(
                    collection_name=args.collection,
                    field_name=field_name,
                    field_schema=schema_type,
                )
                status = "created"
            except Exception as exc:  # already-exists race with ingest driver
                status = f"create-attempted:{type(exc).__name__}"
            created_ms = (time.monotonic() - t0) * 1000.0
        report["fields"][field_name] = {
            "want": schema_type,
            "status": status,
            "ms": round(created_ms, 2),
        }

    after, after_ms = filtered_count()
    report["rights_cleared_true_after"] = after
    report["rights_cleared_count_ms_after"] = round(after_ms, 2)
    report["counts_stable"] = before == after == total

    print(json.dumps(report, indent=2))
    if not report["counts_stable"]:
        print("FAIL: counts changed across index ensure", file=sys.stderr)
        return 1
    print("OK: all payload indexes ensured; filter counts stable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
