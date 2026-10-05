#!/usr/bin/env python3
"""
scripts/ingestion/repair_v7_clips.py — V7 Corpus Surgery

# ponytail: V7 corpus surgery — repair/drop defective clips without LLM
Repairs defective clips using snap_to_sentences, or drops unsalvageable fragments.
Guarantees 100% boundary-clean clips in first_person_v7.

AUDIT CAVEAT (2026-09-29): payload surgery is the LAST resort — prefer a full
`build_first_person_index --apply` rebuild, which re-embeds and re-validates.
This script (a) recomputes transcript_hash after any text change (binding rule,
lessons.md L-INTEGRITY-HASH-MISMATCH-1), (b) never re-embeds passage_dense, so
every repaired point carries vector/text drift until a rebuild, and (c) deletes
points with no backup (collection is RF=1) — dropped IDs are printed for audit.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

# Path setup
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from qdrant_client import QdrantClient
from ingest.verbatim.boundaries import boundary_defects, snap_to_sentences

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = "first_person_v7"


def scroll_all_points(client: QdrantClient, collection: str) -> list:
    all_points = []
    offset = None
    while True:
        pts, offset = client.scroll(
            collection,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(pts)
        if offset is None:
            break
    return all_points


def main():
    print(f"Connecting to Qdrant at {QDRANT_URL}...")
    client = QdrantClient(url=QDRANT_URL, timeout=30)

    points = scroll_all_points(client, COLLECTION)
    total_before = len(points)
    print(f"Total clips before surgery: {total_before}")

    clean_untouched = 0
    repaired_count = 0
    dropped_count = 0
    points_to_delete = []

    for p in points:
        pl = p.payload or {}
        vt = pl.get("verbatim_text", "")
        defs = boundary_defects(vt.split())
        if not defs:
            clean_untouched += 1
            continue

        # Defective clip: attempt sentence snapping
        toks = vt.split()
        snapped = snap_to_sentences(toks, 0, len(toks), min_words=6)

        if snapped is not None:
            new_toks = toks[snapped[0] : snapped[1]]
            new_defs = boundary_defects(new_toks)
            if not new_defs:
                new_text = " ".join(new_toks)
                # Update payload in Qdrant
                # Binding invariant: recompute transcript_hash BEFORE writing any
                # text change, else the serve-time hash gate quarantines the clip.
                pl["verbatim_text"] = new_text
                pl["transcript_hash"] = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
                # set_payload never touches vectors: passage_dense still embeds the
                # pre-repair text (silent ranking drift). Surface it, never hide it.
                print(
                    f"  WARN {p.id}: text changed, hash recomputed, "
                    f"passage_dense NOT re-embedded (rebuild to restore parity)"
                )
                # Also ensure display_text is clean
                dt = pl.get("display_text", "")
                if dt:
                    dt_toks = dt.split()
                    dt_snapped = snap_to_sentences(dt_toks, 0, len(dt_toks), min_words=6)
                    if dt_snapped is not None:
                        pl["display_text"] = " ".join(dt_toks[dt_snapped[0] : dt_snapped[1]])
                    else:
                        pl["display_text"] = new_text
                else:
                    pl["display_text"] = new_text

                client.set_payload(
                    collection_name=COLLECTION,
                    payload=pl,
                    points=[p.id],
                )
                repaired_count += 1
                continue

        # Cannot be repaired cleanly: mark for deletion
        points_to_delete.append(p.id)
        dropped_count += 1

    if points_to_delete:
        print(f"Dropping {len(points_to_delete)} unsalvageable defective clips (no backup, RF=1):")
        for pid in points_to_delete:
            print(f"  DROP {pid}")
        client.delete(
            collection_name=COLLECTION,
            points_selector=points_to_delete,
        )

    # Re-audit collection
    remaining_points = scroll_all_points(client, COLLECTION)
    total_after = len(remaining_points)

    final_defects = []
    for p in remaining_points:
        pl = p.payload or {}
        vt = pl.get("verbatim_text", "")
        d = boundary_defects(vt.split())
        if d:
            final_defects.append((p.id, d, vt[:50]))

    print("\n" + "=" * 60)
    print("V7 CORPUS SURGERY AUDIT REPORT")
    print("=" * 60)
    print(f"Total clips before: {total_before}")
    print(f"Clean untouched:    {clean_untouched}")
    print(f"Repaired cleanly:   {repaired_count}")
    print(f"Dropped:            {dropped_count}")
    print(f"Total clips after:  {total_after}")
    print(f"Defects remaining:  {len(final_defects)}")
    clean_pct = ((total_after - len(final_defects)) / total_after * 100) if total_after else 0
    print(f"Pristine clip rate: {clean_pct:.1f}%")
    print("=" * 60)

    if final_defects:
        print(f"WARNING: {len(final_defects)} defects remain:")
        for pid, d, snippet in final_defects:
            print(f"  {pid}: {d} => {snippet}")
        sys.exit(1)
    else:
        print("SUCCESS: 100.0% of clips in first_person_v7 are PRISTINE.")


if __name__ == "__main__":
    main()
