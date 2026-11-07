#!/usr/bin/env python3
"""Give hashless first-person children their source_text_hash and their derived point id (C-L3, C-L5).

Owner approval: Harsha, 2026-11-07. Scope per point id given on the command line:
  * source_text_hash := sha256(verbatim_text). verbatim_text and transcript_hash are NEVER changed.
  * The point moves to point_id_for_record(source_span_id): same vectors, same payload plus the hash.
  * Before any write the full old record (payload and vectors) goes to --backup. That file holds
    verbatim text, so keep it local. This script never prints text.
  * It stops without writing if the point has no verbatim_text or source_span_id, if the new id
    already exists, or if the point already has a matching hash and id.
  * The point count must be the same after the run.
Without --apply it is a dry run. Rollback: upsert the backup record back and delete the new id.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.first_person_context_store import point_id_for_record  # noqa: E402


def fix_points(client, collection: str, ids: list[str], *, apply: bool, backup: Path | None):
    from qdrant_client import models

    before = client.get_collection(collection).points_count
    recs = client.retrieve(collection, ids, with_payload=True, with_vectors=True)
    found = {str(r.id): r for r in recs}
    plan: list[dict[str, Any]] = []
    for pid in ids:
        rec = found.get(pid)
        if rec is None:
            plan.append({"id": pid, "action": "stop", "why": "not found"})
            continue
        pl = dict(rec.payload or {})
        text, span = pl.get("verbatim_text"), pl.get("source_span_id")
        if not isinstance(text, str) or not span:
            plan.append({"id": pid, "action": "stop", "why": "no verbatim_text or source_span_id"})
            continue
        new_id = point_id_for_record(str(span))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if new_id == pid and pl.get("source_text_hash") == digest:
            plan.append({"id": pid, "action": "skip", "why": "already correct"})
            continue
        if new_id != pid and client.retrieve(collection, [new_id], with_payload=False):
            plan.append({"id": pid, "action": "stop", "why": "new id already exists"})
            continue
        plan.append(
            {"id": pid, "new_id": new_id, "action": "move", "had_hash": "source_text_hash" in pl}
        )
    report: dict[str, Any] = {
        "collection": collection,
        "apply": apply,
        "points_before": before,
        "plan": plan,
        "moved": 0,
    }
    if apply:
        if any(p["action"] == "stop" for p in plan):
            raise SystemExit("a point cannot be fixed; nothing written")
        if backup is None:
            raise SystemExit("--apply needs --backup")
        backup.write_text(
            json.dumps(
                [
                    {"id": str(r.id), "payload": r.payload, "vector": r.vector}
                    for r in found.values()
                ],
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
        for p in plan:
            if p["action"] != "move":
                continue
            rec = found[p["id"]]
            pl = dict(rec.payload or {})
            pl["source_text_hash"] = hashlib.sha256(pl["verbatim_text"].encode("utf-8")).hexdigest()
            client.upsert(
                collection,
                [models.PointStruct(id=p["new_id"], vector=rec.vector, payload=pl)],
                wait=True,
            )
            if p["new_id"] != p["id"]:
                client.delete(
                    collection, points_selector=models.PointIdsList(points=[p["id"]]), wait=True
                )
            report["moved"] += 1
    report["points_after"] = client.get_collection(collection).points_count
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="+", help="point ids to fix")
    ap.add_argument("--collection", default="first_person_v10")
    ap.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    ap.add_argument("--backup", type=Path)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(
            url=args.qdrant_url, api_key=os.environ.get("QDRANT_API_KEY") or None, timeout=60
        )
        report = fix_points(client, args.collection, args.ids, apply=args.apply, backup=args.backup)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Fix could not run: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["points_before"] == report["points_after"] else 1


if __name__ == "__main__":
    sys.exit(main())
