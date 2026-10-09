#!/usr/bin/env python3
"""Read-only preview: what dropping the severed head sentence would do to clips
that the serve-time ``head_fragment`` check blocks (the "23 cut-off clips").

Scrolls a first-person collection and, for each clip whose boundary defects
include ``head_fragment``, prints the current opening, the proposed text after
``snap_to_sentences`` (shrink-only) and the sha256 the new text would need.
It NEVER writes to Qdrant. Playback start_ms is not adjusted here: the payload
carries no word timings, so a real repair must re-cut from the transcript words.
A repair would also change ``transcript_hash`` (FP invariants 2 and 13), so it
needs the review gate and the owner's OK first.

  .venv/bin/python -m scripts.ops.preview_first_person_head_fragment_repair \
      --collection first_person_v7 [--out report.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

from ingest.verbatim.boundaries import boundary_defects, snap_to_sentences  # noqa: E402


def preview_clip(text: str, min_words: int = 12) -> dict[str, Any] | None:
    """None when the clip has no head_fragment defect; else the proposed shrink."""
    tokens = text.split()
    defects = boundary_defects(tokens)
    if "head_fragment" not in defects:
        return None
    span = snap_to_sentences(tokens, 0, len(tokens), min_words=min_words)
    proposed = " ".join(tokens[span[0] : span[1]]) if span else None
    return {
        "defects": defects,
        "current_head": " ".join(tokens[:8]),
        "proposed_head": " ".join(proposed.split()[:8]) if proposed else None,
        "proposed_text": proposed,
        "proposed_sha256": hashlib.sha256(proposed.encode()).hexdigest() if proposed else None,
        "repairable_by_shrink": proposed is not None,
    }


def _scroll(collection: str):
    from qdrant_client import QdrantClient

    from app.config import settings

    client = QdrantClient(
        url=settings.qdrant_url, api_key=os.getenv("QDRANT_API_KEY") or None, timeout=30
    )
    offset = None
    while True:
        points, offset = client.scroll(
            collection, limit=256, offset=offset, with_payload=True, with_vectors=False
        )
        yield from points
        if offset is None:
            return


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--collection", required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    rows = []
    for p in _scroll(args.collection):
        pl = p.payload or {}
        r = preview_clip(pl.get("verbatim_text", ""))
        if r:
            rows.append(
                {
                    "point_id": str(p.id),
                    "video_id": pl.get("video_id"),
                    "speaker": pl.get("speaker"),
                    **r,
                }
            )
    report = {
        "collection": args.collection,
        "writes": 0,
        "head_fragment_clips": len(rows),
        "repairable_by_shrink": sum(r["repairable_by_shrink"] for r in rows),
        "clips": rows,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text)
    print(
        f"{args.collection}: {report['head_fragment_clips']} head_fragment clips, "
        f"{report['repairable_by_shrink']} repairable by shrink, 0 writes"
        + (f" -> {args.out}" if args.out else "")
    )
    if not args.out:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
