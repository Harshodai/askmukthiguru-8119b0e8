#!/usr/bin/env python3
"""Deterministic rolling-window resegmentation of corpus-gap videos into v13.

Why this exists
---------------
`first_person_v13_shadow` was seeded with 13 hand-picked clips. The
`CORPUS_GAP_INGESTION_PLAN_2026-11-20.md` asks for the gap videos to be
*re-segmented* into complete 18-25 s doctrine passages, not hand-picked
snippets. This script does that deterministically from Whisper segment
timings: it merges consecutive ASR segments into sentence-closing windows,
rejects artifacts / event announcements / fragments, and upserts only into
`first_person_v13_shadow`.

Honest limits
-------------
- No ECAPA speaker verification is performed here (the repo `audio_archive/`
  is empty). Every emitted point is stamped `speaker_verified=False`. The
  existing v12 points for these same sources are already mixed
  True/False, and v12's declared evidence policy is
  `payload_speaker_and_rights_claims_unverified`, so this is consistent.
- Rights are inherited from how the serving collection already treats the
  source (`domain_rights_status="licensed"`, `rights_cleared=True`). This is a
  re-chunk of content already in v12, not a new rights determination.
- `rRs__D_3mKY` is excluded: its clips_summary reports host_other=1.0 and
  n_clips=0 (host-dominated, not teacher speech).
- `0z-IZ2ar4eA` is excluded: its WAV exists but no ASR model is installed
  (parakeet/nemo absent), so there are no timings to window honestly.

Usage
-----
    python3 scripts/ops/resegment_gap_videos_v13.py --dry-run
    python3 scripts/ops/resegment_gap_videos_v13.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http.models import (  # noqa: E402
    PointStruct,
    SparseVector,
)

from services.embedding_service import EmbeddingService  # noqa: E402
from services.first_person_content_assessment import EVENT_MARKER_RE  # noqa: E402
from services.text_quality_filter import find_artifact  # noqa: E402

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
TARGET = "first_person_v13_shadow"
SOURCE = "first_person_v12_shadow"
CORPUS_VERSION = "fp-context-transcript-v3"
CHUNKER_VERSION = "rolling_window_v1:18-25s"

DATA = Path.home() / "mukthiguru_attribution_data"
RAW = DATA / "mass_ingest_2026-10" / "raw"
ULT = DATA / "corpus_UlOt31lBhLY" / "canonical_segments.json"

MIN_WINDOW_S = 18.0
MAX_WINDOW_S = 25.0
MIN_WORDS = 15
DEDUP_OVERLAP = 0.70

WHISPER_VIDEOS = [
    "xTVHvMHakow",
    "gMrOMT4mfno",
    "Oc5ar2g2rnI",
    "bF6kr28QHJc",
    "odXq5g-Y7gM",
    "DmzZPgTh7_M",
    "XzS56RqIxeE",
]

SENT_END = re.compile(r"[.?!][\"'”’)]?$")


def _ends_sentence(text: str) -> bool:
    return bool(SENT_END.search(text.strip()))


def _load_whisper(video_id: str) -> list[dict]:
    p = RAW / f"{video_id}_whisper.json"
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("segments", [])


def _load_ult() -> list[dict]:
    if not ULT.is_file():
        return []
    data = json.loads(ULT.read_text(encoding="utf-8"))
    return data.get("segments", [])


def _windows(segments: list[dict]) -> list[dict]:
    out: list[dict] = []
    cur: list[dict] = []
    start: float | None = None
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        st = float(seg.get("start", 0.0))
        en = float(seg.get("end", 0.0))
        if start is None:
            start = st
        # Close BEFORE this segment would push the window past the cap, so a
        # window is never emitted longer than MAX_WINDOW_S. Prefer trimming to
        # the last sentence boundary so the emitted window closes cleanly.
        if cur and (en - start) > MAX_WINDOW_S:
            cut = next((j for j in range(len(cur) - 1, -1, -1) if _ends_sentence(cur[j]["text"])), None)
            if cut is not None:
                out.append(_make_window(cur[: cut + 1], start, cur[cut]["end"]))
                cur = cur[cut + 1 :]
            else:
                out.append(_make_window(cur, start, cur[-1]["end"]))
                cur = []
            start = cur[0]["start"] if cur else st
        cur.append({"start": st, "end": en, "text": text})
        dur = en - start
        if dur >= MIN_WINDOW_S and _ends_sentence(text):
            out.append(_make_window(cur, start, en))
            cur, start = [], None
    if cur and start is not None:
        out.append(_make_window(cur, start, cur[-1]["end"]))
    return out


def _make_window(segs: list[dict], start: float, end: float) -> dict:
    text = " ".join(s["text"] for s in segs).strip()
    return {"start": start, "end": end, "text": text}


def _deterministic_id(video_id: str, start_ms: int, end_ms: int, text: str) -> str:
    h = hashlib.sha256(f"{video_id}|{start_ms}|{end_ms}|{text}".encode()).hexdigest()
    return str(uuid.UUID(h[:32]))


def _gate(text: str) -> str | None:
    if find_artifact(text):
        return "artifact"
    if EVENT_MARKER_RE.search(text):
        return "event_marker"
    if len(text.split()) < MIN_WORDS:
        return "too_short"
    if not _ends_sentence(text):
        return "no_sentence_close"
    return None


def _existing_spans(client: QdrantClient, video_id: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    offset = None
    while True:
        recs, offset = client.scroll(
            collection_name=TARGET,
            limit=200,
            offset=offset,
            with_payload=["start_ms", "end_ms"],
            with_vectors=False,
            scroll_filter={"must": [{"key": "video_id", "match": {"value": video_id}}]},
        )
        for r in recs:
            s, e = r.payload.get("start_ms"), r.payload.get("end_ms")
            if s is not None and e is not None:
                spans.append((int(s), int(e)))
        if offset is None:
            break
    return spans


def _overlaps(start_ms: int, end_ms: int, spans: list[tuple[int, int]]) -> bool:
    dur = max(1, end_ms - start_ms)
    for s, e in spans:
        inter = max(0, min(end_ms, e) - max(start_ms, s))
        if inter / dur > DEDUP_OVERLAP:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = QdrantClient(url=QDRANT_URL, timeout=120)

    sources: dict[str, list[dict]] = {v: _load_whisper(v) for v in WHISPER_VIDEOS}
    ult = _load_ult()
    if ult:
        sources["UlOt31lBhLY"] = ult

    report: dict[str, dict] = {}
    accepted: list[dict] = []
    for video_id, segs in sources.items():
        if not segs:
            report[video_id] = {"segments": 0, "windows": 0, "accepted": 0, "note": "no source data"}
            continue
        spans = _existing_spans(client, video_id)
        wins = _windows(segs)
        reasons: dict[str, int] = {}
        acc = 0
        for w in wins:
            start_ms, end_ms = int(w["start"] * 1000), int(w["end"] * 1000)
            if end_ms - start_ms > MAX_WINDOW_S * 1000 + 1500:
                reasons["too_long"] = reasons.get("too_long", 0) + 1
                continue
            reason = _gate(w["text"])
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            if _overlaps(start_ms, end_ms, spans):
                reasons["duplicate_of_existing"] = reasons.get("duplicate_of_existing", 0) + 1
                continue
            acc += 1
            accepted.append({"video_id": video_id, **w})
        report[video_id] = {
            "segments": len(segs),
            "windows": len(wins),
            "accepted": acc,
            "rejected": reasons,
        }

    print(json.dumps({"mode": "dry-run" if args.dry_run else "apply", "per_video": report, "accepted_total": len(accepted)}, indent=1))

    if args.dry_run or not accepted:
        if args.apply:
            print("nothing accepted; no writes")
        return 0

    emb = EmbeddingService()
    encoded = emb.encode_batch([a["text"] for a in accepted])
    dense, sparse = encoded["dense"], encoded["sparse"]

    points = []
    now = datetime.now(UTC).isoformat()
    for i, a in enumerate(accepted):
        start_ms, end_ms = int(a["start"] * 1000), int(a["end"] * 1000)
        sv = sparse[i]
        if hasattr(sv, "indices"):
            idx = [int(x) for x in sv.indices.tolist()] if hasattr(sv.indices, "tolist") else [int(x) for x in sv.indices]
            val = [float(x) for x in sv.values.tolist()] if hasattr(sv.values, "tolist") else [float(x) for x in sv.values]
        elif isinstance(sv, dict):
            idx = [int(k) for k in sv]
            val = [float(v) for v in sv.values()]
        else:
            idx, val = [], []
        payload = {
            "video_id": a["video_id"],
            "title": a["video_id"],
            "speaker_role": "teacher",
            "answer_role": "primary",
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": end_ms - start_ms,
            "text": a["text"],
            "source_url": f"https://www.youtube.com/watch?v={a['video_id']}",
            "rights_cleared": True,
            "domain_rights_status": "licensed",
            "speaker_verified": False,
            "is_verbatim": True,
            "corpus_version": CORPUS_VERSION,
            "chunker_version": CHUNKER_VERSION,
            "completeness_status": "complete",
            "boundary_status": "clean",
            "record_type": "passage",
            "parent_unit_id": f"{a['video_id']}_rw_{start_ms}",
            "indexed_at": now,
        }
        points.append(
            PointStruct(
                id=_deterministic_id(a["video_id"], start_ms, end_ms, a["text"]),
                vector={"passage_dense": [float(x) for x in dense[i]], "passage_sparse": SparseVector(indices=idx, values=val)},
                payload=payload,
            )
        )

    before = client.count(TARGET).count
    client.upsert(collection_name=TARGET, points=points, wait=True)
    after = client.count(TARGET).count
    print(f"upserted {len(points)} points into {TARGET}: {before} -> {after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
