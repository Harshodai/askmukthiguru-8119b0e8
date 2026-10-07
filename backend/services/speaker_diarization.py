"""Speaker Diarization & Quotable Clip Pipeline — Invariant C1/C2/C3.

Transforms raw word alignments and voiceprint windows into certified,
turn-bounded teacher clips with host exclusion and cryptographic transcript hashes.

Invariants:
1. Abstain by default: unaligned words or mixed speaker intervals are never quoted as a named teacher.
2. Host exclusion: questions/interviews exclude host or translator speech turns.
3. Turn-boundary padding: each run's start/end is padded by a fixed `padding_s`
   (default 200ms). There is no adaptive anti-bleed shrink for gaps under 400ms --
   padding is constant regardless of how close the adjacent speaker turn is.
4. Content-addressed clip hashing: each clip carries its own deterministic transcript_hash,
   computed over the exact joined clip text (no whitespace normalization).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

try:
    from ingest.verbatim.speaker_verify import relabel_turn_start_prefixes
except ImportError:
    try:
        from backend.ingest.verbatim.speaker_verify import relabel_turn_start_prefixes
    except ImportError:
        relabel_turn_start_prefixes = None

logger = logging.getLogger(__name__)

TEACHER_NAME_MAP = {
    "P": "Sri Preethaji",
    "K": "Sri Krishnaji",
    "O": "Host / Questioner",
    "?": "Unknown",
}

# clip["speaker"] values for the v2 run-based clip builder below -- lowercase,
# matching build_first_person_index.py's _TEACHER_LABELS, not TEACHER_NAME_MAP.
_RUN_TEACHER_LABELS = {"P": "preethaji", "K": "krishnaji"}
_SENTENCE_END_CHARS = (".", "?", "!")

# Coordinating and subordinating conjunctions: clips must never split on or end
# with these dangling tokens without forward clause resolution (CLAUDE.md Invariant 10).
_COORDINATING_CONJUNCTIONS = frozenset(
    {
        "or",
        "and",
        "so",
        "but",
        "because",
        "nor",
        "for",
        "yet",
        "although",
        "though",
    }
)

# --- v2 clip-builder thresholds ------------------------------------------------
# Named constants (not magic literals) so a future retune has one place to look.
# Values are the original offline-pilot defaults (run_clips.py's predecessor),
# carried over unchanged -- INFERRED provenance, not re-derived this session;
# see the build_clips_v2 dry-run report for the measurement that motivated the
# *sentence-boundary* fix below, not these specific numbers.
_MAX_UNKNOWN_GAP_S = (
    3.0  # a "?" island longer than this (wall-clock) is a real pause/turn, not noise
)
_MAX_UNKNOWN_WORDS = (
    8  # a "?" island longer than this (word count) is a real turn, not ASR/ECAPA flicker
)
_MIN_CLIP_WORDS = 12  # below this a "clip" is an unusable fragment, not a quotable teaching
_PARENT_MAX_S = (
    180.0  # forced-split budget: a single run longer than this is split into multiple parents
)
_CHILD_TARGET_WORDS = (100, 200)  # sub-clips of an over-long parent, sized for citation display
_PAD_S = 0.2  # turn-boundary padding, see module docstring invariant 3


def _grow_to_budget(words: list[dict[str, Any]], start: int, fits) -> int:
    """Largest exclusive end index such that words[start:end] satisfies `fits`.

    Always advances by at least one word, so callers always make progress.
    """
    n = len(words)
    end = start + 1
    while end < n and fits(words, start, end + 1):
        end += 1
    return end


def _find_sentence_end(words: list[dict[str, Any]], start: int, end: int) -> Optional[int]:
    """Exclusive end index of the last word in words[start:end) ending in
    '.', '?' or '!', or None if no word in the range does.

    Skips words that are coordinating conjunctions even if punctuated, as
    they do not represent complete grammatical thoughts.
    """
    for i in range(end - 1, start - 1, -1):
        w = words[i]["w"]
        if w and w[-1] in _SENTENCE_END_CHARS:
            clean = w.rstrip(".?!…,:;—–-").lower()
            if clean in _COORDINATING_CONJUNCTIONS:
                continue
            return i + 1
    return None


def _cut_point(words: list[dict[str, Any]], start: int, end: int) -> tuple[int, str]:
    """Best cut (exclusive end index, "sentence"|"pause") within words[start:end).

    Prefers the last word ending in '.', '?' or '!'; falls back to cutting
    after the word preceding the largest inter-word pause. If the word preceding
    the pause is a coordinating conjunction, shifts the cut before the conjunction
    so it does not dangle at clip end.
    """
    sentence_end = _find_sentence_end(words, start, end)
    if sentence_end is not None:
        return sentence_end, "sentence"

    if end - start <= 1:
        return end, "pause"

    best_gap, best_idx = -1.0, start
    for i in range(start, end - 1):
        gap = words[i + 1]["start"] - words[i]["end"]
        if gap >= best_gap:
            best_gap, best_idx = gap, i

    # If the word preceding the pause is a coordinating conjunction,
    # shift cut to before the conjunction so the conjunction stays with the next clause.
    w_chosen = words[best_idx]["w"].rstrip(".,;:!?…—–-").lower()
    if w_chosen in _COORDINATING_CONJUNCTIONS and best_idx > start:
        return best_idx, "pause"

    return best_idx + 1, "pause"


def _split_run(
    words: list[dict[str, Any]], fits, stats: dict[str, int], ends_at_flip: bool
) -> list[list[dict[str, Any]]]:
    """Split `words` into chunks that satisfy `fits`, cutting at sentence ends
    (falling back to the largest pause) only when a forced cut is needed.

    `ends_at_flip` says whether `words` was truncated by a genuine speaker
    change (more, differently-labelled words follow in the full transcript)
    rather than simply running out of transcript. Only the final chunk is
    affected: when it was cut off by a real flip and does not itself end on a
    sentence boundary, the trailing partial sentence is dropped rather than
    served (rule: never end a served clip mid-sentence). When `words` instead
    ends because the transcript does -- there is no "next" speaker to have cut
    it off -- the tail is kept whole even without terminal punctuation; there
    is nothing more complete to fall back to.
    """
    chunks: list[list[dict[str, Any]]] = []
    start, n = 0, len(words)
    while start < n:
        grown_end = _grow_to_budget(words, start, fits)
        if grown_end >= n:
            tail_end = n
            # Strip trailing conjunctions from tail
            while (
                tail_end > start + 1
                and words[tail_end - 1]["w"].rstrip(".,;:!?…—–-").lower()
                in _COORDINATING_CONJUNCTIONS
            ):
                tail_end -= 1
            last_w = words[tail_end - 1]["w"] if tail_end > start else ""
            if ends_at_flip and not (last_w and last_w[-1] in _SENTENCE_END_CHARS):
                cut_end = _find_sentence_end(words, start, tail_end)
                if cut_end is not None and cut_end > start:
                    chunks.append(words[start:cut_end])
                    stats["cut_at_sentence"] += 1
                stats["dropped_mid_sentence_at_flip"] += 1
            else:
                chunks.append(words[start:tail_end])
            break
        cut_end, kind = _cut_point(words, start, grown_end)
        # Avoid leaving trailing conjunction at cut_end
        while (
            cut_end > start + 1
            and words[cut_end - 1]["w"].rstrip(".,;:!?…—–-").lower() in _COORDINATING_CONJUNCTIONS
        ):
            cut_end -= 1
        chunks.append(words[start:cut_end])
        stats["cut_at_sentence" if kind == "sentence" else "cut_at_pause"] += 1
        start = cut_end
    return chunks


def _duration_fits(max_duration_s: float):
    return lambda words, start, end: (
        (words[end - 1]["end"] - words[start]["start"]) <= max_duration_s
    )


def _word_count_fits(max_words: int):
    return lambda words, start, end: (end - start) <= max_words


def _build_teacher_runs(
    words: list[dict[str, Any]],
    max_unknown_gap_s: float,
    max_unknown_words: int,
    stats: dict[str, int],
) -> list[tuple[str, list[dict[str, Any]], bool]]:
    """Group words into (teacher_label, run_words, ends_at_flip) runs per the
    module docstring's rule 1: a run is consecutive words of one teacher; a
    "?" stretch is absorbed only when the same teacher brackets it and it is
    short enough; any "O" word, a different teacher, or a longer "?" stretch
    ends the run. `ends_at_flip` is True when the run stops short of the end
    of `words` -- i.e. a genuine speaker change follows, as opposed to the
    run simply running out of transcript.
    """
    n = len(words)
    segments: list[tuple[str, int, int]] = []
    i = 0
    while i < n:
        j = i
        spk = words[i]["spk"]
        while j < n and words[j]["spk"] == spk:
            j += 1
        segments.append((spk, i, j))
        i = j

    runs: list[tuple[str, list[dict[str, Any]], bool]] = []
    m = len(segments)
    seg_i = 0
    while seg_i < m:
        label, run_start, run_end = segments[seg_i]
        if label not in _RUN_TEACHER_LABELS:
            seg_i += 1
            continue

        k = seg_i + 1
        while k < m:
            nlabel, ns, ne = segments[k]
            if nlabel != "?" or k + 1 >= m or segments[k + 1][0] != label:
                break
            gap_words = ne - ns
            gap_s = words[ne - 1]["end"] - words[ns]["start"]
            if gap_words > max_unknown_words or gap_s > max_unknown_gap_s:
                break
            run_end = segments[k + 1][2]
            stats["merged_unknown_gaps"] += 1
            k += 2

        runs.append((label, words[run_start:run_end], run_end < n))
        seg_i = k

    return runs


def _make_run_clip(
    words: list[dict[str, Any]], video_id: str, speaker: str, group_id: str, k: int, pad_s: float
) -> dict[str, Any]:
    start = max(0.0, words[0]["start"] - pad_s)
    end = words[-1]["end"] + pad_s
    verbatim_text = " ".join(w["w"] for w in words)
    return {
        "clip_id": f"{group_id}_{k}",
        "video_id": video_id,
        "start": round(start, 2),
        "end": round(end, 2),
        "speaker": speaker,
        "speaker_confidence": None,
        "verbatim_text": verbatim_text,
        "display_text": verbatim_text,
        "question_context": None,
        "transcript_hash": compute_clip_hash(verbatim_text),
        "has_disputed_words": any(w.get("disputed") for w in words),
        "parent_id": group_id,
    }


def build_clips_from_labelled_words(
    words: list[dict[str, Any]],
    video_id: str,
    *,
    max_unknown_gap_s: float = _MAX_UNKNOWN_GAP_S,
    max_unknown_words: int = _MAX_UNKNOWN_WORDS,
    min_words: int = _MIN_CLIP_WORDS,
    parent_max_s: float = _PARENT_MAX_S,
    child_target_words: tuple[int, int] = _CHILD_TARGET_WORDS,
    pad_s: float = _PAD_S,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build sentence-bounded teacher clips from per-word speaker labels.

    Root-causes the offline pilot's fragment problem (see run_clips.py):
    that builder starts a new clip at every '?' flicker and cuts children
    every 150 words regardless of sentence ends. Here a run absorbs short
    unknown-label flicker, and every cut -- parent and child -- lands after
    a sentence end when one is available, else the largest pause.

    A parent of `child_target_words[1]` words or fewer is emitted alone (no
    identical child, so no duplicate points downstream); a longer parent is
    additionally split into ~100-200-word children sharing its group/parent_id.

    Returns (clips, stats) where stats tracks runs found, clips emitted,
    clips dropped for being under `min_words`, unknown-gaps merged into a
    run, and how many cuts landed on a sentence end vs. a pause.
    """
    stats = {
        "runs": 0,
        "clips": 0,
        "dropped_short": 0,
        "merged_unknown_gaps": 0,
        "cut_at_sentence": 0,
        "cut_at_pause": 0,
        "dropped_mid_sentence_at_flip": 0,
    }
    # ponytail: S1 turn-start prefix recovery — fixes mid-sentence heads without an LLM call
    if relabel_turn_start_prefixes is not None and words:
        words = relabel_turn_start_prefixes(words)

    runs = _build_teacher_runs(words, max_unknown_gap_s, max_unknown_words, stats)
    stats["runs"] = len(runs)

    clips: list[dict[str, Any]] = []
    parent_n = 0
    for teacher_label, run_words, ends_at_flip in runs:
        speaker = _RUN_TEACHER_LABELS[teacher_label]
        for parent_words in _split_run(
            run_words, _duration_fits(parent_max_s), stats, ends_at_flip
        ):
            parent_n += 1
            if len(parent_words) < min_words:
                stats["dropped_short"] += 1
                continue

            group_id = f"{video_id}_v2_p{parent_n}"
            clips.append(_make_run_clip(parent_words, video_id, speaker, group_id, 0, pad_s))

            if len(parent_words) > child_target_words[1]:
                for k, child_words in enumerate(
                    _split_run(
                        parent_words, _word_count_fits(child_target_words[1]), stats, ends_at_flip
                    ),
                    start=1,
                ):
                    if len(child_words) < min_words:
                        stats["dropped_short"] += 1
                        continue
                    clips.append(_make_run_clip(child_words, video_id, speaker, group_id, k, pad_s))

    stats["clips"] = len(clips)
    return clips, stats


def _clips_v2_self_check() -> None:
    words = [
        {"w": "Suffering", "start": 0.0, "end": 0.3, "spk": "K"},
        {"w": "is", "start": 0.3, "end": 0.5, "spk": "K"},
        {"w": "not", "start": 0.5, "end": 0.7, "spk": "K"},
        {"w": "a", "start": 0.7, "end": 0.8, "spk": "K"},
        {"w": "fact.", "start": 0.8, "end": 1.1, "spk": "K"},
        {"w": "question", "start": 1.2, "end": 1.6, "spk": "O"},
        {"w": "It", "start": 1.7, "end": 1.8, "spk": "K"},
        {"w": "is", "start": 1.8, "end": 1.9, "spk": "K"},
        {"w": "a", "start": 1.9, "end": 2.0, "spk": "K"},
        {"w": "perception.", "start": 2.0, "end": 2.5, "spk": "K"},
    ]
    clips, stats = build_clips_from_labelled_words(words, "self_check_vid", min_words=3)
    assert stats["runs"] == 2
    assert len(clips) == 2
    assert all("question" not in c["verbatim_text"] for c in clips)
    assert clips[0]["transcript_hash"] == compute_clip_hash(clips[0]["verbatim_text"])


def compute_clip_hash(verbatim_text: str) -> str:
    """Compute deterministic SHA-256 over the exact clip text.

    No whitespace normalization here -- the clip builder (`_finalize_clip`
    below) already joins segment texts with a single space before calling
    this, and the serving-time check must hash that same exact string to
    agree. Normalizing again here would silently diverge from both.
    """
    return hashlib.sha256(verbatim_text.encode("utf-8")).hexdigest()


def apply_speaker_attribution_to_segments(
    segments: list[dict[str, Any]],
    speaker_windows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Map time-window speaker labels onto transcript segments.

    Args:
        segments: list of canonical segment dicts with start, end, text.
        speaker_windows: list of dicts with t_start, t_end, speaker ("P", "K", "O", "?").

    Returns:
        Updated segments with speaker_evidence populated.
    """
    updated: list[dict[str, Any]] = []

    for seg in segments:
        s_mid = (seg.get("start", 0.0) + seg.get("end", 0.0)) / 2.0
        best_spk = "?"
        best_dist = float("inf")

        for win in speaker_windows:
            w_mid = (win.get("t_start", 0.0) + win.get("t_end", 0.0)) / 2.0
            dist = abs(s_mid - w_mid)
            if dist < best_dist:
                best_dist = dist
                best_spk = win.get("speaker", "?")

        seg_copy = dict(seg)
        spk_evidence = dict(seg_copy.get("speaker_evidence") or {})

        if best_spk in ("P", "K"):
            spk_evidence["detected_speaker"] = TEACHER_NAME_MAP[best_spk]
            spk_evidence["speaker_identity_source"] = "diarization"
            spk_evidence["speaker_role"] = "teacher"
            spk_evidence["speaker_role_source"] = "diarization"
            spk_evidence["confidence"] = 0.95
            spk_evidence["confidence_kind"] = "heuristic"
        elif best_spk == "O":
            spk_evidence["detected_speaker"] = TEACHER_NAME_MAP["O"]
            spk_evidence["speaker_identity_source"] = "diarization"
            spk_evidence["speaker_role"] = "questioner"
            spk_evidence["speaker_role_source"] = "diarization"
            spk_evidence["confidence"] = 0.90
            spk_evidence["confidence_kind"] = "heuristic"
        else:
            spk_evidence["detected_speaker"] = None
            spk_evidence["speaker_identity_source"] = "unknown"
            spk_evidence["speaker_role"] = "unknown"
            spk_evidence["speaker_role_source"] = "unknown"

        seg_copy["speaker_evidence"] = spk_evidence
        updated.append(seg_copy)

    return updated


def extract_quotable_clips(
    segments: list[dict[str, Any]],
    video_id: str,
    min_duration_s: float = 3.0,
    max_duration_s: float = 60.0,
    padding_s: float = 0.20,
) -> list[dict[str, Any]]:
    """
    Extract pure teacher speech turns, excluding host words, snapped to turn bounds.

    Returns:
        List of certified clip dictionaries with deterministic clip_id and transcript_hash.
    """
    clips: list[dict[str, Any]] = []
    current_run: list[dict[str, Any]] = []
    current_speaker: Optional[str] = None

    for seg in segments:
        spk_meta = seg.get("speaker_evidence") or {}
        role = spk_meta.get("speaker_role")
        teacher = spk_meta.get("detected_speaker")

        # Exclude host, questioners, or unknown intervals
        if role != "teacher" or not teacher:
            if current_run:
                _finalize_clip(
                    current_run,
                    current_speaker,
                    video_id,
                    min_duration_s,
                    max_duration_s,
                    padding_s,
                    clips,
                )
                current_run = []
                current_speaker = None
            continue

        if current_speaker is None or teacher == current_speaker:
            current_speaker = teacher
            current_run.append(seg)
        else:
            _finalize_clip(
                current_run,
                current_speaker,
                video_id,
                min_duration_s,
                max_duration_s,
                padding_s,
                clips,
            )
            current_speaker = teacher
            current_run = [seg]

    if current_run:
        _finalize_clip(
            current_run, current_speaker, video_id, min_duration_s, max_duration_s, padding_s, clips
        )

    return clips


def _piece_bounds(piece: list[dict[str, Any]], padding_s: float) -> tuple[float, float, float]:
    """Return (padded_start, padded_end, padded_duration) for a segment piece."""
    start = max(0.0, float(piece[0].get("start", 0.0)) - padding_s)
    end = float(piece[-1].get("end", 0.0)) + padding_s
    return start, end, end - start


def _split_run_by_largest_gap(
    run: list[dict[str, Any]], max_dur: float, padding_s: float
) -> list[list[dict[str, Any]]]:
    """Recursively split a speaker run at its largest inter-segment gap until
    every piece's padded duration is <= max_dur.

    Teachers speak uninterrupted for minutes; a run exceeding max_dur is
    split rather than dropped, so no teaching is lost. The split is at the
    segment boundary, so pieces partition `run` exactly -- no segment is
    ever duplicated or omitted.
    """
    if not run:
        return []
    _, _, duration = _piece_bounds(run, padding_s)
    if duration <= max_dur or len(run) < 2:
        return [run]

    split_idx = max(
        range(1, len(run)),
        key=lambda i: float(run[i].get("start", 0.0)) - float(run[i - 1].get("end", 0.0)),
    )
    left, right = run[:split_idx], run[split_idx:]
    return _split_run_by_largest_gap(left, max_dur, padding_s) + _split_run_by_largest_gap(
        right, max_dur, padding_s
    )


def _merge_short_pieces(
    pieces: list[list[dict[str, Any]]], min_dur: float, padding_s: float
) -> list[list[dict[str, Any]]]:
    """Merge any piece whose padded duration is below min_dur into its
    neighbour, so a split never produces a fragment too short to be a
    usable clip."""
    if len(pieces) <= 1:
        return pieces

    merged: list[list[dict[str, Any]]] = [list(pieces[0])]
    for piece in pieces[1:]:
        _, _, prev_dur = _piece_bounds(merged[-1], padding_s)
        if prev_dur < min_dur:
            merged[-1] = merged[-1] + piece
        else:
            merged.append(list(piece))

    _, _, last_dur = _piece_bounds(merged[-1], padding_s)
    if last_dur < min_dur and len(merged) > 1:
        merged[-2] = merged[-2] + merged[-1]
        merged.pop()

    return merged


def _emit_clip(
    piece: list[dict[str, Any]],
    speaker: str,
    video_id: str,
    min_dur: float,
    max_dur: float,
    padding_s: float,
    out_clips: list[dict[str, Any]],
) -> None:
    start, end, duration = _piece_bounds(piece, padding_s)
    # max_dur is the split target, not a reject rule: a piece still over it is a
    # single unsplittable segment (or a merged fragment), and dropping it loses teaching.
    if duration < min_dur:
        return

    verbatim_text = " ".join(
        (s.get("verbatim_text") or s.get("text") or "").strip()
        for s in piece
        if (s.get("verbatim_text") or s.get("text") or "").strip()
    )
    if not verbatim_text:
        return

    clip_hash = compute_clip_hash(verbatim_text)
    clip_id = f"{video_id}_{int(start)}_{int(end)}"

    out_clips.append(
        {
            "clip_id": clip_id,
            "video_id": video_id,
            "speaker": speaker,
            "start": round(start, 2),
            "end": round(end, 2),
            "duration_seconds": round(duration, 2),
            "verbatim_text": verbatim_text,
            "transcript_hash": clip_hash,
        }
    )


def _finalize_clip(
    run: list[dict[str, Any]],
    speaker: Optional[str],
    video_id: str,
    min_dur: float,
    max_dur: float,
    padding_s: float,
    out_clips: list[dict[str, Any]],
) -> None:
    if not run or not speaker:
        return

    pieces = _merge_short_pieces(
        _split_run_by_largest_gap(run, max_dur, padding_s), min_dur, padding_s
    )
    for piece in pieces:
        _emit_clip(piece, speaker, video_id, min_dur, max_dur, padding_s, out_clips)


if __name__ == "__main__":
    _clips_v2_self_check()
    print("self-check OK")
