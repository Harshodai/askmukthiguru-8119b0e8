#!/usr/bin/env python3
"""Writer for the `first_person_v1` Qdrant collection — the missing piece of
the first-person verbatim route (see backend/CLAUDE.md's "#1 priority" and
services/first_person_store.py).

Reads speaker-labelled clip files (produced by an external pipeline's
run_clips.make_clip — see the WD/passages_B/<video_id>.json schema) plus the
matching verbatim word-level transcript (WD/transcripts_B/<video_id>.json) and
video durations (videos_final.json), and turns them into FirstPersonStore
points. Fail-closed: any hard-gate failure quarantines the WHOLE video, never
just the offending clip.

Usage
-----
    .venv/bin/python -m scripts.ops.build_first_person_index \\
        --passages-dir ~/mukthiguru_attribution_data/bakeoff_2026-09-25/passages_B \\
        --passages-dir ~/mukthiguru_attribution_data/pilot50_2026-09-25/passages_B \\
        --videos-json ~/mukthiguru_attribution_data/pilot50_2026-09-25/videos_final.json

Dry-run by default (no embedding, no Qdrant write). Pass --apply to write.
`--passages-dir` is repeatable, in priority order: the FIRST dir containing a
given video_id wins.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import settings  # noqa: E402

logger = logging.getLogger(__name__)

# Rights-cleared channel names — see CONTENT-RIGHTS.md (repo root) "Registered
# Content" table. Only channels with an owner-confirmed rights basis belong
# here; never guess. Compared case-insensitively.
CLEARED_CHANNELS = {
    "sri preethaji & sri krishnaji",
    "ekam",
    "o&o academy",
    "times now",
}

# clip["speaker"] -> (teacher_id, display speaker label)
_TEACHER_LABELS = {
    "preethaji": "Sri Preethaji",
    "krishnaji": "Sri Krishnaji",
}

_BATCH_SIZE = 64

# Whisper-vs-Parakeet word agreement below this means the transcript may hold words
# never spoken (pilot: AK435vKMtlo 0.064). Bake-off videos span 0.855-0.941, so 0.80
# only cuts outliers. Provisional -- the owner can move it.
MIN_ASR_AGREEMENT = 0.80


def asr_agreement(passages_path: Path, video_id: str) -> Optional[float]:
    """Word agreement from the pipeline's raw/<id>_vote.json, or None if absent/unreadable."""
    vote = passages_path.parent.parent / "raw" / f"{video_id}_vote.json"
    try:
        value = json.loads(vote.read_text()).get("agreement_rate")
    except (OSError, ValueError):
        return None
    return float(value) if isinstance(value, (int, float)) else None


@dataclass
class VideoGateResult:
    video_id: str
    ok: bool
    reason: Optional[str] = None
    clips: list[dict] = field(default_factory=list)
    host_skipped: int = 0


def load_clips(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def load_transcript(path: Path) -> Optional[list[dict]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def load_video_durations(videos_json: Path) -> dict[str, Optional[float]]:
    data = json.loads(Path(videos_json).read_text())
    return {v["video_id"]: v.get("duration_s") for v in data.get("videos", [])}


def discover_videos(passages_dirs: list[Path]) -> dict[str, Path]:
    """First dir containing a given video_id wins (priority order)."""
    found: dict[str, Path] = {}
    for d in passages_dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            video_id = f.stem
            if video_id not in found:
                found[video_id] = f
    return found


def _gate_clip(clip: dict, full_text: str, duration_s: float) -> Optional[str]:
    """Return a failure reason, or None if the clip clears every hard gate."""
    vt = clip.get("verbatim_text") or ""
    if not vt or vt not in full_text:
        return "substring_mismatch"
    if hashlib.sha256(vt.encode()).hexdigest() != clip.get("transcript_hash"):
        return "hash_mismatch"
    start, end = clip.get("start"), clip.get("end")
    if start is None or end is None or not (0 <= start < end <= duration_s + 1.0):
        return "bad_bounds"
    return None


def gate_video(
    video_id: str,
    clips: list[dict],
    transcript_words: Optional[list[dict]],
    duration_s: Optional[float],
) -> VideoGateResult:
    if transcript_words is None:
        return VideoGateResult(video_id, ok=False, reason="transcript_missing")
    if duration_s is None:
        return VideoGateResult(video_id, ok=False, reason="duration_unknown")

    full_text = " ".join(w["w"] for w in transcript_words)
    host_skipped = 0
    teacher_clips: list[dict] = []
    for clip in clips:
        speaker = clip.get("speaker")
        if speaker not in _TEACHER_LABELS:
            host_skipped += 1
            continue
        reason = _gate_clip(clip, full_text, duration_s)
        if reason:
            return VideoGateResult(video_id, ok=False, reason=reason, host_skipped=host_skipped)
        teacher_clips.append(clip)

    return VideoGateResult(video_id, ok=True, clips=teacher_clips, host_skipped=host_skipped)


def build_store_clip(
    clip: dict,
    video_id: str,
    channel: str,
    rights_cleared: bool,
    layer_sha256: str,
    duration_ms: int,
) -> dict:
    """Map a passages_B clip dict onto FirstPersonStore's clip schema.

    `first_person_eligible` is a data-quality gate only (did it pass our
    substring/hash/bounds checks?), never a rights gate — every clip that
    reaches this function already cleared those, so it is always True here.
    Rights enforcement is `rights_cleared`, persisted separately and filtered
    at serve time (`search_hybrid`, gated on `settings.first_person_serve_unregistered`)
    so the owner's decision to serve unregistered-channel clips for a local
    eval isn't permanently hidden by this indexer.
    """
    teacher_id = clip["speaker"]
    start_ms = round(clip["start"] * 1000)
    end_ms = round(clip["end"] * 1000)
    verbatim_text = clip["verbatim_text"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    return {
        "video_id": video_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker": _TEACHER_LABELS[teacher_id],
        "teacher_id": teacher_id,
        "teacher_ids": [teacher_id],
        "transcript_hash": clip["transcript_hash"],
        "verbatim_text": verbatim_text,
        "display_text": clip.get("display_text") or verbatim_text,
        "parent_id": clip.get("parent_id"),
        "group_id": clip.get("parent_id"),
        "question_text": clip.get("question_context") or "",
        "video_url": video_url,
        "source_url": video_url,
        "duration_ms": duration_ms,
        "layer_sha256": layer_sha256,
        "provenance_kind": "speech_turn_clip",
        "channel": channel,
        "rights_cleared": rights_cleared,
        "first_person_eligible": True,
    }


def lookup_channel_metadata(video_id: str) -> tuple[str, Optional[float]]:
    """Single yt-dlp metadata-only lookup: channel name + duration (seconds).

    Never downloads. Returns ("UNKNOWN", None) on any failure so a network
    hiccup degrades to an uncleared-channel / unknown-duration video, never a
    crash.
    """
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--skip-download",
                "--print",
                "%(channel)s|%(channel_id)s|%(duration)s",
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("|")
            channel = (parts[0].strip() if parts else "") or "UNKNOWN"
            duration_s = None
            if len(parts) > 2:
                try:
                    duration_s = float(parts[2].strip())
                except (ValueError, TypeError):
                    duration_s = None
            return channel, duration_s
    except Exception as exc:
        logger.warning(f"[first_person_index] yt-dlp metadata lookup failed for {video_id}: {exc}")
    return "UNKNOWN", None


def _load_channels_cache(cache_path: Path) -> dict[str, dict]:
    """Load the channel/duration cache. Tolerates the old plain-string format
    (channel only, no duration) by normalizing it to duration_s=None, which
    naturally triggers a re-query per get_channel_and_duration_cached below.
    """
    if not cache_path.exists():
        return {}
    try:
        raw = json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    cache: dict[str, dict] = {}
    for video_id, value in raw.items():
        if isinstance(value, dict):
            cache[video_id] = value
        else:
            cache[video_id] = {"channel": value, "duration_s": None}
    return cache


def get_channel_and_duration_cached(
    video_id: str, cache: dict[str, dict], cache_path: Path
) -> tuple[str, Optional[float]]:
    """Cached channel + duration lookup. Re-queries any entry cached without a
    duration (a prior lookup may have failed, or predate this field existing).
    """
    entry = cache.get(video_id)
    if entry is not None and entry.get("duration_s") is not None:
        return entry["channel"], entry["duration_s"]

    channel, duration_s = lookup_channel_metadata(video_id)
    cache[video_id] = {"channel": channel, "duration_s": duration_s}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True))
    return channel, duration_s


def apply_indexable_clips(indexable_clips: list[dict], collection: str) -> int:
    """Embed + upsert into Qdrant. Only imported/run when --apply is passed."""
    from services.embedding_service import EmbeddingService
    from services.first_person_store import FirstPersonStore
    from services.qdrant.utils import QdrantUtils

    embedder = EmbeddingService()
    store = FirstPersonStore(collection=collection)
    store.init_collection()

    for i in range(0, len(indexable_clips), _BATCH_SIZE):
        batch = indexable_clips[i : i + _BATCH_SIZE]
        embeddings = embedder.encode_batch([c["verbatim_text"] for c in batch])
        sparse_vectors = []
        for sparse_dict in embeddings["sparse"]:
            sv = QdrantUtils.sparse_dict_to_vector(sparse_dict)
            sparse_vectors.append({"indices": sv.indices, "values": sv.values})
        store.upsert_clips(batch, embeddings["dense"], None, sparse_vectors)

    # Mirror this build exactly: drop points of any video that is no longer indexable
    # (e.g. quarantined since an earlier apply), so it can never be served again.
    from qdrant_client.http.models import FieldCondition, Filter, FilterSelector, MatchAny

    keep = sorted({c["video_id"] for c in indexable_clips})
    store.client.delete(
        collection_name=collection,
        points_selector=FilterSelector(filter=Filter(must_not=[FieldCondition(key="video_id", match=MatchAny(any=keep))])),
        wait=True,
    )
    return store.count()


def build_index(
    passages_dirs: list[Path],
    videos_json: Path,
    report_dir: Path,
    collection: str,
    apply: bool = False,
) -> dict[str, Any]:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    durations = load_video_durations(videos_json)
    discovered = discover_videos(passages_dirs)

    channels_cache_path = report_dir / "channels.json"
    channels_cache = _load_channels_cache(channels_cache_path)

    quarantined: list[dict[str, str]] = []
    host_skipped_total = 0
    indexable_clips: list[dict] = []
    clips_per_teacher: Counter = Counter()
    channel_video_counts: Counter = Counter()
    channel_rights: dict[str, bool] = {}
    duration_sources: dict[str, str] = {}

    for video_id, passages_path in discovered.items():
        clips = load_clips(passages_path)
        transcripts_path = passages_path.parent.parent / "transcripts_B" / passages_path.name
        transcript_words = load_transcript(transcripts_path)

        if transcript_words is None:
            quarantined.append({"video_id": video_id, "reason": "transcript_missing"})
            continue

        agreement = asr_agreement(passages_path, video_id)
        if agreement is None:
            quarantined.append({"video_id": video_id, "reason": "asr_agreement_unknown"})
            continue
        if agreement < MIN_ASR_AGREEMENT:
            quarantined.append({"video_id": video_id, "reason": f"asr_agreement_low:{agreement:.3f}"})
            continue

        # Duration precedence: videos_final.json first (cheap, no network); if
        # that's null, fall back to a cached yt-dlp lookup (which also yields
        # the channel, needed later regardless — one combined call).
        duration_s = durations.get(video_id)
        duration_source = "videos_final"
        channel: Optional[str] = None
        if duration_s is None:
            channel, yt_duration_s = get_channel_and_duration_cached(video_id, channels_cache, channels_cache_path)
            if yt_duration_s is not None:
                duration_s = yt_duration_s
                duration_source = "yt_dlp"
            else:
                duration_source = "none"

        if duration_s is None:
            quarantined.append({"video_id": video_id, "reason": "duration_unknown"})
            duration_sources[video_id] = duration_source
            continue

        duration_sources[video_id] = duration_source

        result = gate_video(video_id, clips, transcript_words, duration_s)
        host_skipped_total += result.host_skipped

        if not result.ok:
            quarantined.append({"video_id": video_id, "reason": result.reason})
            continue

        if channel is None:
            channel, _ = get_channel_and_duration_cached(video_id, channels_cache, channels_cache_path)
        rights_cleared = channel.strip().casefold() in CLEARED_CHANNELS
        channel_video_counts[channel] += 1
        channel_rights[channel] = rights_cleared

        full_text = " ".join(w["w"] for w in transcript_words)
        layer_sha256 = hashlib.sha256(full_text.encode()).hexdigest()
        duration_ms = round(duration_s * 1000)

        for clip in result.clips:
            store_clip = build_store_clip(clip, video_id, channel, rights_cleared, layer_sha256, duration_ms)
            indexable_clips.append(store_clip)
            clips_per_teacher[store_clip["teacher_id"]] += 1

    # A <=150-word parent and its single child are the same recorded span, so they
    # map to the same UUIDv5 point. Keep the first (the parent) and count only unique
    # points, so the post-apply count check compares like with like.
    unique_clips = {(c["transcript_hash"], c["start_ms"], c["end_ms"]): c for c in reversed(indexable_clips)}
    duplicates_collapsed = len(indexable_clips) - len(unique_clips)
    indexable_clips = [c for c in indexable_clips if unique_clips.get((c["transcript_hash"], c["start_ms"], c["end_ms"])) is c]

    store_count_after: Optional[int] = None
    count_mismatch = False
    if apply and indexable_clips:
        store_count_after = apply_indexable_clips(indexable_clips, collection)
        count_mismatch = store_count_after != len(indexable_clips)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": collection,
        "passages_dirs": [str(d) for d in passages_dirs],
        "videos_discovered": len(discovered),
        "videos_indexed": len(discovered) - len(quarantined),
        "videos_quarantined": quarantined,
        "host_skipped_total": host_skipped_total,
        "clips_indexed_total": len(indexable_clips),
        "duplicates_collapsed": duplicates_collapsed,
        "clips_per_teacher": dict(clips_per_teacher),
        "channels": {
            ch: {"video_count": channel_video_counts[ch], "rights_cleared": channel_rights[ch]}
            for ch in channel_video_counts
        },
        "duration_sources": duration_sources,
        "applied": bool(apply),
        "store_count_after_apply": store_count_after,
        "count_mismatch": count_mismatch,
    }

    report_path = report_dir / f"report_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(json.dumps(report, indent=2))
    report["report_path"] = str(report_path)

    return report


def print_summary(report: dict[str, Any]) -> None:
    print("=" * 70)
    print("first_person_v1 index build")
    print("=" * 70)
    print(f"collection:          {report['collection']}")
    print(f"videos discovered:   {report['videos_discovered']}")
    print(f"videos indexed:      {report['videos_indexed']}")
    print(f"videos quarantined:  {len(report['videos_quarantined'])}")
    for q in report["videos_quarantined"]:
        print(f"    - {q['video_id']}: {q['reason']}")
    source_counts = Counter(report["duration_sources"].values())
    if source_counts:
        print("duration sources:    " + ", ".join(f"{src}={n}" for src, n in source_counts.items()))
    print(f"host clips skipped:  {report['host_skipped_total']}")
    print(f"clips indexed:       {report['clips_indexed_total']} (identical parent/child spans collapsed: {report['duplicates_collapsed']})")
    for teacher, n in report["clips_per_teacher"].items():
        print(f"    - {teacher}: {n}")
    print("channels:")
    for ch, info in report["channels"].items():
        print(f"    - {ch}: {info['video_count']} video(s), rights_cleared={info['rights_cleared']}")
    print(f"applied: {report['applied']}")
    if report["applied"]:
        print(f"store count after apply: {report['store_count_after_apply']}")
        if report["count_mismatch"]:
            print("!! COUNT MISMATCH — see above !!")
    print(f"report written to: {report.get('report_path')}")


def _self_check() -> None:
    words = [{"w": "Suffering"}, {"w": "is"}, {"w": "not"}, {"w": "a"}, {"w": "fact."}]
    full_text = " ".join(w["w"] for w in words)
    vt = "Suffering is not a fact."
    clip = {"verbatim_text": vt, "transcript_hash": hashlib.sha256(vt.encode()).hexdigest()}
    assert _gate_clip({**clip, "start": 1.0, "end": 2.0}, full_text, 10.0) is None
    assert _gate_clip({**clip, "transcript_hash": "0" * 64, "start": 1.0, "end": 2.0}, full_text, 10.0) == "hash_mismatch"
    assert _gate_clip({**clip, "start": 1.0, "end": 2.0}, "unrelated text", 10.0) == "substring_mismatch"
    assert _gate_clip({**clip, "start": 1.0, "end": 20.0}, full_text, 10.0) == "bad_bounds"
    print("self-check OK")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--passages-dir",
        action="append",
        dest="passages_dirs",
        default=[],
        help="Repeatable, priority order (first dir containing a video_id wins).",
    )
    parser.add_argument("--videos-json", type=Path, default=None)
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path.home() / "mukthiguru_attribution_data" / "first_person_index",
    )
    parser.add_argument("--collection", default=None)
    parser.add_argument("--apply", action="store_true", help="Actually embed + write to Qdrant (default: dry-run).")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)

    if args.self_check:
        _self_check()
        return 0

    if not args.passages_dirs or not args.videos_json:
        parser.error("--passages-dir (repeatable) and --videos-json are required")

    collection = args.collection or getattr(settings, "first_person_collection", "first_person_v1")

    report = build_index(
        passages_dirs=[Path(d) for d in args.passages_dirs],
        videos_json=args.videos_json,
        report_dir=args.report_dir,
        collection=collection,
        apply=args.apply,
    )
    print_summary(report)

    if report["count_mismatch"]:
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
