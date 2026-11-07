#!/usr/bin/env python3
"""Quarantine named first-person points with a reversible payload flag (DATA-15).

Owner approval: Harsha, 2026-11-07 ("quarantine"). It writes two payload keys with set_payload:
  quality_status="quarantined" and quarantine_reason=<--reason>. Serving already refuses a point
  with either (first_person_context_store._payload_is_quarantined). No vector, text, hash or id
  changes; the point count never changes. Dry run unless --apply. It never prints text.
Rollback: --release (delete_payload of both keys; dry run unless --apply).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

KEYS = ["quality_status", "quarantine_reason"]


def run(client, collection: str, ids: list[str], *, reason: str, apply: bool, release: bool):
    before = client.get_collection(collection).points_count
    found = {str(r.id): r for r in client.retrieve(collection, ids, with_payload=KEYS)}
    missing = [i for i in ids if str(i) not in found]
    report: dict[str, Any] = {
        "collection": collection,
        "apply": apply,
        "release": release,
        "points_before": before,
        "missing": missing,
        "previous": {
            str(i): {k: (found[str(i)].payload or {}).get(k) for k in KEYS}
            for i in ids
            if str(i) in found
        },
        "changed": 0,
    }
    if apply and not missing:
        present = [i for i in ids if str(i) in found]
        if release:
            client.delete_payload(collection_name=collection, keys=KEYS, points=present, wait=True)
        else:
            client.set_payload(
                collection_name=collection,
                payload={"quality_status": "quarantined", "quarantine_reason": reason},
                points=present,
                wait=True,
            )
        report["changed"] = len(present)
    report["points_after"] = client.get_collection(collection).points_count
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--collection", default="first_person_v10")
    ap.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    ap.add_argument("--reason", default="test_data_not_a_teaching_clip")
    ap.add_argument("--release", action="store_true", help="remove the flag")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(
            url=args.qdrant_url, api_key=os.environ.get("QDRANT_API_KEY") or None, timeout=60
        )
        report = run(
            client,
            args.collection,
            args.ids,
            reason=args.reason,
            apply=args.apply,
            release=args.release,
        )
    except Exception as exc:
        print(f"Quarantine could not run: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not report["missing"] and report["points_before"] == report["points_after"] else 1


if __name__ == "__main__":
    sys.exit(main())
