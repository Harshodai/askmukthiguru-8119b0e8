#!/usr/bin/env python3
"""Score first_person_v10 children that carry no voice-verification method.

**Read-only.** Never writes to Qdrant and never sets ``speaker_verified``. For
every ``retrieval_child`` whose ``voice_verification_method`` is empty it asks
the repo's per-window verifier (``ingest.verbatim.speaker_verify``) whether the
saved diarization windows (``<video_id>_speaker.json``) confirm the labelled
teacher, and emits one JSONL row plus a summary:

* ``window_pass``     windows cover the span, none is host/other-teacher, and a
                      strict majority is the labelled teacher;
* ``window_fail``     windows exist and contradict or fail to confirm the label;
* ``no_diarization``  no usable window file: no acoustic evidence either way.

This is a weaker cue than ``batch_speaker_recheck.py`` (no centroid verdict, and
``?`` windows are neutral). A pass is supporting evidence, never grounds to set
``speaker_verified``; absence of evidence is never converted into evidence.
Any backfill is a separate Qdrant write: dry-run, snapshot, ask, apply.

Usage:
    python -m scripts.ops.score_v10_unchecked_speakers \\
        --qdrant-url http://localhost:6333 --speaker-dir <raw dir> \\
        --out report.jsonl --summary summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from ingest.verbatim.speaker_verify import verify_clip_speaker  # noqa: E402

_TEACHER_CODES = {
    "sri preethaji": "preethaji",
    "sri krishnaji": "krishnaji",
    "preethaji": "preethaji",
    "krishnaji": "krishnaji",
}


def classify_child(payload: dict[str, Any], speaker_result: dict[str, Any] | None) -> str:
    """Return ``window_pass``, ``window_fail`` or ``no_diarization`` for one child."""
    if not isinstance(speaker_result, dict) or speaker_result.get("ok") is not True:
        return "no_diarization"
    code = _TEACHER_CODES.get(str(payload.get("speaker_id") or "").strip().casefold())
    if code is None:
        return "window_fail"
    clip = {
        "speaker": code,
        "start": payload["start_ms"] / 1000.0,
        "end": payload["end_ms"] / 1000.0,
    }
    return "window_pass" if verify_clip_speaker(clip, speaker_result) else "window_fail"


def _load_speaker(speaker_dir: Path, video_id: str, cache: dict[str, Any]) -> dict[str, Any] | None:
    if video_id not in cache:
        path = speaker_dir / f"{video_id}_speaker.json"
        cache[video_id] = json.loads(path.read_text()) if path.is_file() else None
    return cache[video_id]


def score(payloads: Iterable[dict[str, Any]], speaker_dir: Path) -> tuple[list[dict], dict]:
    cache: dict[str, Any] = {}
    rows: list[dict] = []
    for p in payloads:
        if p.get("record_type") != "retrieval_child" or p.get("voice_verification_method"):
            continue
        verdict = classify_child(p, _load_speaker(speaker_dir, p["video_id"], cache))
        text = (p.get("verbatim_text") or "").strip()
        rows.append(
            {
                "source_span_id": p.get("source_span_id"),
                "video_id": p["video_id"],
                "start_ms": p["start_ms"],
                "end_ms": p["end_ms"],
                "speaker_id": p.get("speaker_id"),
                "verdict": verdict,
                "ends_in_question": text.endswith("?"),
            }
        )
    summary = {
        "unchecked_children": len(rows),
        "verdicts": dict(Counter(r["verdict"] for r in rows)),
        "no_diarization_ending_in_question": sum(
            r["verdict"] == "no_diarization" and r["ends_in_question"] for r in rows
        ),
    }
    return rows, summary


def _scroll(url: str, collection: str) -> Iterable[dict[str, Any]]:
    offset = None
    while True:
        body: dict[str, Any] = {"limit": 512, "with_payload": True, "with_vector": False}
        if offset:
            body["offset"] = offset
        req = urllib.request.Request(
            f"{url}/collections/{collection}/points/scroll",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
        )
        result = json.load(urllib.request.urlopen(req, timeout=30))["result"]
        for point in result["points"]:
            yield point["payload"]
        offset = result.get("next_page_offset")
        if not offset:
            return


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    ap.add_argument("--collection", default="first_person_v10")
    ap.add_argument("--speaker-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--summary", required=True, type=Path)
    args = ap.parse_args()
    rows, summary = score(_scroll(args.qdrant_url, args.collection), args.speaker_dir)
    args.out.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
