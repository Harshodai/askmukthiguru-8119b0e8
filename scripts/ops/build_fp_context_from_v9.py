#!/usr/bin/env python3
"""Build the fp-context-v1 parent/child index from an existing clip collection.

Why this exists: the plan's phase C asks for a rebuild from ASR output with word
timings. This workspace has no ASR JSON and no teacher audio, so this script does
the only thing that is verifiable here — it derives word offsets by *locating*
each stored clip inside its own transcript file, and it refuses (quarantines) any
clip whose text cannot be located with a high similarity score. Nothing is
invented: text, hashes, timings, speaker status, and rights come from the stored
payload; only the word-offset coordinate is derived, and the derivation is
recorded per clip in the report.

Two modes, both explicit:

``--dry-run`` (default)
    Emit a JSONL manifest plus a JSON report. No Qdrant write of any kind.

``--apply``
    Create/refresh ``--target-collection`` (never the source collection) and
    write parents + children. Child vectors are copied from the source points
    rather than recomputed; the text is unchanged, so re-embedding would only
    add drift, but the producing model is not recorded in v9 payloads and is
    therefore left unstated. Parents are payload-only. A snapshot of the target
    collection is requested afterwards so a rollback artifact exists.

Usage:
    python -m scripts.ops.build_fp_context_from_v9 --dry-run \
        --manifest .work/fp_context/manifest.jsonl --report .work/fp_context/report.json
    python -m scripts.ops.build_fp_context_from_v9 --apply \
        --target-collection fp_context_v1_local
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _resolve_backend_root() -> Path:
    """Directory that holds the ``domain``/``ingest`` packages.

    The canonical copy lives at ``backend/scripts/ops/`` (this file's
    ``parents[2]``). The byte-identical repo-root copy at ``scripts/ops/``
    resolves ``parents[2]`` to the repository root instead, so the backend
    directory is found by looking for the packages it actually imports.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "domain" / "first_person_context.py").is_file():
            return candidate
        nested = candidate / "backend"
        if (nested / "domain" / "first_person_context.py").is_file():
            return nested
    raise RuntimeError(f"cannot locate the backend package root from {here}")


_BACKEND_ROOT = _resolve_backend_root()
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from domain.first_person_context import (
    AnswerRole,
    BoundaryStatus,
    CompletenessStatus,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
    make_parent_unit_id,
    make_source_span_id,
)
from ingest.verbatim.asr_cleaner import asr_cleaner_flags, clean_verbatim_text
from ingest.verbatim.boundaries import boundary_defects
from ingest.verbatim.gates import script_and_loop_problem

DEFAULT_CORPUS_VERSION = "fp-context-transcript-v1"
DEFAULT_MIN_ALIGNMENT = 0.85
# Method recorded for a span whose speaker an ECAPA verdict confirmed.
VOICE_METHOD_DEFAULT = "ecapa_voxceleb_centroid_v1"
# Reported only, never blocking: the data-quality scorecard
# (scripts/ops/fp_data_quality_scorecard.py) treats a span outside 8-60 s as out of band.
SPAN_MAX_SECONDS_REPORTED = 60.0
PROBE_WORDS = 6
_FRAGMENT_STARTS = frozenset(
    {"and", "but", "or", "so", "because", "which", "that", "who", "whose", "it", "this", "these"}
)

_NORM_RE = re.compile(r"[^a-z0-9 ]")


def _resolve_repo_root() -> Path:
    """Repository root, independent of which copy of this file is running."""
    return _BACKEND_ROOT.parent


_REPO_ROOT = _resolve_repo_root()


def _norm(text: str) -> str:
    # Normalize numbers (e.g. 40 ,000 -> 40000), hyphens/dashes to space, quotes, and common phonetics
    t = re.sub(r"(\d+)\s*,\s*(\d+)", r"\1\2", text.lower())
    t = re.sub(r"[-—–/]", " ", t)
    t = re.sub(r"[\x27\u2018\u2019\u201c\u201d]", "", t)
    t = re.sub(r"\bshri\b", "sri", t)
    t = re.sub(r"\b(acom|acum|aekam)\b", "ekam", t)
    t = re.sub(r"\bkrishna\s+ji\b", "krishnaji", t)
    t = re.sub(r"\bpreetha\s+ji\b", "preethaji", t)
    t = re.sub(r"\b(o\s*and\s*o|o&o|ono)\b", "oo", t)
    t = re.sub(r"\bpeacemakers\b", "peace makers", t)
    t = re.sub(r"\bpeacemaker\b", "peace maker", t)
    t = re.sub(r"\bwelltested\b", "well tested", t)
    t = re.sub(r"\bwellbeing\b", "well being", t)
    t = re.sub(r"\bsoulsync\b", "soul sync", t)
    return _NORM_RE.sub("", t).strip()


def _norm_words(text: str) -> list[str]:
    return _norm(text).split()


def transcript_words(path: Path) -> list[str] | None:
    """Words of the transcript body, in order. ``None`` when the file is absent."""
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8", errors="replace")
    body = raw.split("## Transcript", 1)[1] if "## Transcript" in raw else raw
    body = re.split(r"\n## ", body)[0]
    return re.findall(r"\S+", re.sub(r"\s+", " ", body).strip())


def _best_window(
    clip_words: list[str], transcript: list[str], *, probe: int = PROBE_WORDS
) -> tuple[int, float]:
    """Locate ``clip_words`` in ``transcript``; return (word_start, similarity)."""
    if not clip_words or not transcript:
        return -1, 0.0
    n = len(clip_words)
    if n < probe:
        # Too short for a probe: require literal containment of the whole clip.
        for index in range(len(transcript) - n + 1):
            if transcript[index : index + n] == clip_words:
                return index, 1.0
        return -1, 0.0

    head = clip_words[:probe]
    best_start, best_ratio = -1, 0.0
    for index in range(len(transcript) - probe + 1):
        if transcript[index : index + probe] != head:
            continue
        window = transcript[index : index + n]
        ratio = difflib.SequenceMatcher(None, clip_words, window).ratio()
        if ratio > best_ratio:
            best_start, best_ratio = index, ratio
            if ratio >= 0.98:
                return best_start, best_ratio

    if best_ratio >= 0.95:
        return best_start, best_ratio

    # Enhanced fallback: multi-anchor candidate search across the clip
    candidate_starts: set[int] = set()
    if best_start >= 0:
        candidate_starts.add(best_start)

    anchor_lens = [5, 4, 3] if n >= 5 else [n]
    for k in anchor_lens:
        offsets = list(range(min(12, max(1, n - k + 1))))
        if n > 12:
            for frac in [0.2, 0.33, 0.5, 0.66, 0.8]:
                pos = int(n * frac)
                offsets.extend([pos - 1, pos, pos + 1])
            offsets.extend([n - k - 1, n - k])
        offsets = sorted(set(o for o in offsets if 0 <= o <= n - k))

        for off in offsets:
            anchor = clip_words[off : off + k]
            for idx in range(len(transcript) - k + 1):
                if transcript[idx : idx + k] == anchor:
                    cand = idx - off
                    if -10 <= cand < len(transcript):
                        candidate_starts.add(max(0, cand))
        if len(candidate_starts) >= 3:
            break

    # Slide window length and start position around candidate starts
    delta_range = [0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5, -6, 6, -8, 8, -10, 10, -15, 15]
    for start in sorted(candidate_starts):
        for delta in delta_range:
            end = start + n + delta
            if end <= start or end > len(transcript):
                continue
            window = transcript[start:end]
            ratio = difflib.SequenceMatcher(None, clip_words, window).ratio()
            if ratio > best_ratio:
                best_start, best_ratio = start, ratio
                if ratio >= 0.98:
                    return best_start, best_ratio

    return best_start, best_ratio


def _word_source(
    video_id: str, transcripts_dir: Path, asr_dir: Path | None, asr_model: str
) -> tuple[list[str], list[str], str] | None:
    """ASR word timings when present, else transcript words. Never invents either."""
    if asr_dir is not None:
        candidate = asr_dir / asr_model / f"{video_id}.json"
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                pairs = []
                for word in data.get("words", []):
                    text = str(word.get("word") or "").strip()
                    for n in _norm_words(text):
                        if n:
                            pairs.append((text, n))
                if pairs:
                    return [p[0] for p in pairs], [p[1] for p in pairs], "asr"
            except (ValueError, KeyError, TypeError):
                pass
    raw = transcript_words(transcripts_dir / f"{video_id}.md")
    if raw is None:
        return None
    pairs: list[tuple[str, str]] = []
    for word in raw:
        sub_words = re.findall(r"[^\s—–\-/]+", word)
        if len(sub_words) > 1:
            for sub_w in sub_words:
                for n in _norm_words(sub_w):
                    if n:
                        pairs.append((sub_w, n))
        else:
            for n in _norm_words(word):
                if n:
                    pairs.append((word, n))
    if not pairs:
        return None
    return [p[0] for p in pairs], [p[1] for p in pairs], "transcript"


def _boundary_status(clip_text: str) -> BoundaryStatus:
    defects = boundary_defects(clip_text.split())
    return BoundaryStatus.UNCERTAIN if defects else BoundaryStatus.VERIFIED


def _completeness_status(clip_text: str) -> CompletenessStatus:
    stripped = clip_text.strip()
    if not stripped:
        return CompletenessStatus.UNCERTAIN
    first = stripped.split()[0]
    first_word = _norm(first).strip()
    starts_lower = first[:1].islower()
    if starts_lower and first_word in _FRAGMENT_STARTS:
        return CompletenessStatus.FRAGMENT
    return CompletenessStatus.COMPLETE


def _speaker_role(payload: dict[str, Any]) -> SpeakerRole:
    kind = str(payload.get("provenance_kind") or "")
    if kind == ProvenanceKind.HOST_QUESTION.value:
        return SpeakerRole.HOST
    return SpeakerRole.GURU


def _source_url(payload: dict[str, Any], video_id: str) -> str:
    url = str(payload.get("source_url") or payload.get("video_url") or "").strip()
    return url or f"https://www.youtube.com/watch?v={video_id}"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ledger_entry(point: dict[str, Any], stage: str, before: str, after: str) -> dict[str, str]:
    """One hash-only edit-ledger row (no teacher text)."""
    return {
        "source_point_id": str(point.get("id") or ""),
        "stage": stage,
        "before_sha256": _sha256_text(before),
        "after_sha256": _sha256_text(after),
    }


def _is_container(
    outer: int, inner: int, rows: list, row_words: list[list[str]]
) -> bool:
    p_a, p_b = rows[outer][0], rows[inner][0]
    s_a, e_a = int(p_a.get("start_ms") or 0), int(p_a.get("end_ms") or 0)
    s_b, e_b = int(p_b.get("start_ms") or 0), int(p_b.get("end_ms") or 0)
    if not (s_a <= s_b and e_a >= e_b and (e_a - s_a) > (e_b - s_b)):
        return False
    outer_words, inner_words = row_words[outer], row_words[inner]
    if len(inner_words) >= len(outer_words):
        return False
    return any(
        outer_words[i : i + len(inner_words)] == inner_words
        for i in range(len(outer_words) - len(inner_words) + 1)
    )


def build(
    points: Iterable[dict[str, Any]],
    *,
    transcripts_dir: Path,
    corpus_version: str = DEFAULT_CORPUS_VERSION,
    min_alignment: float = DEFAULT_MIN_ALIGNMENT,
    speaker_verdicts: dict[str, Any] | None = None,
    asr_dir: Path | None = None,
    asr_model: str = "large-v3",
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    """Return (manifest payloads, report, source vectors keyed by old point id).

    ``speaker_verdicts`` (from verify_speakers_ecapa) is the ONLY thing that sets
    ``speaker_verified`` on a span, and it records the method with it. A source
    payload that merely carries ``speaker_verified=True`` (a v9 clip-level label with
    no span-level verdict behind it) is still admitted, but as ``speaker_verified=False``
    with no method, and counted in ``report["quality_counters"]["speaker_label_only"]``. Before this
    change every span was written ``speaker_verified=True`` and the method was set
    only for spans that were NOT already labelled, i.e. inverted: 732 of 2,737 live v10
    spans carry the flag with no method (docs/audits/DATA_QUALITY_ASSESSMENT_2026-10-25.md).
    Absence of evidence must never become ``speaker_verified=true`` (public-release
    blocker B1). ``asr_dir`` switches word offsets from transcript locations to real ASR
    word timings for the videos that have them.
    """
    quarantined: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    by_guru: Counter[str] = Counter()
    alignments: list[float] = []
    verdict_items = (speaker_verdicts or {}).get("items", {})
    alignment_source: Counter[str] = Counter()
    # Report-only data-quality counters (see the scorecard); none of them blocks a span.
    quality: Counter[str] = Counter()
    # D9: every built span is run through the release-grade contract. Defects are
    # counted per reason code, never "fixed" by dropping the span here — the
    # scorecard decides release grade, and a silent drop would shrink the
    # candidate set instead of measuring it.
    release_grade_defects: Counter[str] = Counter()
    # Hash-only evidence of where a stored clip differs from its source. This is
    # the beginning of the per-span edit ledger the data-quality assessment asks
    # for (fix 1): which span, which stage's difference, and the hashes of both
    # sides, so a human can audit the audio for exactly these spans. It carries
    # no teacher text (repo is public per L-PUBLIC-REPO-1) and never edits text.
    edit_ledger: list[dict[str, str]] = []

    words_cache: dict[str, tuple[list[str], list[str]] | None] = {}
    groups: dict[tuple[str, str, str], list[tuple[dict[str, Any], int, int, str]]] = {}

    total = 0
    for point in points:
        payload = dict(point.get("payload") or {})
        total += 1
        guru_id = str(payload.get("guru_id") or payload.get("teacher_id") or "").strip()
        video_id = str(payload.get("video_id") or "").strip()
        clip_text = str(payload.get("verbatim_text") or "").strip()
        parent_key = str(payload.get("parent_id") or payload.get("group_id") or video_id)
        verdict = verdict_items.get(str(point.get("id"))) or {}
        voice_verified = verdict.get("verified") is True
        cleaner_flags = asr_cleaner_flags(clip_text)
        quarters = [
            ("guru_unresolved", not guru_id),
            ("video_unresolved", not video_id),
            ("empty_clip_text", not clip_text),
            ("asr_script_garbage", script_and_loop_problem(clip_text) is not None),
            # D2: the cleaner's deletion rules are quarantine reasons, not edits.
            # This build never rewrites text (that would move the hash and the id),
            # so a flagged span is quarantined and the flag is the recorded reason.
            ("asr_cleaner_flags", bool(cleaner_flags)),
            ("rights_not_cleared", payload.get("rights_cleared") is not True),
            (
                "quality_not_verified",
                str(payload.get("quality_status") or "") != "verified_verbatim",
            ),
            (
                "transcript_hash_invalid",
                not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("transcript_hash") or "")),
            ),
            (
                "speaker_unverified",
                payload.get("speaker_verified") is not True and not voice_verified,
            ),
            # An explicit refusal beats an inherited label: never serve a span as
            # verified when the span-level check said no. Listed after
            # speaker_unverified so an unlabelled refused clip keeps its old reason.
            ("speaker_verdict_refused", verdict.get("verified") is False),
        ]
        blocked = next((name for name, hit in quarters if hit), None)
        if blocked:
            quarantined[blocked] += 1
            if blocked == "asr_cleaner_flags":
                for flag in cleaner_flags:
                    reasons[f"asr_cleaner_{flag}"] += 1
            continue

        if video_id not in words_cache:
            words_cache[video_id] = _word_source(video_id, transcripts_dir, asr_dir, asr_model)
        cached = words_cache[video_id]
        if cached is None:
            quarantined["transcript_missing"] += 1
            continue
        raw_words, norm_transcript, source = cached

        clip_words = _norm_words(clip_text)
        word_start, ratio = _best_window(clip_words, norm_transcript)
        if word_start < 0 or ratio < min_alignment:
            quarantined["clip_text_not_locatable"] += 1
            reasons[f"alignment_below_{min_alignment:.2f}"] += 1
            continue

        word_end = word_start + max(1, len(clip_words))
        window_text = " ".join(raw_words[word_start : word_start + len(clip_words)])
        # Carry the per-span voice evidence to the build step below.
        payload["_voice_verified"] = voice_verified
        payload["_voice_method"] = str(verdict.get("method") or VOICE_METHOD_DEFAULT)
        if payload.get("speaker_verified") is True and not voice_verified:
            quality["speaker_label_only"] += 1
        if _norm_words(window_text) != clip_words:
            # Stored clip words differ from the transcript they were located in. The
            # text is kept as stored (never edited here), but no per-span record says
            # which earlier stage changed the words, so the count is surfaced.
            quality["text_differs_from_transcript_window"] += 1
            edit_ledger.append(
                _ledger_entry(
                    point,
                    "stored_text_vs_asr_window",
                    clip_text,
                    window_text,
                )
            )
        if clean_verbatim_text(clip_text) != clip_text:
            # FP invariant 13: text must pass asr_cleaner before it is hashed. Changing
            # it here would change transcript_hash and the point id, so only count it.
            quality["asr_clean_would_change"] += 1
            edit_ledger.append(
                _ledger_entry(
                    point,
                    "asr_cleaner_pending",
                    clip_text,
                    clean_verbatim_text(clip_text),
                )
            )
        if (int(payload.get("end_ms") or 0) - int(payload.get("start_ms") or 0)) / 1000.0 > (
            SPAN_MAX_SECONDS_REPORTED
        ):
            quality["span_over_max_seconds"] += 1
        # Kept-span statistics are accumulated after the container drop below, so
        # ``by_guru_kept``/``alignment`` describe the manifest, not the candidates.
        groups.setdefault((guru_id, video_id, parent_key), []).append(
            (payload, word_start, word_end, window_text, round(ratio, 4), source)
        )

    manifest: list[dict[str, Any]] = []
    kept_spans = 0
    for (guru_id, video_id, _parent_key), rows in sorted(groups.items()):
        rows.sort(key=lambda item: (int(item[0].get("start_ms") or 0), item[1]))

        # Drop enclosing parent containers when child clips exist in the same group (D6).
        # Text containment is required as well as time containment: an overlap alone
        # (two different passages in the same window) is not a parent/child pair, and
        # dropping on time alone would delete unrelated spans.
        row_words = [_norm_words(str(row[0].get("verbatim_text") or "")) for row in rows]

        filtered_rows = []
        for i, row_a in enumerate(rows):
            if any(_is_container(i, j, rows, row_words) for j in range(len(rows)) if j != i):
                quality["container_dropped"] += 1
                continue
            filtered_rows.append(row_a)
        rows = filtered_rows
        if not rows:
            continue

        parent_unit_id = make_parent_unit_id(
            guru_id=guru_id,
            video_id=video_id,
            corpus_version=corpus_version,
            first_word_index=rows[0][1],
            last_word_index=rows[-1][2],
        )
        spans: list[SourceSpan] = []
        seen_span_ids: set[str] = set()
        for payload, word_start, word_end, window_text, ratio, source in rows:
            verbatim = str(payload["verbatim_text"]).strip()
            transcript_hash = str(payload["transcript_hash"]).strip()
            span_id = make_source_span_id(
                guru_id=guru_id,
                video_id=video_id,
                corpus_version=corpus_version,
                word_start=word_start,
                word_end=word_end,
                transcript_hash=transcript_hash,
            )
            if span_id in seen_span_ids:
                quarantined["duplicate_span"] += 1
                continue
            seen_span_ids.add(span_id)
            alignments.append(ratio)
            alignment_source[source] += 1
            by_guru[guru_id] += 1
            index = len(spans)
            spans.append(
                SourceSpan(
                    corpus_version=corpus_version,
                    guru_id=guru_id,
                    video_id=video_id,
                    source_asset_id=video_id,
                    source_span_id=span_id,
                    parent_unit_id=parent_unit_id,
                    turn_id=f"{parent_unit_id[:12]}:t{index}",
                    turn_index=index,
                    source_span_index=index,
                    start_ms=int(payload["start_ms"]),
                    end_ms=int(payload["end_ms"]),
                    word_start=word_start,
                    word_end=word_end,
                    speaker_id=str(payload.get("speaker") or guru_id),
                    speaker_role=_speaker_role(payload),
                    # Only a span-level verdict makes a span verified, and the method is
                    # recorded with it. A legacy clip label alone stays False/None.
                    speaker_verified=bool(payload["_voice_verified"]),
                    voice_verification_method=(
                        payload["_voice_method"] if payload["_voice_verified"] else None
                    ),
                    asr_engine="faster_whisper" if source == "asr" else None,
                    asr_model_version=asr_model if source == "asr" else None,
                    source_transcript_text=window_text or verbatim,
                    verbatim_text=verbatim,
                    transcript_hash=transcript_hash,
                    source_text_hash=clip_text_hash(verbatim),
                    boundary_status=_boundary_status(verbatim),
                    completeness_status=_completeness_status(verbatim),
                    rights_cleared=True,
                    caption_status="auto",
                    provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
                    previous_span_id=None,
                    next_span_id=None,
                    answer_role=AnswerRole.DIRECT,
                    source_url=_source_url(payload, video_id),
                    quality_status=str(payload.get("quality_status") or "verified_verbatim"),
                    # text_origin and source_artifact_sha256 stay None: the payload
                    # is the source here, and it records neither where its text came
                    # from nor an artifact hash (guessing would assert provenance).
                )
            )
        # link neighbours inside the parent
        spans = [
            span.model_copy(
                update={
                    "previous_span_id": spans[i - 1].source_span_id if i else None,
                    "next_span_id": spans[i + 1].source_span_id if i + 1 < len(spans) else None,
                }
            )
            for i, span in enumerate(spans)
        ]
        for span in spans:
            for defect in span.validate_release_grade():
                release_grade_defects[defect.split(":", 1)[0]] += 1
        parent = ParentUnit(
            corpus_version=corpus_version,
            guru_id=guru_id,
            video_id=video_id,
            parent_unit_id=parent_unit_id,
            ordered_source_span_ids=tuple(s.source_span_id for s in spans),
            start_ms=spans[0].start_ms,
            end_ms=spans[-1].end_ms,
            parent_text_hash=clip_text_hash(" ".join(s.verbatim_text for s in spans)),
            speaker_ids=tuple(sorted({s.speaker_id for s in spans})),
            speaker_continuity=len({s.speaker_id for s in spans}) == 1,
            boundary_status=(
                BoundaryStatus.UNCERTAIN
                if any(s.boundary_status == BoundaryStatus.UNCERTAIN for s in spans)
                else spans[0].boundary_status
            ),
            completeness_status=(
                CompletenessStatus.COMPLETE
                if all(s.completeness_status == CompletenessStatus.COMPLETE for s in spans)
                else CompletenessStatus.UNCERTAIN
            ),
        )
        kept_spans += len(spans)
        manifest.extend(span.to_payload() for span in spans)
        manifest.append(parent.to_payload())

    alignment_sorted = sorted(alignments)
    report = {
        "corpus_version": corpus_version,
        "total_source_points": total,
        "derived_span_ids": kept_spans,
        "parents": sum(1 for row in manifest if row["record_type"] == "parent_unit"),
        "quarantined": dict(quarantined),
        "quarantine_reasons": dict(reasons),
        "by_guru_kept": dict(by_guru),
        "alignment_source": dict(alignment_source),
        "quality_counters": dict(quality),
        "release_grade_defects": dict(release_grade_defects),
        "text_edit_ledger": edit_ledger,
        "speaker_verified_by_voice": sum(
            1
            for row in manifest
            if row.get("record_type") == "retrieval_child" and row.get("voice_verification_method")
        ),
        "alignment": {
            "threshold": min_alignment,
            "count": len(alignment_sorted),
            "min": alignment_sorted[0] if alignment_sorted else None,
            "p10": alignment_sorted[len(alignment_sorted) // 10] if alignment_sorted else None,
            "median": alignment_sorted[len(alignment_sorted) // 2] if alignment_sorted else None,
        },
        "derivation": (
            "word_start/word_end are the position of the stored clip text inside "
            "transcripts/<video_id>.md, accepted only above the alignment "
            "threshold. Timings, hashes and rights are copied from the source payload; "
            "speaker_verified is set only by a span-level verdict (a legacy clip label "
            "alone is carried as unverified); no text is generated."
        ),
    }
    return manifest, report, {}


def _load_points(qdrant_url: str, collection: str, *, with_vectors: bool) -> list[dict[str, Any]]:
    from qdrant_client import QdrantClient

    client = QdrantClient(url=qdrant_url)
    out: list[dict[str, Any]] = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=with_vectors,
        )
        out.extend(
            {"id": str(p.id), "payload": dict(p.payload or {}), "vector": p.vector} for p in batch
        )
        if offset is None:
            break
    return out


def _apply(
    manifest: list[dict[str, Any]],
    points: list[dict[str, Any]],
    *,
    qdrant_url: str,
    target: str,
    recreate: bool = False,
) -> dict[str, Any]:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        PayloadSchemaType,
        PointStruct,
        SparseVectorParams,
        VectorParams,
    )

    from services.first_person_context_store import (
        parent_point_id,
        point_id_for_record,
    )

    client = QdrantClient(url=qdrant_url)
    existing = {c.name for c in client.get_collections().collections}
    if target in existing:
        if recreate:
            client.delete_collection(target)
        else:
            raise SystemExit(
                f"Refusing to write to existing collection {target!r} (pass --recreate to replace)"
            )
    client.create_collection(
        collection_name=target,
        vectors_config={"passage_dense": VectorParams(size=1024, distance=Distance.COSINE)},
        sparse_vectors_config={"passage_sparse": SparseVectorParams()},
    )

    vectors = {point["id"]: point.get("vector") for point in points}
    # old point id -> derived span id, matched on (video, verbatim text, start_ms)
    by_key: dict[tuple[str, str, int], Any] = {}
    for point in points:
        payload = point["payload"]
        key = (
            str(payload.get("video_id")),
            str(payload.get("verbatim_text")),
            int(payload.get("start_ms") or 0),
        )
        by_key[key] = point["id"]

    index_types = {
        "guru_id": PayloadSchemaType.KEYWORD,
        "video_id": PayloadSchemaType.KEYWORD,
        "parent_unit_id": PayloadSchemaType.KEYWORD,
        "record_type": PayloadSchemaType.KEYWORD,
        "rights_cleared": PayloadSchemaType.BOOL,
        "source_span_id": PayloadSchemaType.KEYWORD,
    }
    for field, schema in index_types.items():
        try:
            client.create_payload_index(
                collection_name=target, field_name=field, field_schema=schema, wait=True
            )
        except Exception:  # already exists
            pass

    skipped_span_ids: set[str] = set()
    for row in manifest:
        if row["record_type"] == "parent_unit":
            continue
        key = (str(row["video_id"]), str(row["verbatim_text"]), int(row["start_ms"]))
        old_id = by_key.get(key)
        vector = vectors.get(old_id) if old_id else None
        if not isinstance(vector, dict) or "passage_dense" not in vector:
            skipped_span_ids.add(row["source_span_id"])

    batch: list[PointStruct] = []
    written_children = 0
    written_parents = 0
    missing_vectors = 0
    skipped_parents = 0
    for row in manifest:
        if row["record_type"] == "parent_unit":
            span_ids = row.get("ordered_source_span_ids") or ()
            if any(sid in skipped_span_ids for sid in span_ids):
                skipped_parents += 1
                continue
            batch.append(
                PointStruct(id=parent_point_id(row["parent_unit_id"]), vector={}, payload=row)
            )
            written_parents += 1
            continue
        if row["source_span_id"] in skipped_span_ids:
            missing_vectors += 1
            continue
        key = (str(row["video_id"]), str(row["verbatim_text"]), int(row["start_ms"]))
        old_id = by_key.get(key)
        vector = vectors.get(old_id) if old_id else None
        carried: dict[str, Any] = {"passage_dense": vector["passage_dense"]}
        sparse = vector.get("passage_sparse")
        if sparse:
            carried["passage_sparse"] = sparse
        # D4: embedding_model / embedding_revision / embedded_text_sha256 stay
        # None here on purpose. This vector is *carried over* from the live point,
        # and nothing in a v9 payload records which model or revision produced it,
        # so any value written here would be a guess.
        batch.append(
            PointStruct(id=point_id_for_record(row["source_span_id"]), vector=carried, payload=row)
        )
        written_children += 1
        if len(batch) >= 256:
            client.upsert(collection_name=target, points=batch, wait=True)
            batch = []
    if batch:
        client.upsert(collection_name=target, points=batch, wait=True)

    try:
        snapshot = client.create_snapshot(collection_name=target)
        snapshot_name = getattr(snapshot, "name", None)
    except Exception as exc:  # snapshot API unavailable is reported, not fatal
        snapshot_name = f"unavailable: {exc}"

    info = client.get_collection(target)
    return {
        "target_collection": target,
        "points_count": info.points_count,
        "written_children": written_children,
        "written_parents": written_parents,
        "missing_vectors": missing_vectors,
        "skipped_parents": skipped_parents,
        "snapshot": snapshot_name,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-collection", default="first_person_v9")
    parser.add_argument("--target-collection", default="fp_context_v1_local")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument(
        "--transcripts-dir",
        default=str(_REPO_ROOT / "transcripts"),
        help="Directory of <video_id>.md transcript files (default: repo transcripts/)",
    )
    parser.add_argument("--corpus-version", default=DEFAULT_CORPUS_VERSION)
    parser.add_argument("--min-alignment", type=float, default=DEFAULT_MIN_ALIGNMENT)
    parser.add_argument("--manifest", default=str(_REPO_ROOT / ".work/fp_context/manifest.jsonl"))
    parser.add_argument("--report", default=str(_REPO_ROOT / ".work/fp_context/report.json"))
    parser.add_argument(
        "--speaker-verdicts",
        default=None,
        help="JSON from verify_speakers_ecapa; upgrades speaker_verified only where verified=true",
    )
    parser.add_argument(
        "--asr-dir",
        default=None,
        help="ASR word-timing root (expects <root>/<model>/<video_id>.json); preferred over transcripts",
    )
    parser.add_argument("--asr-model", default="large-v3")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Allow deleting and replacing an existing target collection",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    apply_mode = bool(args.apply) and not args.dry_run
    points = _load_points(args.qdrant_url, args.source_collection, with_vectors=apply_mode)
    verdicts = (
        json.loads(Path(args.speaker_verdicts).read_text(encoding="utf-8"))
        if args.speaker_verdicts
        else None
    )
    manifest, report, _ = build(
        points,
        transcripts_dir=Path(args.transcripts_dir),
        corpus_version=args.corpus_version,
        min_alignment=args.min_alignment,
        speaker_verdicts=verdicts,
        asr_dir=Path(args.asr_dir) if args.asr_dir else None,
        asr_model=args.asr_model,
    )
    report["source_collection"] = args.source_collection
    report["speaker_verdicts"] = args.speaker_verdicts
    report["asr_dir"] = args.asr_dir
    report["transcripts_dir"] = str(args.transcripts_dir)

    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in manifest) + ("\n" if manifest else ""),
        encoding="utf-8",
    )
    if apply_mode:
        report["applied"] = _apply(
            manifest,
            points,
            qdrant_url=args.qdrant_url,
            target=args.target_collection,
            recreate=args.recreate,
        )
    else:
        report["applied"] = None

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
