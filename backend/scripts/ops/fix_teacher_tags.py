#!/usr/bin/env python3
"""Idempotent backfill: recompute teacher tags/ids with the fixed resolver.

Background
----------
`services.teacher_attribution.resolve_teacher_attribution` was, until
2026-09-24, letting a text MENTION of another teacher's name inside a
transcript override the SPEAKER. Live Qdrant audit (2026-09-24) found 3,121
false external-teacher tags across 143 Preethaji/Krishnaji/Ekam/O&O videos:
  - 111 `teacher:iskcon`   (triggered by "digital"/"Krishnaji" substrings)
  - 19  `teacher:sadhguru` (triggered by "Mahishasura" containing "isha")
  - 2,991 `teacher:amma_bhagavan` (triggered by "oneness"/"amma"-in-"grammar"/
    "deeksha"; only 46 of those points even name Amma Bhagavan, and those are
    the teachers themselves talking about him)

This script recomputes every point's `tags`, `teacher_id`, and `teacher_ids`
straight from that point's own payload (title, source_url, speaker, text)
using the fixed, source-only resolver, and reports the diff. It never infers
anything itself -- `resolve_teacher_attribution` is the single source of
truth; this script is a thin apply/report wrapper (Gate 0.1 style, see
`backfill_qdrant_teacher_id.py`, which this follows for style/CLI shape).

Execution Protocol
-------------------
1. Dry-run by default: scrolls the collection, recomputes, prints diff
   counts and 10 example diffs. Zero writes.
2. `--apply`: snapshots the collection first (Qdrant REST
   `POST /collections/{c}/snapshots`), prints the snapshot name, then
   payload-only `set_payload` for just the points whose tags/teacher_id/
   teacher_ids actually changed. Never touches vectors. Idempotent: a
   second run against an already-fixed collection reports zero changes.
"""

from __future__ import annotations

import argparse
import collections
import os
import sys
from typing import Any, Optional


def _recompute(payload: dict[str, Any]) -> tuple[list[str], str, list[str]]:
    """Recompute (tags, teacher_id, teacher_ids) for one point's payload."""
    from services.teacher_attribution import resolve_teacher_attribution

    old_tags = payload.get("tags") or []
    if isinstance(old_tags, str):
        old_tags = [old_tags]

    new_teacher_tags, primary_id, attributed_ids = resolve_teacher_attribution(
        source_url=payload.get("source_url") or "",
        title=payload.get("title") or "",
        speaker=payload.get("speaker") or payload.get("channel_name") or "",
        chunks=[payload.get("text") or ""],
        tags=old_tags,
    )

    # Keep every non-attribution tag as-is; only `teacher:`/`mentions:` values
    # are the resolver's responsibility.
    kept = [t for t in old_tags if not (t.startswith("teacher:") or t.startswith("mentions:"))]
    new_tags = sorted(set(kept) | set(new_teacher_tags))
    return new_tags, primary_id, attributed_ids


EXTERNAL_TEACHER_TAGS = frozenset({"teacher:sadhguru", "teacher:amma_bhagavan", "teacher:iskcon"})


def _diff_point(pt_id: str, payload: dict[str, Any], scope: str = "external-tags") -> dict[str, Any]:
    old_tags = payload.get("tags") or []
    if isinstance(old_tags, str):
        old_tags = [old_tags]
    old_teacher_id = payload.get("teacher_id") or ""
    old_teacher_ids = payload.get("teacher_ids") or []

    new_tags, new_teacher_id, new_teacher_ids = _recompute(payload)
    if scope == "external-tags":
        # Title-only identity scored no better than the current labels against the
        # voice census (2,171 vs 2,149 of 4,801 correct), so leave teacher_id and
        # non-external teacher tags alone until voice attribution can decide them.
        mentions = {t for t in new_tags if t.startswith("mentions:")}
        kept = set(old_tags) - EXTERNAL_TEACHER_TAGS
        # The whole corpus is Sri Preethaji & Sri Krishnaji (owner, 2026-09-24): a point
        # that loses a false external tag is credited to both unless it already names one.
        if EXTERNAL_TEACHER_TAGS & set(old_tags) and not kept & {"teacher:sri_preethaji", "teacher:sri_krishnaji"}:
            kept |= {"teacher:sri_preethaji", "teacher:sri_krishnaji"}
        new_tags = sorted(kept | mentions)
        new_teacher_id, new_teacher_ids = old_teacher_id, old_teacher_ids

    return {
        "id": pt_id,
        "title": payload.get("title") or "",
        "old_tags": sorted(old_tags),
        "new_tags": new_tags,
        "tags_removed": sorted(set(old_tags) - set(new_tags)),
        "tags_added": sorted(set(new_tags) - set(old_tags)),
        "old_teacher_id": old_teacher_id,
        "new_teacher_id": new_teacher_id,
        "old_teacher_ids": sorted(old_teacher_ids),
        "new_teacher_ids": sorted(new_teacher_ids),
        "changed": (
            sorted(old_tags) != new_tags
            or old_teacher_id != new_teacher_id
            or sorted(old_teacher_ids) != sorted(new_teacher_ids)
        ),
    }


def _take_snapshot(qdrant_url: str, collection: str) -> str:
    import requests

    resp = requests.post(f"{qdrant_url}/collections/{collection}/snapshots", timeout=60)
    resp.raise_for_status()
    name = resp.json()["result"]["name"]
    print(f"Snapshot created: {name}")
    return name


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply the fix to Qdrant (default: dry-run only)"
    )
    parser.add_argument(
        "--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333")
    )
    parser.add_argument("--collection", default=None, help="Defaults to settings.qdrant_collection")
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--sample-size", type=int, default=10, help="Example diffs to print")
    parser.add_argument(
        "--scope",
        choices=("external-tags", "full"),
        default="external-tags",
        help="external-tags: drop false teacher:sadhguru/amma_bhagavan/iskcon tags and add "
        "mentions:* only; full: also rewrite teacher_id/teacher_ids from source metadata",
    )
    args = parser.parse_args(argv)

    collection = args.collection
    if not collection:
        from app.config import settings

        collection = settings.qdrant_collection

    from qdrant_client import QdrantClient

    client = QdrantClient(url=args.qdrant_url)
    print(f"{'APPLY' if args.apply else 'DRY-RUN'} — teacher tag fix")
    print(f"  Qdrant URL:  {args.qdrant_url}")
    print(f"  Collection:  {collection}\n")

    total = 0
    changed_points: list[dict[str, Any]] = []
    tags_removed_counter: collections.Counter = collections.Counter()
    tags_added_counter: collections.Counter = collections.Counter()
    transition_matrix: collections.Counter = collections.Counter()

    offset = None
    while True:
        res, next_offset = client.scroll(
            collection_name=collection,
            limit=args.batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not res:
            break

        for pt in res:
            total += 1
            diff = _diff_point(str(pt.id), pt.payload or {}, args.scope)
            transition_matrix[(diff["old_teacher_id"] or "<empty>", diff["new_teacher_id"])] += 1
            for v in diff["tags_removed"]:
                tags_removed_counter[v] += 1
            for v in diff["tags_added"]:
                tags_added_counter[v] += 1
            if diff["changed"]:
                changed_points.append(diff)

        if next_offset is None:
            break
        offset = next_offset

    mentions_added = {
        k: v for k, v in tags_added_counter.items() if k.startswith("mentions:")
    }

    print(f"Scanned {total} points.\n")

    print("=== TAGS REMOVED (by value) ===")
    for tag, count in tags_removed_counter.most_common():
        print(f"  {tag:<28s} {count:>6d}")

    print("\n=== TAGS ADDED (by value) ===")
    for tag, count in tags_added_counter.most_common():
        print(f"  {tag:<28s} {count:>6d}")

    print("\n=== mentions:* ADDED ===")
    for tag, count in sorted(mentions_added.items()):
        print(f"  {tag:<28s} {count:>6d}")

    print("\n=== teacher_id TRANSITION MATRIX (old -> new) ===")
    for (old_id, new_id), count in sorted(transition_matrix.items(), key=lambda x: -x[1]):
        marker = "  (unchanged)" if old_id == new_id else "  <-- CHANGED"
        print(f"  {old_id:<20s} -> {new_id:<20s} {count:>6d}{marker}")

    print(f"\n=== POINTS CHANGED: {len(changed_points)} / {total} ===")

    print(f"\n=== {min(args.sample_size, len(changed_points))} EXAMPLE DIFFS ===")
    for diff in changed_points[: args.sample_size]:
        print(f"\n  id: {diff['id'][:12]}...  title: {diff['title'][:70]!r}")
        print(f"    teacher_id:  {diff['old_teacher_id']!r} -> {diff['new_teacher_id']!r}")
        print(f"    teacher_ids: {diff['old_teacher_ids']} -> {diff['new_teacher_ids']}")
        print(f"    tags removed: {diff['tags_removed']}")
        print(f"    tags added:   {diff['tags_added']}")

    if not args.apply:
        print("\n" + "=" * 60)
        print("DRY-RUN COMPLETE — Zero writes performed.")
        print("Re-run with --apply to write the fix to live Qdrant.")
        print("=" * 60)
        return 0

    print("\n" + "=" * 60)
    snapshot_name = _take_snapshot(args.qdrant_url, collection)
    print(f"APPLYING FIX to {len(changed_points)} changed points (of {total} scanned)...")
    print("=" * 60)

    updated = 0
    for diff in changed_points:
        payload = {"tags": diff["new_tags"]}
        if args.scope == "full":
            payload["teacher_id"] = diff["new_teacher_id"]
            payload["teacher_ids"] = diff["new_teacher_ids"]
        client.set_payload(collection_name=collection, payload=payload, points=[diff["id"]])
        updated += 1
        if updated % 500 == 0:
            print(f"  Progress: {updated}/{len(changed_points)} points updated")

    print(f"\nSUCCESS: updated {updated} points. Snapshot for rollback: {snapshot_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
