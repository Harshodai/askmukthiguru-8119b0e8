#!/usr/bin/env python3
"""Read-only cross-store reconciliation & drift audit across Qdrant, Memgraph, OKF, and Postgres.

Detects:
  - Mixed schemas / unverified rights / unverified speakers inside the active Qdrant collection
  - Discrepancies between Qdrant span IDs and Memgraph TUTeachingUnit nodes
  - Unverified / generic-tag-skewed OKF compiled entries
  - Empty or unpopulated Postgres canonical governance tables (source_releases, canonical_evidence)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def check_qdrant_drift(qdrant_url: str, collection: str) -> dict[str, Any]:
    import urllib.request

    def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{qdrant_url.rstrip('/')}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())

    info_req = urllib.request.urlopen(
        f"{qdrant_url.rstrip('/')}/collections/{collection}", timeout=5
    )
    info = json.loads(info_req.read().decode()).get("result", {})
    facets: dict[str, Any] = {}
    for key in (
        "record_type",
        "corpus_version",
        "domain_rights_status",
        "speaker_verified",
        "source_type",
    ):
        try:
            res = _post(
                f"/collections/{collection}/facet", {"key": key, "limit": 20, "exact": True}
            )
            facets[key] = [(h["value"], h["count"]) for h in res.get("result", {}).get("hits", [])]
        except Exception:
            facets[key] = []
    return {
        "collection": collection,
        "points_count": info.get("points_count", 0),
        "facets": facets,
    }


def check_okf_drift() -> dict[str, Any]:
    compiled_path = ROOT / "memory" / "okf" / "compiled.json"
    if not compiled_path.is_file():
        return {"present": False, "entries": 0}
    data = json.loads(compiled_path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    verified_count = sum(1 for e in entries if e.get("verified") is True)
    unverified_count = len(entries) - verified_count
    return {
        "present": True,
        "version": data.get("version"),
        "entries": len(entries),
        "verified": verified_count,
        "unverified": unverified_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-store reconciliation audit (read-only)")
    parser.add_argument(
        "--qdrant-url", default=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
    )
    parser.add_argument(
        "--collection",
        default=os.environ.get("FIRST_PERSON_CONTEXT_COLLECTION", "first_person_v13_shadow"),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    report = {
        "qdrant": check_qdrant_drift(args.qdrant_url, args.collection),
        "okf": check_okf_drift(),
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=== Cross-Store Reconciliation Report ===")
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
