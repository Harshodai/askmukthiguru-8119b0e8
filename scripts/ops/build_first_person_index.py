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
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
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

# Third-party channels are cleared per VIDEO, never per channel: the owner approved
# these specific recordings (CONTENT-RIGHTS.md, 2026-09-26), not every upload on
# TEDx Talks or MarieTV. A new video from either channel stays uncleared until added.
CLEARED_VIDEO_IDS = {
    "TqxxCYnAxo8",  # Sri Preethaji at TEDxKC
    "UlOt31lBhLY",  # Sri Preethaji & Sri Krishnaji on MarieTV
    "iKkySU5r_x8",  # Curly Tales × Ekam — Kamiya Jani interview (approved 2026-10-04, smoke test)
    "hUmlujE6SN0",  # Sri Preethaji anchor discourse (Four Sacred Secrets / Financial fear)
    "HCs6I_BNtxo",  # Sri Preethaji discourse (Love & Attachment)
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

# Clips shorter than this are dropped (per clip, not per video). Short fragments
# carry unreliable speaker labels and out-rank real answers by looking like the
# question ("elaborate on it a little bit?", 1.6s, host speech tagged Krishnaji).
# Read-only simulation on the 116 bake-off questions (2026-09-27): >=8s lowered
# top-1 host-like leak in both v2 (7.8%->6.0%) and v4 (15.5%->10.3%) with no top-1
# loss. ponytail: chosen on the bake-off set, not held out; re-check on B1 gold.
MIN_CLIP_DURATION_S = 8.0


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
    if isinstance(data, list):
        return {v["video_id"]: v.get("duration_s") for v in data if "video_id" in v}
    if isinstance(data, dict) and "targets_515" in data:
        return {v["video_id"]: v.get("duration_s") for v in data["targets_515"] if "video_id" in v}
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


# Dangling coordinating conjunction regex: clips terminating on a conjunction
# (e.g. "...fear or", "...and,", "...so.") represent incomplete grammatical clauses
# and must never be indexed (CLAUDE.md Invariant 10, L-SENTENCE-SPLIT-CONJUNCTION-1).
_DANGLING_CONJUNCTION_RE = re.compile(
    r"\b(or|and|so|but|because)\s*[.,;:!?…—–-]*$",
    re.IGNORECASE,
)


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
    # A dangling conjunction is a clip-boundary defect, not corrupt data: it drops
    # that clip (after optional snapping) in build_index, never the whole video.
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


def load_display_words(passages_path: Path, video_id: str, n_words: int) -> Optional[list[str]]:
    """Punctuated display tokens, only when they map 1:1 onto the verbatim words."""
    punct = load_transcript(passages_path.parent.parent / "raw" / f"{video_id}_punct.json")
    if not isinstance(punct, dict) or not punct.get("zero_change_assert_passed"):
        return None
    words = punct.get("display_words") or []
    return words if len(words) == n_words else None


def clip_word_span(clip: dict, words: list[dict]) -> Optional[tuple[int, int]]:
    """[a, b) word indices whose joined text is exactly the clip's verbatim_text.
    None when the words carry no timings (the span can't be located, so it isn't guessed)."""
    if not words or "start" not in words[0]:
        return None
    # Anchored on the words themselves, not a time window: clip edges don't sit
    # exactly on word timings, and a window test lost 31 of 174 real clips.
    tokens = clip["verbatim_text"].split()
    n = len(tokens)
    starts = [
        i
        for i in range(len(words) - n + 1)
        if words[i]["w"] == tokens[0] and [w["w"] for w in words[i : i + n]] == tokens
    ]
    if not starts:
        return None
    a = min(starts, key=lambda i: abs(words[i]["start"] - clip["start"]))
    return a, a + n


def disputed_rate(words: list[dict], a: int, b: int) -> Optional[float]:
    """Share of words in [a, b) the two ASR engines disagreed on; None if not recorded."""
    if b <= a or "disputed" not in words[a]:
        return None
    return round(sum(bool(w.get("disputed")) for w in words[a:b]) / (b - a), 4)


def _rate_summary(rates: list[Optional[float]]) -> dict[str, Any]:
    known = sorted(r for r in rates if r is not None)
    if not known:
        return {"n_known": 0}
    return {
        "n_known": len(known),
        "n_unknown": len(rates) - len(known),
        "median": known[len(known) // 2],
        "p90": known[min(len(known) - 1, int(0.9 * len(known)))],
        "share_any_disputed": round(sum(r > 0 for r in known) / len(known), 4),
    }


def _boundary_defects_of(verbatim_text: str, display_text: Optional[str]) -> list[str]:
    """Defects judged on the punctuated display layer when present (verbatim is unpunctuated)."""
    from ingest.verbatim.boundaries import boundary_defects

    return boundary_defects((display_text or verbatim_text).split())


def snap_clip(
    clip: dict, words: list[dict], display_words: Optional[list[str]]
) -> tuple[Optional[dict], Optional[str]]:
    """B2: shrink a clip to whole sentences (ingest.verbatim.boundaries), recomputing
    start/end and transcript_hash from the snapped verbatim words. Returns
    (clip, None) or (None, quarantine_reason). Sentence ends come from the
    punctuated display layer when it maps 1:1, else from the verbatim words' own
    ASR punctuation (display layer aligns for only 169/295 passages_C clips); a
    span with no sentence boundary is quarantined, never guessed."""
    from ingest.verbatim.boundaries import snap_to_sentences

    span = clip_word_span(clip, words)
    if span is None:
        return None, "span_not_found"
    if display_words is None:
        display_words = [w["w"] for w in words]
    snapped = snap_to_sentences(display_words, *span)
    if snapped is None:
        return None, "boundary_unrecoverable"
    s, e = snapped
    verbatim = " ".join(w["w"] for w in words[s:e])
    return {
        **clip,
        "start": words[s]["start"],
        "end": words[e - 1]["end"],
        "verbatim_text": verbatim,
        "display_text": " ".join(display_words[s:e]),
        "transcript_hash": hashlib.sha256(verbatim.encode()).hexdigest(),
        "boundary_snapped": (s, e) != span,
    }, None


# Same cap the clip segmenter uses (mass_ingest_2026-10/stages/run_clips.py:68).
MAX_CLIP_DURATION_S = 180.0
# Complete thoughts duration cap (E5 / MASTER_PLAN: moves back to sentence holding antecedent within 120s)
COMPLETE_THOUGHTS_MAX_DURATION_S = 120.0
# clip["speaker"] -> per-word ``spk`` label in transcripts_B (ECAPA window labels).
_TEACHER_SPK = {"krishnaji": "K", "preethaji": "P"}
_NEVER_EXTEND = frozenset({"event_marker", "health_claim"})

# Extended orphan opener regex matching the E5 specification:
# 'yes,' and 'this/these/those/that + is/are/was/were'. 'So' stays allowed.
_EXTENDED_ORPHAN_OPENER_RE = re.compile(
    r"^[\"'\u201c\u2018\s]*(?:"
    r"yes\s*,"
    r"|(?:this|these|those|that)\s+(?:is|are|was|were)\b"
    r")",
    re.IGNORECASE,
)


def completeness_problem(verbatim_text: str) -> Optional[str]:
    """The SERVE-time standalone predicate, run on the text serve will see (cleaned).

    Imported, not copied, so index and serve rules cannot drift.
    Extended at index time (E5) with 'yes,' and 'this/these/those/that + is/are/was/were'.
    'So' remains allowed.
    """
    from ingest.verbatim.asr_cleaner import clean_verbatim_text
    from services.first_person_pipeline import _standalone_problem

    text = clean_verbatim_text(verbatim_text)
    problem = _standalone_problem(text)
    if problem is None and _DANGLING_CONJUNCTION_RE.search(text):
        problem = "dangling_conjunction"
    if problem is None and _EXTENDED_ORPHAN_OPENER_RE.match(text):
        problem = "orphan_opener"
    return problem


def _fit_under_cap(
    tokens: list[str],
    words: list[dict],
    clip: dict,
    s: int,
    e: int,
    max_s: float,
    trim_end: bool,
    keep: tuple[int, int],
) -> Optional[tuple[int, int]]:
    """Keep the sentences of an over-long repaired passage that fit ``max_s``.

    Growing a fragment until it stands alone can overshoot the duration cap. The old
    behaviour threw the repaired teaching away (the ``incomplete:*:over_120s`` drop --
    the second-largest reject bucket in the live funnel). Instead, walk the passage's
    whole sentences outward from the end the repair grew TOWARDS -- the antecedent side
    for an orphan opener (keep the head, drop trailing sentences), the completed tail
    for a cut tail (keep the tail, drop leading sentences) -- and keep as many
    consecutive sentences as the cap allows.

    Shrink-only, so no other voice can enter and the result stays an exact transcript
    substring. ``keep`` is the ORIGINAL clip's span: the remainder must still overlap it,
    or a clip whose single sentence did not fit could be replaced by the bare sentence we
    grew back over -- serving the repair scaffold as if it were the teaching. Returns None
    when even one sentence exceeds the cap, when the passage holds no sentence boundary,
    when nothing of the original clip survives, or when the remainder would be too thin to
    serve (``_MIN_TEACHING_WORDS``, imported so index and serve cannot drift -- a shorter
    remainder would be rejected on serve anyway, so keeping it would only move the drop
    from index to serve).
    """
    from ingest.verbatim.boundaries import sentence_spans
    from services.first_person_pipeline import _MIN_TEACHING_WORDS

    spans = sentence_spans(tokens, s, e)
    if not spans:
        return None
    lo: Optional[int] = None
    hi = 0
    for a, b in spans if trim_end else reversed(spans):
        if lo is None:
            lo, hi = a, b
            continue
        cand_lo, cand_hi = min(lo, a), max(hi, b)
        if words[cand_hi - 1]["end"] - words[cand_lo]["start"] > max_s:
            break
        lo, hi = cand_lo, cand_hi
    if lo is None or words[hi - 1]["end"] - words[lo]["start"] > max_s:
        return None
    if hi <= keep[0] or lo >= keep[1]:
        return None  # remainder is only the scaffold we grew over, not the clip
    is_interview = bool(clip.get("question_text") or clip.get("question_context"))
    if hi - lo < (5 if is_interview else _MIN_TEACHING_WORDS):
        return None
    return lo, hi


def _resliced_clip(
    clip: dict,
    words: list[dict],
    tokens: list[str],
    display_words: Optional[list[str]],
    s: int,
    e: int,
    **extra: Any,
) -> dict:
    """The same clip re-cut to the word span [s, e): timings, text and hash recomputed.

    Only ever a sub-span of the transcript words, so the text stays an exact transcript
    substring and the speaker attribution is untouched.
    """
    verbatim = " ".join(w["w"] for w in words[s:e])
    return {
        **clip,
        "start": words[s]["start"],
        "end": words[e - 1]["end"],
        "verbatim_text": verbatim,
        "display_text": " ".join((display_words or tokens)[s:e]),
        "transcript_hash": hashlib.sha256(verbatim.encode()).hexdigest(),
        **extra,
    }


def complete_clip(
    clip: dict,
    words: list[dict],
    display_words: Optional[list[str]],
    max_s: float = COMPLETE_THOUGHTS_MAX_DURATION_S,
    max_steps: int = 4,
) -> tuple[Optional[dict], Optional[str]]:
    """Index-time completeness: return (clip, None) if it stands alone, possibly after
    EXTENDING it by whole adjacent sentences (back for an orphan opener, forward for a
    cut tail); else (None, reason). Every added word must carry the clip teacher's own
    per-word speaker label, so another voice is never pulled in. Text is only ever
    widened along the transcript words, so it stays an exact transcript substring.
    Event markers and health claims are never extended -- they drop.

    When the repair overshoots ``max_s``, the passage is not discarded: the sentences
    that fit the cap are kept (``_fit_under_cap``) and re-checked for standalone-ness.

    A clip that already stands alone but is LONGER than ``max_s`` is likewise cut back to
    the sentences that fit and flagged ``thought_trimmed``; nothing capped those before,
    so they were stored too long and then refused on serve.
    """
    from ingest.verbatim.boundaries import grow_to_sentence_end, grow_to_sentence_start

    problem = completeness_problem(clip["verbatim_text"])
    spk = _TEACHER_SPK.get(clip.get("speaker"))
    span = clip_word_span(clip, words)
    tokens = [w["w"] for w in words]
    if problem is None and span is not None:
        # Standalone already -- but a clip LONGER than the cap is refused on serve
        # ("%.0fs exceeds the %.0fs cap" in _passes_content_quality_gate), which is the
        # single largest reject bucket in the live funnel. Nothing used to cap these,
        # because the completeness cap only ran on passages that had to be grown. Cut
        # them down to the sentences that fit, so the corpus holds only servable lengths.
        s, e = span
        if words[e - 1]["end"] - words[s]["start"] > max_s:
            fitted = _fit_under_cap(tokens, words, clip, s, e, max_s, trim_end=True, keep=span)
            if fitted is not None:
                fs, fe = fitted
                trimmed = _resliced_clip(
                    clip, words, tokens, display_words, fs, fe, thought_trimmed=True
                )
                # Only accept the re-cut when it still reads as a complete thought;
                # otherwise keep the original and let serve's cap guard it.
                if completeness_problem(trimmed["verbatim_text"]) is None:
                    return trimmed, None
        return clip, None
    if problem is None:
        return clip, None
    if problem in _NEVER_EXTEND or spk is None or span is None or "spk" not in words[0]:
        return None, f"incomplete:{problem}"
    # Sentence ends are read from the VERBATIM words (what serve judges), not the
    # display layer: they disagree, and display-led growth served "...pain. You".
    labels = [w.get("spk") for w in words]
    s, e = span
    base_defects = set(_boundary_defects_of(clip["verbatim_text"], None))
    for _ in range(max_steps):
        if problem == "orphan_opener":
            grown = grow_to_sentence_start(tokens, labels, s - 1, spk) if s > 0 else None
            s = grown if grown is not None else s
        else:  # ends_mid_sentence / dangling_conjunction
            grown = grow_to_sentence_end(tokens, labels, e, spk)
            e = grown if grown is not None else e
        if grown is None:
            return None, f"incomplete:{problem}"
        if words[e - 1]["end"] - words[s]["start"] > max_s:
            fitted = _fit_under_cap(
                tokens, words, clip, s, e, max_s, trim_end=problem == "orphan_opener", keep=span
            )
            if fitted is None:
                return None, f"incomplete:{problem}:over_{int(max_s)}s"
            s, e = fitted
        verbatim = " ".join(w["w"] for w in words[s:e])
        direction = problem
        problem = completeness_problem(verbatim)
        # A stray ASR full stop can make "yourself." look like a sentence start; if
        # growing introduced a new edge defect (e.g. head_lowercase), keep growing.
        if problem is None and set(_boundary_defects_of(verbatim, None)) - base_defects:
            problem = direction
        if problem in _NEVER_EXTEND:
            return None, f"incomplete:{problem}"
        if problem is None:
            return _resliced_clip(
                clip, words, tokens, display_words, s, e, thought_extended=True
            ), None
    return None, f"incomplete:{problem}"


def dedupe_contained(clips: list[dict]) -> tuple[list[dict], int, int]:
    """Per video, drop a clip whose span lies inside another surviving clip's span
    (keep the complete parent) and drop exact-duplicate text. A voice-verified child
    is kept when no covering parent is verified, so dedupe never downgrades a named
    attribution. Returns (kept, contained_removed, text_duplicates_removed).
    ponytail: O(n^2) per video (tens of clips); interval tree if videos grow to thousands.
    """
    by_video: dict[str, list[dict]] = {}
    for c in clips:
        by_video.setdefault(c["video_id"], []).append(c)
    kept: list[dict] = []
    contained = text_dupes = 0
    for vid_clips in by_video.values():
        seen_text: set[str] = set()
        vid_kept: list[dict] = []
        for c in sorted(vid_clips, key=lambda c: (c["start_ms"], -c["end_ms"])):
            if c["verbatim_text"] in seen_text:
                text_dupes += 1
                continue
            cover = [
                k for k in vid_kept if k["start_ms"] <= c["start_ms"] and c["end_ms"] <= k["end_ms"]
            ]
            if cover and (
                not c.get("speaker_verified") or any(k.get("speaker_verified") for k in cover)
            ):
                contained += 1
                continue
            seen_text.add(c["verbatim_text"])
            vid_kept.append(c)
        kept.extend(vid_kept)
    return kept, contained, text_dupes


def _load_speaker_result(passages_path: Path, video_id: str) -> Optional[dict]:
    """The video's ECAPA speaker-verification result (``raw/<id>_speaker.json``).

    Returns None when absent or unreadable — the caller fails closed (clip stays
    unverified), never crashes the build.
    """
    path = passages_path.parent.parent / "raw" / f"{video_id}_speaker.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def build_store_clip(
    clip: dict,
    video_id: str,
    channel: str,
    rights_cleared: bool,
    layer_sha256: str,
    duration_ms: int,
    speaker_result: Optional[dict] = None,
) -> dict:
    """Map a passages_B clip dict onto FirstPersonStore's clip schema.

    `first_person_eligible` is a data-quality gate only (did it pass our
    substring/hash/bounds checks?), never a rights gate — every clip that
    reaches this function already cleared those, so it is always True here.
    Rights enforcement is `rights_cleared`, persisted separately and filtered
    at serve time (`search_hybrid`, gated on `settings.first_person_serve_unregistered`)
    so the owner's decision to serve unregistered-channel clips for a local
    eval isn't permanently hidden by this indexer.

    `speaker_verified` is emitted as True ONLY on a real ECAPA pass over the
    clip's span (`verify_clip_speaker` against `speaker_result`,
    L-FP-HYBRID-SCAFFOLD-1). Missing/failed verification omits the key, so
    attribution keeps "shared in <channel>" — never map teacher_id to a name.
    """
    teacher_id = clip["speaker"]
    start_ms = round(clip["start"] * 1000)
    end_ms = round(clip["end"] * 1000)
    from ingest.verbatim.asr_cleaner import clean_verbatim_text
    from ingest.verbatim.speaker_verify import verify_clip_speaker

    verbatim_text = clean_verbatim_text(str(clip["verbatim_text"]))
    if not verbatim_text.strip():
        raise ValueError(f"ASR cleaner removed all text for video {video_id}")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    store_clip = {
        "video_id": video_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker": _TEACHER_LABELS[teacher_id],
        "teacher_id": teacher_id,
        "teacher_ids": [teacher_id],
        "transcript_hash": hashlib.sha256(verbatim_text.encode("utf-8")).hexdigest(),
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
    # I2 / I3: metadata context and OKF concept tags
    for ctx_key in ("discourse_context", "tags", "okf_concept_id", "okf_title"):
        if clip.get(ctx_key) is not None:
            store_clip[ctx_key] = clip[ctx_key]
    if verify_clip_speaker(clip, speaker_result):
        store_clip["speaker_verified"] = True
    return store_clip


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
    """Embed + upsert into Qdrant. Only imported/run when --apply is passed.

    Cleanup strategy: snapshot the collection's full ID set before upserting,
    then delete any point whose ID is NOT produced by this build. This is
    ID-exact rather than video_id-based, so no point survives if its source
    video is no longer indexable — even when indexable_clips is empty.
    """
    from qdrant_client.http.models import PointIdsList

    from services.embedding_service import EmbeddingService
    from services.first_person_store import (
        FirstPersonStore,
        canonical_video_id,
        is_blocked_promise_clip,
        make_first_person_point_id,
    )
    from services.qdrant.utils import QdrantUtils

    # Hard Stop H4 apply-path pre-filter (L-FP-PROMISE-1): a blocked promise
    # clip must never reach the batch upsert (validate_clip_entry raises there
    # and would crash the whole batch). Drop + log, upsert the rest.
    blocked = [c for c in indexable_clips if is_blocked_promise_clip(c)]
    if blocked:
        logger.warning(
            "[first_person_index] dropping %d blocked promise clip(s) "
            "(quarantine_reason=outcome_promise_H4), upserting %d remaining",
            len(blocked),
            len(indexable_clips) - len(blocked),
        )
        indexable_clips = [c for c in indexable_clips if not is_blocked_promise_clip(c)]

    if not indexable_clips:
        # The ID diff below would delete every existing point. An empty build is
        # almost always a wrong --passages-dir or an upstream failure, not intent.
        raise RuntimeError(
            f"Refusing to apply: this build produced 0 clips and would empty '{collection}'."
        )

    embedder = EmbeddingService()
    store = FirstPersonStore(collection=collection)
    store.init_collection()

    # Snapshot existing IDs BEFORE upsert so we can diff against the build output.
    existing_ids: set = set()
    scroll_offset = None
    while True:
        result, scroll_offset = store.client.scroll(
            collection_name=collection,
            offset=scroll_offset,
            limit=1000,
            with_payload=False,
            with_vectors=False,
        )
        for pt in result:
            existing_ids.add(pt.id)
        if scroll_offset is None:
            break

    produced_ids: set = set()
    for i in range(0, len(indexable_clips), _BATCH_SIZE):
        batch = indexable_clips[i : i + _BATCH_SIZE]
        embeddings = embedder.encode_batch([c["verbatim_text"] for c in batch])
        sparse_vectors = []
        for sparse_dict in embeddings["sparse"]:
            sv = QdrantUtils.sparse_dict_to_vector(sparse_dict)
            sparse_vectors.append({"indices": sv.indices, "values": sv.values})
        store.upsert_clips(batch, embeddings["dense"], None, sparse_vectors)
        # Mirror upsert_clips' within-batch (video_id, verbatim_text) dedup
        # (first_person_store.py) so produced_ids reflects only points the
        # store actually writes. Reset per batch: the store dedups per call.
        # NOTE (W1 2026-10-11): this derives IDs from the clip's own
        # transcript_hash WITHOUT the store's clean+rehash step — a latent
        # skew if a caller ever passes uncleaned text (build_store_clip
        # clean-before-hash makes build outputs canonical, and the store
        # re-clean is idempotent, so live inputs agree). It is also immune to
        # the mass driver's missing-point tripwire class: this path has no
        # expected-vs-after assertion — post-apply verification is count-based
        # (store.count() vs len(indexable_clips), count_mismatch), not
        # ID-based. Do NOT add an ID tripwire here without routing both sides
        # through store_point_id_for_clip.
        seen_clip_keys: set[tuple[str, str]] = set()
        for clip in batch:
            # Same ID the store assigns on upsert (clips carry no point_id key).
            dedupe_key = (
                canonical_video_id(str(clip.get("video_id", ""))),
                str(clip.get("verbatim_text", "")),
            )
            if dedupe_key in seen_clip_keys:
                continue
            seen_clip_keys.add(dedupe_key)
            produced_ids.add(
                make_first_person_point_id(
                    clip["transcript_hash"], clip["start_ms"], clip["end_ms"]
                )
            )

    # Delete any point that was in the collection before the build but is not
    # produced by this build. Includes stale clips from quarantined videos.
    stale_ids = list(existing_ids - produced_ids)
    if stale_ids:
        store.client.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=stale_ids),
            wait=True,
        )

    return store.count()


def build_index(
    passages_dirs: list[Path],
    videos_json: Path,
    report_dir: Path,
    collection: str,
    apply: bool = False,
    dump_ids: Optional[Path] = None,
    min_clip_duration_s: float = MIN_CLIP_DURATION_S,
    snap_boundaries: bool = False,
    max_disputed_rate: Optional[float] = None,
    complete_thoughts: bool = False,
    only_videos: Optional[set[str]] = None,
    clips_out: Optional[list[dict]] = None,
) -> dict[str, Any]:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    durations = load_video_durations(videos_json)
    discovered = discover_videos(passages_dirs)
    if only_videos is not None:
        discovered = {v: p for v, p in discovered.items() if v in only_videos}

    channels_cache_path = report_dir / "channels.json"
    channels_cache = _load_channels_cache(channels_cache_path)

    quarantined: list[dict[str, str]] = []
    host_skipped_total = 0
    clips_too_short = 0
    speaker_verified_clips = 0
    videos_missing_speaker_result = 0
    clip_quarantine: Counter = Counter()  # per-clip reasons (B2 snap, ASR disagreement)
    clips_snapped = 0
    clips_extended = 0
    clips_trimmed = 0
    incomplete_reasons: Counter = Counter()
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
            quarantined.append(
                {"video_id": video_id, "reason": f"asr_agreement_low:{agreement:.3f}"}
            )
            continue

        # Duration precedence: videos_final.json first (cheap, no network); if
        # that's null, fall back to a cached yt-dlp lookup (which also yields
        # the channel, needed later regardless — one combined call).
        duration_s = durations.get(video_id)
        duration_source = "videos_final"
        channel: Optional[str] = None
        if duration_s is None:
            channel, yt_duration_s = get_channel_and_duration_cached(
                video_id, channels_cache, channels_cache_path
            )
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
            channel, _ = get_channel_and_duration_cached(
                video_id, channels_cache, channels_cache_path
            )
        rights_cleared = (
            channel.strip().casefold() in CLEARED_CHANNELS or video_id in CLEARED_VIDEO_IDS
        )
        channel_video_counts[channel] += 1
        channel_rights[channel] = rights_cleared

        full_text = " ".join(w["w"] for w in transcript_words)
        layer_sha256 = hashlib.sha256(full_text.encode()).hexdigest()
        duration_ms = round(duration_s * 1000)

        # ECAPA voice evidence for this video (L-FP-HYBRID-SCAFFOLD-1). Absent
        # or failed evidence fails closed per clip (no speaker_verified key).
        speaker_result = _load_speaker_result(passages_path, video_id)
        if speaker_result is None or speaker_result.get("ok") is not True:
            videos_missing_speaker_result += 1

        display_words = (
            load_display_words(passages_path, video_id, len(transcript_words))
            if snap_boundaries
            else None
        )
        for clip in result.clips:
            if snap_boundaries:
                clip, reason = snap_clip(clip, transcript_words, display_words)
                if reason:
                    clip_quarantine[reason] += 1
                    continue
                clips_snapped += bool(clip.get("boundary_snapped"))
            if complete_thoughts:
                clip, reason = complete_clip(clip, transcript_words, display_words)
                if reason:
                    incomplete_reasons[reason] += 1
                    continue
                clips_extended += bool(clip.get("thought_extended"))
                clips_trimmed += bool(clip.get("thought_trimmed"))
            if _DANGLING_CONJUNCTION_RE.search(clip["verbatim_text"]):
                clip_quarantine["dangling_conjunction"] += 1
                continue
            # Clips with explicit question context (from verified interview turns) can be
            # as concise as 2.0s (e.g. rapid-fire spiritual answers). Monologues without
            # question context retain the strict 8.0s floor to eliminate fragment leaks.
            effective_min_s = 2.0 if clip.get("question_context") else min_clip_duration_s
            if clip["end"] - clip["start"] < effective_min_s:
                clips_too_short += 1
                continue
            span = clip_word_span(clip, transcript_words)
            rate = disputed_rate(transcript_words, *span) if span else None
            if max_disputed_rate is not None and (rate is None or rate > max_disputed_rate):
                clip_quarantine[
                    "asr_disputed_rate_high" if rate is not None else "asr_disputed_rate_unknown"
                ] += 1
                continue
            store_clip = build_store_clip(
                clip,
                video_id,
                channel,
                rights_cleared,
                layer_sha256,
                duration_ms,
                speaker_result,
            )
            speaker_verified_clips += store_clip.get("speaker_verified") is True
            # Hard Stop H4 apply-path pre-filter (L-FP-PROMISE-1): drop blocked
            # promise clips per-clip with quarantine_reason=outcome_promise_H4.
            # validate_clip_entry stays fail-closed (raises) for direct writes;
            # this gate keeps a blocked clip from ever reaching the batch upsert
            # and crashing it. Local import avoids a module-level cycle.
            from services.first_person_store import is_blocked_promise_clip

            if is_blocked_promise_clip(store_clip):
                clip_quarantine["outcome_promise_H4"] += 1
                continue
            store_clip["asr_disputed_rate"] = rate
            store_clip["has_disputed_words"] = bool(rate) if rate is not None else None
            indexable_clips.append(store_clip)

    # A <=150-word parent and its single child are the same recorded span, so they
    # map to the same UUIDv5 point. Keep the first (the parent) and count only unique
    # points, so the post-apply count check compares like with like.
    unique_clips = {
        (c["transcript_hash"], c["start_ms"], c["end_ms"]): c for c in reversed(indexable_clips)
    }
    duplicates_collapsed = len(indexable_clips) - len(unique_clips)
    indexable_clips = [
        c
        for c in indexable_clips
        if unique_clips.get((c["transcript_hash"], c["start_ms"], c["end_ms"])) is c
    ]

    contained_removed = text_duplicates_removed = 0
    if complete_thoughts:
        indexable_clips, contained_removed, text_duplicates_removed = dedupe_contained(
            indexable_clips
        )

    # Count clips per teacher after duplicate collapse so breakdown matches clips_indexed_total
    for c in indexable_clips:
        clips_per_teacher[c["teacher_id"]] += 1

    if dump_ids is not None:
        from services.first_person_store import make_first_person_point_id

        sorted_ids = sorted(
            make_first_person_point_id(c["transcript_hash"], c["start_ms"], c["end_ms"])
            for c in indexable_clips
        )
        dump_ids_path = Path(dump_ids)
        dump_ids_path.parent.mkdir(parents=True, exist_ok=True)
        dump_ids_path.write_text(
            "\n".join(sorted_ids) + ("\n" if sorted_ids else ""), encoding="utf-8"
        )

    if clips_out is not None:
        clips_out.extend(indexable_clips)

    from services.first_person_pipeline import _passes_content_quality_gate

    n_clips = len(indexable_clips) or 1
    standalone_pass = sum(completeness_problem(c["verbatim_text"]) is None for c in indexable_clips)
    gate_pass = sum(_passes_content_quality_gate(c, gate_enabled=True) for c in indexable_clips)

    store_count_after: Optional[int] = None
    count_mismatch = False
    if apply:
        store_count_after = apply_indexable_clips(indexable_clips, collection)
        count_mismatch = store_count_after != len(indexable_clips)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "collection": collection,
        "passages_dirs": [str(d) for d in passages_dirs],
        "videos_discovered": len(discovered),
        "videos_indexed": len(discovered) - len(quarantined),
        "videos_quarantined": quarantined,
        "host_skipped_total": host_skipped_total,
        "min_clip_duration_s": min_clip_duration_s,
        "clips_too_short": clips_too_short,
        "snap_boundaries": snap_boundaries,
        "clips_snapped": clips_snapped,
        "max_disputed_rate": max_disputed_rate,
        "clips_quarantined": dict(clip_quarantine),
        "asr_disputed_rate": _rate_summary([c.get("asr_disputed_rate") for c in indexable_clips]),
        "boundary_clean": sum(
            not _boundary_defects_of(c["verbatim_text"], c.get("display_text"))
            for c in indexable_clips
        ),
        "clips_indexed_total": len(indexable_clips),
        "complete_thoughts": complete_thoughts,
        "only_videos": sorted(only_videos) if only_videos is not None else None,
        "clips_extended": clips_extended,
        "clips_trimmed": clips_trimmed,
        "clips_dropped_incomplete": sum(incomplete_reasons.values()),
        "incomplete_reasons": dict(incomplete_reasons),
        "contained_removed": contained_removed,
        "text_duplicates_removed": text_duplicates_removed,
        "standalone_pass_share": round(standalone_pass / n_clips, 4),
        "strict_complete_share": round(gate_pass / n_clips, 4),
        "speaker_verified_clips": speaker_verified_clips,
        "videos_missing_speaker_result": videos_missing_speaker_result,
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

    report_path = report_dir / f"report_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
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
    print(f"short clips dropped: {report['clips_too_short']} (< {report['min_clip_duration_s']}s)")
    print(
        f"snap boundaries:     {report['snap_boundaries']} (snapped {report['clips_snapped']}); clip quarantine: {report['clips_quarantined']}"
    )
    print(
        f"boundary-clean:      {report['boundary_clean']} of {report['clips_indexed_total']}; ASR disputed rate: {report['asr_disputed_rate']}"
    )
    print(
        f"clips indexed:       {report['clips_indexed_total']} (identical parent/child spans collapsed: {report['duplicates_collapsed']})"
    )
    if report["complete_thoughts"]:
        print(
            f"complete thoughts:   extended {report['clips_extended']}, trimmed to cap "
            f"{report['clips_trimmed']}, dropped "
            f"{report['clips_dropped_incomplete']} {report['incomplete_reasons']}, contained removed "
            f"{report['contained_removed']}, text dupes removed {report['text_duplicates_removed']}"
        )
    print(
        f"standalone pass:     {report['standalone_pass_share']}; strict (full serve gate): "
        f"{report['strict_complete_share']}"
    )
    print(
        f"speaker verified:    {report['speaker_verified_clips']} of {report['clips_indexed_total']} "
        f"(videos without usable speaker evidence: {report['videos_missing_speaker_result']})"
    )
    for teacher, n in report["clips_per_teacher"].items():
        print(f"    - {teacher}: {n}")
    print("channels:")
    for ch, info in report["channels"].items():
        print(
            f"    - {ch}: {info['video_count']} video(s), rights_cleared={info['rights_cleared']}"
        )
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
    assert (
        _gate_clip({**clip, "transcript_hash": "0" * 64, "start": 1.0, "end": 2.0}, full_text, 10.0)
        == "hash_mismatch"
    )
    assert (
        _gate_clip({**clip, "start": 1.0, "end": 2.0}, "unrelated text", 10.0)
        == "substring_mismatch"
    )
    assert _gate_clip({**clip, "start": 1.0, "end": 20.0}, full_text, 10.0) == "bad_bounds"
    print("self-check OK")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
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
    parser.add_argument(
        "--min-clip-seconds",
        type=float,
        default=MIN_CLIP_DURATION_S,
        help="Drop clips shorter than this (default %(default)s).",
    )
    parser.add_argument(
        "--dump-ids",
        type=Path,
        default=None,
        help="Optional path to write sorted list of generated point IDs (for exact determinism diffing).",
    )
    parser.add_argument(
        "--snap-boundaries",
        action="store_true",
        help="B2: shrink clips to whole sentences via the punct display layer; unrecoverable clips are quarantined.",
    )
    parser.add_argument(
        "--max-disputed-rate",
        type=float,
        default=None,
        help="Quarantine clips whose share of ASR-disputed words exceeds this (unset = record only; pick the value on gold, not by hand).",
    )
    parser.add_argument(
        "--complete-thoughts",
        action="store_true",
        help="Extend clips that fail the serve-time standalone predicate by whole same-teacher "
        "sentences (drop if unrecoverable), then drop contained/duplicate clips.",
    )
    parser.add_argument(
        "--only-videos",
        default=None,
        help="Comma-separated video ids: build only these (pilot builds).",
    )
    parser.add_argument(
        "--dump-clips",
        default=None,
        help="Optional path to write JSON array of candidate indexable clips.",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Actually embed + write to Qdrant (default: dry-run)."
    )
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)

    if args.self_check:
        _self_check()
        return 0

    if not args.passages_dirs or not args.videos_json:
        parser.error("--passages-dir (repeatable) and --videos-json are required")

    collection = args.collection or getattr(settings, "first_person_collection", "first_person_v1")

    clips_out: Optional[list[dict]] = [] if args.dump_clips else None

    report = build_index(
        passages_dirs=[Path(d) for d in args.passages_dirs],
        videos_json=args.videos_json,
        report_dir=args.report_dir,
        collection=collection,
        apply=args.apply,
        dump_ids=args.dump_ids,
        min_clip_duration_s=args.min_clip_seconds,
        snap_boundaries=args.snap_boundaries,
        max_disputed_rate=args.max_disputed_rate,
        complete_thoughts=args.complete_thoughts,
        only_videos=set(args.only_videos.split(",")) if args.only_videos else None,
        clips_out=clips_out,
    )
    if args.dump_clips and clips_out is not None:
        dump_clips_path = Path(args.dump_clips)
        dump_clips_path.parent.mkdir(parents=True, exist_ok=True)
        dump_clips_path.write_text(json.dumps(clips_out, indent=2), encoding="utf-8")

    print_summary(report)

    if report["count_mismatch"]:
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
