#!/usr/bin/env python3
"""Read-only drift audit of the active Qdrant collection and the OKF compiled file.

Checks that RUN:
  - Qdrant facets (record_type, corpus_version, domain_rights_status, speaker_verified,
    source_type). Drift = a record_type outside the expected set, or a
    domain_rights_status outside {licensed, unverified}. The unverified-rights count is
    reported as information (such points exist by design); speaker_verified is not judged.
  - OKF compiled.json verified/unverified counts (informational).

NOT CHECKED: memgraph, postgres. There is no Qdrant<->Memgraph span reconciliation and no
Postgres governance-table check in this script; a clean result says nothing about them.

Exit codes: 0 = every check ran and found no drift; 1 = drift detected;
2 = a check could not run (error). Error takes precedence over drift.
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


FACET_LIMIT = 100
EXPECTED_RECORD_TYPES = {"retrieval_child", "parent_unit", "speech_turn_clip", "passage", "child"}
ALLOWED_RIGHTS = {"licensed", "unverified"}


def check_qdrant_drift(qdrant_url: str, collection: str) -> dict[str, Any]:
    import urllib.request

    api_key = os.environ.get("QDRANT_API_KEY") or os.environ.get("QDRANT_READ_ONLY_API_KEY")
    auth: dict[str, str] = {"api-key": api_key} if api_key else {}

    def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{qdrant_url.rstrip('/')}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", **auth},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())

    info_req = urllib.request.urlopen(
        urllib.request.Request(f"{qdrant_url.rstrip('/')}/collections/{collection}", headers=auth),
        timeout=5,
    )
    info = json.loads(info_req.read().decode()).get("result", {})
    facets: dict[str, Any] = {}
    errors: list[str] = []
    for key in (
        "record_type",
        "corpus_version",
        "domain_rights_status",
        "speaker_verified",
        "source_type",
    ):
        try:
            res = _post(
                f"/collections/{collection}/facet",
                {"key": key, "limit": FACET_LIMIT, "exact": True},
            )
            facets[key] = [(h["value"], h["count"]) for h in res.get("result", {}).get("hits", [])]
            if len(facets[key]) >= FACET_LIMIT:
                errors.append(f"facet {key}: result hit limit {FACET_LIMIT}; truncated")
        except Exception as exc:
            errors.append(f"facet {key}: {type(exc).__name__}: {exc}")
    points_count = info.get("points_count", 0)
    if not points_count:
        errors.append(f"collection {collection} is empty (points_count={points_count})")
    missing_record_type: int | None = None
    try:
        res = _post(
            f"/collections/{collection}/points/count",
            {
                "filter": {"must": [{"is_empty": {"key": "record_type"}}]},
                "exact": True,
            },
        )
        missing_record_type = res.get("result", {}).get("count")
    except Exception as exc:
        errors.append(f"count missing record_type: {type(exc).__name__}: {exc}")
    return {
        "collection": collection,
        "points_count": points_count,
        "points_missing_record_type": missing_record_type,
        "facets": facets,
        "errors": errors,
    }


def find_drift(qdrant: dict[str, Any]) -> list[str]:
    facets = qdrant["facets"]
    drift: list[str] = []
    unexpected = [
        (v, c) for v, c in facets.get("record_type", []) if v not in EXPECTED_RECORD_TYPES
    ]
    if unexpected:
        drift.append(f"unexpected record_type: {unexpected}")
    bad = [(v, c) for v, c in facets.get("domain_rights_status", []) if v not in ALLOWED_RIGHTS]
    if bad:
        drift.append(f"unexpected domain_rights_status: {bad}")
    return drift


def check_okf_drift() -> dict[str, Any]:
    compiled_path = ROOT / "memory" / "okf" / "compiled.json"
    if not compiled_path.is_file():
        raise FileNotFoundError(f"OKF compiled file missing: {compiled_path}")
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

    errors: list[str] = []
    try:
        qdrant = check_qdrant_drift(args.qdrant_url, args.collection)
    except Exception as exc:
        errors.append(f"qdrant: {type(exc).__name__}: {exc}")
        qdrant = {"facets": {}, "errors": []}
    errors.extend(f"qdrant {e}" for e in qdrant["errors"])
    okf: dict[str, Any] = {}
    try:
        okf = check_okf_drift()
    except Exception as exc:
        errors.append(f"okf: {type(exc).__name__}: {exc}")
    drift = find_drift(qdrant) if not qdrant["errors"] and not errors else []
    unverified_rights = sum(
        c for v, c in qdrant["facets"].get("domain_rights_status", []) if v == "unverified"
    )
    report = {
        "info": {
            "unverified_rights_points": unverified_rights,
            "points_missing_record_type": qdrant.get("points_missing_record_type"),
        },
        "qdrant": qdrant,
        "okf": okf,
        "not_checked": ["memgraph", "postgres"],
        "errors": errors,
        "drift": drift,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=== Cross-Store Reconciliation Report ===")
        print(json.dumps(report, indent=2))
        print("NOT CHECKED: memgraph, postgres")
        for e in errors:
            print(f"ERROR: {e}")
        for d in drift:
            print(f"DRIFT: {d}")
    if errors:
        return 2
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
