#!/usr/bin/env python3
"""Idempotent backfill: stamp `provenance` + `provenance_rationale` on all points in Qdrant.

Background
----------
backend/CLAUDE.md's provenance task: retrieval currently treats an LLM-written
RAPTOR summary paragraph as equivalent evidence to the guru's own transcribed
speech. Fixing that at retrieval time needs a payload signal that says what a
chunk actually *is*. `services/provenance.py::classify_chunk_provenance` is
the classifier (same module `ingest/quality_gate.py` uses to reject junk and
third-party content at ingest time going forward); this script applies it to
the existing 12,904 points, which are NOT being re-ingested or re-embedded —
this is a payload-only backfill, same shape as
`backfill_qdrant_teacher_id.py`.

Execution Protocol
-------------------
1. Dry-run by default: scans collection, classifies all points, prints
   distribution and stratified samples. Zero writes occur.
2. Apply: invoked explicitly with `--apply` to update payloads via Qdrant's
   batch `set_payload` API. Safe to re-run — classification is a pure
   function of already-stored payload fields, so re-running reproduces the
   same result (idempotent) rather than accumulating drift.
"""

from __future__ import annotations

import argparse
import collections
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from services.provenance import ChunkProvenance, classify_chunk_provenance  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply the backfill to Qdrant (default: dry-run only)"
    )
    parser.add_argument(
        "--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333")
    )
    parser.add_argument(
        "--collection", default=os.environ.get("QDRANT_COLLECTION", "spiritual_wisdom_contextual")
    )
    parser.add_argument(
        "--sample-size", type=int, default=3, help="Samples to print per bucket (default: 3)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="Batch size for scroll and update (default: 250)",
    )
    args = parser.parse_args(argv)

    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    client = QdrantClient(url=args.qdrant_url)
    print(f"{'APPLY' if args.apply else 'DRY-RUN'} — Qdrant chunk provenance backfill")
    print(f"  Qdrant URL:  {args.qdrant_url}")
    print(f"  Collection:  {args.collection}")
    print()

    offset = None
    total = 0
    buckets: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    update_batches: list[list[tuple[str, str, str]]] = []
    current_batch: list[tuple[str, str, str]] = []

    while True:
        res, next_offset = client.scroll(
            collection_name=args.collection,
            limit=args.batch_size,
            offset=offset,
            with_payload=[
                "raptor_level",
                "content_type",
                "source_type",
                "speaker",
                "channel_name",
                "text",
                "title",
                "source_url",
            ],
            with_vectors=False,
        )
        if not res:
            break

        for pt in res:
            total += 1
            payload = pt.payload or {}
            result = classify_chunk_provenance(
                raptor_level=payload.get("raptor_level"),
                content_type=payload.get("content_type") or "",
                source_type=payload.get("source_type") or "",
                speaker=payload.get("speaker") or "",
                channel_name=payload.get("channel_name") or "",
                text=payload.get("text") or "",
            )
            item = {
                "id": str(pt.id),
                "title": (payload.get("title") or "NO_TITLE")[:70],
                "source_url": payload.get("source_url") or "",
                "provenance": result.provenance.value,
                "rationale": result.rationale,
            }
            buckets[result.provenance.value].append(item)
            current_batch.append((str(pt.id), result.provenance.value, result.rationale))
            if len(current_batch) >= args.batch_size:
                update_batches.append(current_batch)
                current_batch = []

        if next_offset is None:
            break
        offset = next_offset

    if current_batch:
        update_batches.append(current_batch)

    print(f"Scanned {total} points from collection '{args.collection}'.\n")
    print("=== PROVENANCE DISTRIBUTION ===")
    for provenance, items in sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True):
        pct = (len(items) / total) * 100 if total else 0
        print(f"  {provenance:<20s} {len(items):>6d} points ({pct:>5.1f}%)")
    print()

    print("=== STRATIFIED SAMPLES FOR HUMAN REVIEW ===")
    for provenance, items in sorted(buckets.items()):
        print(f"\n--- {provenance} (total: {len(items)}) ---")
        for sample in items[: args.sample_size]:
            print(f"  [id: {sample['id'][:8]}...] {sample['title']}")
            print(
                f"      rationale: {sample['rationale']}  source_url: {sample['source_url'][:80]}"
            )

    if not args.apply:
        print("\n" + "=" * 60)
        print("DRY-RUN COMPLETE — Zero writes performed.")
        print("Review the distribution and samples above, then re-run with --apply.")
        print("=" * 60)
        return 0

    print("\n" + "=" * 60)
    print(f"APPLYING BACKFILL to {total} points...")
    print("=" * 60)

    updated_count = 0
    for batch in update_batches:
        # Group within the batch by (provenance, rationale) so identical
        # payload writes are sent together — same batching shape as
        # backfill_qdrant_teacher_id.py.
        grouped: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
        for pt_id, provenance, rationale in batch:
            grouped[(provenance, rationale)].append(pt_id)
        for (provenance, rationale), pt_ids in grouped.items():
            client.set_payload(
                collection_name=args.collection,
                payload={"provenance": provenance, "provenance_rationale": rationale},
                points=pt_ids,
            )
            updated_count += len(pt_ids)
        print(f"    Progress: {updated_count}/{total} points updated")

    print("\nVerifying backfill integrity...")
    valid_values = [p.value for p in ChunkProvenance]
    missing_count = client.count(
        collection_name=args.collection,
        count_filter=models.Filter(
            must_not=[
                models.FieldCondition(key="provenance", match=models.MatchAny(any=valid_values))
            ]
        ),
        exact=True,
    ).count

    if missing_count == 0:
        print(f"SUCCESS: 100% of {total} points now carry a valid provenance value.")
        return 0
    print(f"WARNING: {missing_count} points still lack a valid provenance value.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
