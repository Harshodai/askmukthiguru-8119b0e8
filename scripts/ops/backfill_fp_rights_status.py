#!/usr/bin/env python3
"""Stamp the missing domain_rights_status on first-person children (DATA-15, C-L7).

Owner approval: Harsha, 2026-11-07 ("its ok, you can do those"). Scope is fixed:
  * It writes ONE payload key, domain_rights_status, with set_payload. No vector, no
    verbatim_text, no hash, no id, no other key. The point count never changes.
  * The value comes from the same rights-register resolver that serving uses
    (services.qdrant.indexer.resolve_source_rights_status). A video the register does not
    clear is left untouched and listed. Nothing is stamped "licensed" by assumption.
  * Only children (record_type=retrieval_child) that LACK the key are touched.
  * Before any write it saves a backup file (point ids, video ids, previous state "absent").
    Rollback: delete_payload(keys=["domain_rights_status"]) on the ids in that file.
  * Without --apply it is a dry run and writes nothing.
The report holds counts, video ids and point-id counts. It never holds text.

    backend/.venv/bin/python scripts/ops/backfill_fp_rights_status.py --backup /tmp/rights_backup.json
    backend/.venv/bin/python scripts/ops/backfill_fp_rights_status.py --backup /tmp/rights_backup.json --apply
Exit code: 0 ok, 1 a check failed (count changed, ids left unstamped that the register clears), 2 error.
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

BATCH = 256


def _missing_children(client, collection: str):
    from qdrant_client import models

    flt = models.Filter(
        must=[
            models.FieldCondition(
                key="record_type", match=models.MatchValue(value="retrieval_child")
            )
        ]
    )
    offset = None
    while True:
        points, offset = client.scroll(
            collection,
            scroll_filter=flt,
            limit=500,
            offset=offset,
            with_payload=["video_id", "source_url", "domain_rights_status"],
            with_vectors=False,
        )
        for p in points:
            pl = p.payload or {}
            if "domain_rights_status" not in pl:
                yield p.id, str(pl.get("video_id") or ""), str(pl.get("source_url") or "")
        if offset is None:
            return


def plan(client, collection: str, resolve) -> dict[str, Any]:
    """Group the keyless children by video and ask the register about each video once."""
    by_video: dict[str, list[Any]] = {}
    urls: dict[str, str] = {}
    for pid, vid, url in _missing_children(client, collection):
        by_video.setdefault(vid, []).append(pid)
        urls.setdefault(vid, url)
    stamp: dict[str, list[Any]] = {}
    left: dict[str, int] = {}
    for vid, ids in by_video.items():
        url = urls[vid] or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
        status = resolve(url, vid) if vid else "unverified"
        if status == "licensed":
            stamp[vid] = ids
        else:
            left[vid or "<no video_id>"] = len(ids)
    return {"stamp": stamp, "left": left, "missing_total": sum(len(v) for v in by_video.values())}


def run(client, collection: str, resolve, *, apply: bool, backup: Path | None) -> dict[str, Any]:
    before = client.get_collection(collection).points_count
    pl = plan(client, collection, resolve)
    n_stamp = sum(len(v) for v in pl["stamp"].values())
    report: dict[str, Any] = {
        "collection": collection,
        "apply": apply,
        "points_before": before,
        "children_missing_status": pl["missing_total"],
        "to_stamp_licensed": n_stamp,
        "videos_to_stamp": len(pl["stamp"]),
        "left_untouched_not_cleared": sum(pl["left"].values()),
        "videos_left_untouched": pl["left"],
        "written": 0,
    }
    if apply:
        if backup is None:
            raise SystemExit("--apply needs --backup")
        backup.write_text(
            json.dumps(
                {
                    "collection": collection,
                    "key": "domain_rights_status",
                    "previous": "absent",
                    "rollback": "delete_payload(keys=['domain_rights_status']) on these ids",
                    "ids_by_video": {v: [str(i) for i in ids] for v, ids in pl["stamp"].items()},
                },
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        for ids in pl["stamp"].values():
            for i in range(0, len(ids), BATCH):
                chunk = ids[i : i + BATCH]
                client.set_payload(
                    collection_name=collection,
                    payload={"domain_rights_status": "licensed"},
                    points=chunk,
                    wait=True,
                )
                report["written"] += len(chunk)
    report["points_after"] = client.get_collection(collection).points_count
    report["children_still_missing"] = plan(client, collection, resolve)["missing_total"]
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--collection", default="first_person_v10")
    ap.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    ap.add_argument(
        "--backup", type=Path, help="file for the pre-write backup (required with --apply)"
    )
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    if args.apply and not args.backup:
        print("--apply needs --backup", file=sys.stderr)
        return 2
    try:
        from qdrant_client import QdrantClient

        from services.qdrant.indexer import resolve_source_rights_status

        client = QdrantClient(
            url=args.qdrant_url, api_key=os.environ.get("QDRANT_API_KEY") or None, timeout=120
        )
        report = run(
            client,
            args.collection,
            resolve_source_rights_status,
            apply=args.apply,
            backup=args.backup,
        )
    except Exception as exc:
        print(f"Backfill could not run: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["points_before"] != report["points_after"]:
        print("FAIL: point count changed", file=sys.stderr)
        return 1
    if args.apply and report["children_still_missing"] != report["left_untouched_not_cleared"]:
        print("FAIL: cleared children are still missing the status", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
