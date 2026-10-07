#!/usr/bin/env python3
"""Read-only boundary audit of first-person clips (plan rev 2, card B5).

Replaces scripts/ops/audit_first_person_v5.py, whose defect regexes were
copied from the clips it scored (circular) and whose output went to /tmp.
This audit uses only ingest.verbatim.boundaries.boundary_defects -- generic
rules, so rates are comparable across collections and builders.

Sources (pick one; nothing is ever written to Qdrant):
  --collection first_person_v5          scroll a live Qdrant collection
  --passages-dir <dir> [--passages-dir]  passages_B / passages_C JSON files

  .venv/bin/python -m scripts.ops.audit_first_person_boundaries --collection first_person_v5
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

from ingest.verbatim.boundaries import boundary_defects  # noqa: E402

_REPO = Path(__file__).resolve().parents[3]
# Buckets follow CLAUDE.md FP invariant 11 (18-25 s target).
_DURATION_BUCKETS = ((18.0, "<18s"), (25.0, "18-25s"), (45.0, "25-45s"), (float("inf"), ">45s"))


def _bucket(duration_s: float) -> str:
    return next(label for limit, label in _DURATION_BUCKETS if duration_s < limit)


def summarize(clips: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """clips: dicts with verbatim_text, duration_s, speaker, video_id."""
    rows = [{**c, "defects": boundary_defects(c["verbatim_text"].split())} for c in clips]
    n = len(rows)
    clean = sum(1 for r in rows if not r["defects"])
    return {
        "clips": n,
        "clean": clean,
        "clean_pct": round(100 * clean / n, 2) if n else 0.0,
        "head_defect_clips": sum(any(d.startswith("head_") for d in r["defects"]) for r in rows),
        "tail_defect_clips": sum(any(d.startswith("tail_") for d in r["defects"]) for r in rows),
        "defect_counts": dict(collections.Counter(d for r in rows for d in r["defects"])),
        "duration_buckets": dict(collections.Counter(_bucket(r["duration_s"]) for r in rows)),
        "speakers": dict(collections.Counter(r["speaker"] for r in rows)),
        "defective_examples": [
            {
                "video_id": r["video_id"],
                "speaker": r["speaker"],
                "duration_s": round(r["duration_s"], 2),
                "defects": r["defects"],
                "head": " ".join(r["verbatim_text"].split()[:8]),
                "tail": " ".join(r["verbatim_text"].split()[-6:]),
            }
            for r in rows
            if r["defects"]
        ][:25],
    }


def _from_collection(name: str) -> list[dict[str, Any]]:
    from qdrant_client import QdrantClient

    from app.config import settings

    client = QdrantClient(
        url=settings.qdrant_url, api_key=os.getenv("QDRANT_API_KEY") or None, timeout=30
    )
    out: list[dict[str, Any]] = []
    offset = None
    while True:
        points, offset = client.scroll(
            name, limit=256, offset=offset, with_payload=True, with_vectors=False
        )
        for p in points:
            pl = p.payload or {}
            out.append(
                {
                    "video_id": pl.get("video_id", ""),
                    "speaker": pl.get("speaker", ""),
                    "verbatim_text": pl.get("verbatim_text", ""),
                    "duration_s": (pl.get("end_ms", 0) - pl.get("start_ms", 0)) / 1000.0,
                }
            )
        if offset is None:
            return out


def _from_passages(dirs: list[Path], min_duration_s: float) -> list[dict[str, Any]]:
    out = []
    for d in dirs:
        for f in sorted(d.glob("*.json")):
            data = json.loads(f.read_text())
            for c in data["clips"] if isinstance(data, dict) else data:
                dur = c["end"] - c["start"]
                if dur >= min_duration_s:
                    out.append(
                        {
                            "video_id": c.get("video_id", f.stem),
                            "speaker": c.get("speaker", ""),
                            "verbatim_text": c.get("verbatim_text", ""),
                            "duration_s": dur,
                        }
                    )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--collection")
    src.add_argument("--passages-dir", type=Path, action="append", dest="passages_dirs")
    ap.add_argument(
        "--min-duration-s", type=float, default=8.0, help="passages only; v5 build floor was 8.0"
    )
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.collection:
        clips, source = _from_collection(args.collection), args.collection
    else:
        clips = _from_passages(args.passages_dirs, args.min_duration_s)
        source = "__".join(f"{d.parent.name}_{d.name}" for d in args.passages_dirs)
    report = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "source": source,
        "detector": "ingest.verbatim.boundaries.boundary_defects",
        "summary": summarize(clips),
    }
    out = (
        args.out
        or _REPO
        / "docs"
        / "evidence"
        / f"first_person_boundaries_{source}_{dt.date.today().isoformat()}.json"
    )
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    s = report["summary"]
    print(
        f"{source}: {s['clips']} clips, clean {s['clean']} ({s['clean_pct']}%), "
        f"head {s['head_defect_clips']}, tail {s['tail_defect_clips']} -> {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
