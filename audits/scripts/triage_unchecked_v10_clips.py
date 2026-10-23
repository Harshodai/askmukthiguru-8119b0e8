#!/usr/bin/env python3
"""Triage v10 clips that carry no voice-window file (read-only).

Input: a JSONL export of the clips (one object per line) with at least
``video_id``, ``start_ms``, ``end_ms`` and ``text``; ``point_id`` and
``transcript_hash`` are used when present. Export it from ``first_person_v10``
with a read-only scroll; this script never contacts Qdrant, Docker, YouTube or
the network.

Each clip is joined to the Phase 2/4 evidence under ``audits/evidence`` (ECAPA
verdicts computed from ``audio_archive/wavs`` with a pinned model) and gets one
of three outcomes:

* ``verified``       - joined to a span whose ECAPA verdict is ``verified`` and
                       which is in the ``local_review_candidate`` tier
                       (automated evidence, NOT human-certified).
* ``host_uncertain`` - joined to a refused span, or ECAPA-verified but the text
                       reads like a host line. A human must listen.
* ``hold``           - no join, or joined to a tier that is never served.

Nothing is promoted by this script; ``verified`` still means "automated
evidence candidate".

Usage:
    python3 audits/scripts/triage_unchecked_v10_clips.py clips.jsonl \\
        --out triage.jsonl [--evidence-dir audits/evidence]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

TIER_FILES = {
    "local_review_candidate": "public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl",
    "review_required": "public_release_phase4_tier_review_required_2026-10-22.jsonl",
    "variant_candidate": "public_release_phase4_tier_variant_candidate_2026-10-22.jsonl",
    "unlocatable_quarantine": "public_release_phase4_tier_unlocatable_quarantine_2026-10-22.jsonl",
    "deterministic_id_collision_quarantine": "public_release_phase4_tier_deterministic_id_collision_quarantine_2026-10-22.jsonl",
}
VERDICTS_FILE = "public_release_phase2_verdicts_2026-10-22.json"
MIN_IOU = 0.5
# Interviewer cues; deliberately narrow. A hit only downgrades to host_uncertain.
_HOST_CUE = re.compile(
    r"\b(welcome (back )?to|thank you for (joining|coming)|my guest|our guest|"
    r"joining me|please welcome|let'?s (begin|start)|tell us|can you (share|tell)|"
    r"how do (we|you)|what (is|are|do) (you|we)|why (is|do|does))\b",
    re.IGNORECASE,
)


def _iou(a0: int, a1: int, b0: int, b1: int) -> float:
    inter = max(0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    return inter / union if union > 0 else 0.0


def load_evidence(evidence_dir: Path) -> dict[str, list[dict]]:
    verdicts = json.loads((evidence_dir / VERDICTS_FILE).read_text())["verdicts"]
    by_video: dict[str, list[dict]] = collections.defaultdict(list)
    for tier, name in TIER_FILES.items():
        for line in (evidence_dir / name).read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            v = verdicts.get(row["source_span_id"], {})
            hashes = {
                row.get("live_transcript_hash"),
                row.get("live_source_text_hash"),
                row.get("transcript_hash"),
            } - {None, ""}
            by_video[row["video_id"]].append(
                {
                    "tier": tier,
                    "source_span_id": row["source_span_id"],
                    "start": int(row["live_start_ms"]),
                    "end": int(row["live_end_ms"]),
                    "hashes": hashes,
                    "reason_code": v.get("reason_code", "no_verdict"),
                    "cosine": v.get("cosine"),
                    "margin": v.get("margin"),
                }
            )
    return by_video


def classify(clip: dict, spans: list[dict]) -> dict:
    text = (clip.get("text") or "").strip()
    host_cue = text.endswith("?") or bool(_HOST_CUE.search(text))
    # Join on time overlap inside the video. Transcript hashes are NOT used to
    # pick the span (several spans of one video can share a transcript hash);
    # they are only recorded as a cross-check.
    match, method = None, None
    best = max(
        spans,
        key=lambda s: _iou(clip["start_ms"], clip["end_ms"], s["start"], s["end"]),
        default=None,
    )
    if best and _iou(clip["start_ms"], clip["end_ms"], best["start"], best["end"]) >= MIN_IOU:
        match, method = best, "time_overlap"
    h = clip.get("transcript_hash")
    out = {
        "point_id": clip.get("point_id"),
        "video_id": clip["video_id"],
        "start_ms": clip["start_ms"],
        "end_ms": clip["end_ms"],
        "host_cue": host_cue,
        "match_method": method,
        "hash_agrees": bool(match and h and h in match["hashes"]),
    }
    if match is None:
        return {**out, "outcome": "hold", "why": "no Phase 2/4 span covers this clip"}
    out.update(
        tier=match["tier"],
        source_span_id=match["source_span_id"],
        reason_code=match["reason_code"],
        cosine=match["cosine"],
        margin=match["margin"],
    )
    if match["tier"] == "local_review_candidate" and match["reason_code"] == "verified":
        if host_cue:
            return {**out, "outcome": "host_uncertain",
                    "why": "ECAPA verified but text reads like a host line; listen"}
        return {**out, "outcome": "verified", "why": "ECAPA verified, automated evidence only"}
    if match["reason_code"] in ("refused_guru_mismatch", "refused_below_cosine_floor"):
        return {**out, "outcome": "host_uncertain",
                "why": f"ECAPA refused ({match['reason_code']}); listen"}
    return {**out, "outcome": "hold", "why": f"tier {match['tier']} is not served"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Triage v10 clips with no voice-window file")
    ap.add_argument("clips")
    ap.add_argument("--out", required=True)
    ap.add_argument("--evidence-dir", default=str(Path(__file__).resolve().parents[1] / "evidence"))
    args = ap.parse_args(argv)
    by_video = load_evidence(Path(args.evidence_dir))
    clips = [json.loads(line) for line in Path(args.clips).read_text().splitlines() if line.strip()]
    rows = [classify(c, by_video.get(c["video_id"], [])) for c in clips]
    Path(args.out).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    print(dict(collections.Counter(r["outcome"] for r in rows)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
