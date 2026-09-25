#!/usr/bin/env python3
"""Additive payload labelling: mark video-less points as ineligible for the
first-person route (P0, 2026-09-25).

Background
----------
docs/agent/first_person_baseline_prompt.md's P0 section + owner decision
(2026-09-25, (b)): video-less summary points are LABELLED and stay in general
chat, but must never be eligible for the first-person route (which serves an
exact recording at an exact second — a point with no `video_id` cannot back
that). A prior audit found 3,473 `content_type="summary"` points with no
`video_id`, and 4,818 video-less points in total (see `data_quality_audit.py`).

This script only ADDS two payload keys, never removes/changes anything else:
  - every video-less point:                     first_person_eligible=false
  - the subset that is also content_type="summary": provenance_kind="machine_summary"

Follows `fix_teacher_tags.py`'s style/shape: dry-run by default, `--apply`
snapshots the collection first, payload-only `set_payload` (vectors and all
other keys untouched), idempotent (a second run reports zero changes).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Optional


def has_video_id(payload: dict[str, Any]) -> bool:
    vid = payload.get("video_id")
    return bool(vid) and str(vid).strip() != ""


def classify_point(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Return the payload delta to set on this point, or None if it has a
    video_id and is therefore out of scope for this script entirely.

    Pure function of the point's own payload — no Qdrant/network access — so
    it is unit-testable with fake payloads (see tests/test_label_summary_points.py).
    """
    if has_video_id(payload):
        return None
    delta: dict[str, Any] = {"first_person_eligible": False}
    if payload.get("content_type") == "summary":
        delta["provenance_kind"] = "machine_summary"
    return delta


def _diff_point(pt_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    delta = classify_point(payload)
    if delta is None:
        return None
    changed = any(payload.get(k) != v for k, v in delta.items())
    return {
        "id": pt_id,
        "content_type": payload.get("content_type"),
        "delta": delta,
        "is_summary_group": "provenance_kind" in delta,
        "changed": changed,
    }


def _take_snapshot(qdrant_url: str, collection: str) -> str:
    import requests

    resp = requests.post(f"{qdrant_url}/collections/{collection}/snapshots", timeout=60)
    resp.raise_for_status()
    name = resp.json()["result"]["name"]
    print(f"Snapshot created: {name}")
    return name


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Apply the labels (default: dry-run only)")
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--collection", default=None, help="Defaults to settings.qdrant_collection")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv)

    collection = args.collection
    if not collection:
        from app.config import settings

        collection = settings.qdrant_collection

    from qdrant_client import QdrantClient

    client = QdrantClient(url=args.qdrant_url)
    print(f"{'APPLY' if args.apply else 'DRY-RUN'} — video-less point labelling")
    print(f"  Qdrant URL:  {args.qdrant_url}")
    print(f"  Collection:  {collection}\n")

    total = 0
    video_less: list[dict[str, Any]] = []
    summary_group: list[dict[str, Any]] = []
    preexisting_conflict = 0  # a target key already set to something ELSE (would not be purely additive)

    offset = None
    while True:
        res, offset = client.scroll(
            collection_name=collection,
            limit=args.batch_size,
            offset=offset,
            with_payload=["content_type", "video_id", "first_person_eligible", "provenance_kind"],
            with_vectors=False,
        )
        if not res:
            break
        for pt in res:
            total += 1
            payload = pt.payload or {}
            diff = _diff_point(str(pt.id), payload)
            if diff is None:
                continue
            video_less.append(diff)
            if diff["is_summary_group"]:
                summary_group.append(diff)
            for key, new_val in diff["delta"].items():
                existing = payload.get(key)
                if existing is not None and existing != new_val:
                    preexisting_conflict += 1
        if offset is None:
            break

    video_less_changed = [d for d in video_less if d["changed"]]
    summary_changed = [d for d in summary_group if d["changed"]]

    print(f"Scanned {total} points.\n")
    print("=== GROUP: content_type=summary AND no video_id ===")
    print(f"  target count:   {len(summary_group)}")
    print(f"  would change:   {len(summary_changed)}")
    print("\n=== GROUP: ALL points with no video_id (superset, includes the above) ===")
    print(f"  target count:   {len(video_less)}")
    print(f"  would change:   {len(video_less_changed)}")
    print(f"\nPre-existing conflicting values on target keys: {preexisting_conflict} "
          f"(0 means purely additive — no existing key would be overwritten with a different value)")

    if not args.apply:
        print("\n" + "=" * 60)
        print("DRY-RUN COMPLETE — Zero writes performed.")
        print("Re-run with --apply to write labels to live Qdrant.")
        print("=" * 60)
        return 0

    print("\n" + "=" * 60)
    snapshot_name = _take_snapshot(args.qdrant_url, collection)
    print(f"APPLYING labels to {len(video_less_changed)} changed points (of {len(video_less)} in scope)...")
    print("=" * 60)

    updated = 0
    for diff in video_less_changed:
        client.set_payload(collection_name=collection, payload=diff["delta"], points=[diff["id"]])
        updated += 1
        if updated % 500 == 0:
            print(f"  Progress: {updated}/{len(video_less_changed)} points updated")

    print(f"\nSUCCESS: updated {updated} points. Snapshot for rollback: {snapshot_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
