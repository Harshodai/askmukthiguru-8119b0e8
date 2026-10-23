#!/usr/bin/env python3
"""Rebuild and validate the first-person v10 ASR word coordinates and audio windows.

**Read-only.** This script never writes to Qdrant, never mutates an input
manifest, never changes a payload and never sets ``speaker_verified``. It emits
a **candidate** package (JSONL) and a **quarantine** package (JSONL) plus a
machine-readable summary. Writing the candidate into the collection is a
separate, explicitly authorised step.

Why this exists
---------------
``docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md`` blockers **B2** and
**B3**:

* **B2** — 298 / 2,737 spans fail the citation/audio-window coverage check and
  13 have no overlap between the cited text and the playback window.
* **B3** — only 589 / 2,737 ``word_start``/``word_end`` pairs reproduce the
  cited location in the archived word-timed transcript; 2,107 disagree and 41
  index past the end of the transcript.

Root cause (measured, not assumed): the live v10 collection was built from
**two different transcripts**. ``build_full_corpus_v10.py`` took the *text* from
the markdown display transcript (``transcripts/{video_id}.md``) and the *timings*
from the voted word-timed artifact (``transcripts_B/{video_id}.json``). The two
layers differ in wording (dropped/duplicated words, homophones, restored
casing), so the word index recorded in the payload belongs to the display
layer while the millisecond offsets belong to the voted layer. The recorded
``word_start``/``word_end`` therefore index neither consistently.

What this script does
----------------------
For every v10 child it re-derives, **from the immutable word-timed artifact
only**:

* the normalized transcript word sequence and its normalization version;
* the artifact's own sha256 (the source/transcript hash);
* ``word_start`` / ``word_end`` as indices into that artifact's word list;
* the exact span text (the artifact's words in that range);
* ``source_text_hash`` over that reconstructed text;
* ``audio_start_ms`` / ``audio_end_ms`` measured from the artifact's own word
  timings — never spread across the WAV duration, never copied from the
  legacy v9 clip store;
* a deterministic ``source_span_id`` and the parent/child identity fields.

It then validates the result and quarantines whatever does not survive.

Coordinate space (``fp-coords-v1``)
------------------------------------
``word_start``/``word_end`` are indices into the word list of the timed
artifact named by ``timed_transcript_path``. The artifact's sha256 is the
``transcript_hash`` used in the deterministic id, so the id is derived from the
same artifact that produced the timings. Because this differs from the live
collection's coordinate space, the rebuilt candidate declares a new
``corpus_version`` by default so that a rebuilt id can never collide with a
live id.

Transcription layers
--------------------
The live span text comes from the markdown *display* transcript; the timing
artifact is the *voted* layer. Where the two disagree in wording, the rebuilt
coordinates are still derived from the artifact, but the reconstruction is not
byte-exact. Those spans are classified:

* ``exact`` — the reconstruction reproduces the span text exactly under
  ``fp-norm-unicode-v1``;
* ``variant`` — the reconstruction covers the span text at or above the
  coverage floor but is not exact (an ASR/display wording difference);
* quarantined — everything else.

``--reconstruction-policy exact`` (the default) admits only ``exact`` spans to
the candidate. ``--reconstruction-policy coverage`` also admits ``variant``
spans, each flagged ``transcription_variant``.

Multilingual handling
---------------------
The normalizer is Unicode-aware (NFKC, Unicode-category aware), so Devanagari
and Urdu spans are tokenized and validated like any other text. A span is
never marked unverifiable merely because an ASCII-only checker cannot tokenize
it; the summary reports the ASCII-only count next to the Unicode count so the
difference is visible.

Usage
-----
    python -m scripts.ops.rebuild_v10_asr_coordinates \\
        --v10-points .work/public_release/v10_points_export.json \\
        --attr-root ~/mukthiguru_attribution_data \\
        --out .work/public_release/phase3_candidate.jsonl \\
        --quarantine .work/public_release/phase3_quarantine.jsonl \\
        --parents .work/public_release/phase3_parents.jsonl \\
        --summary audits/evidence/public_release_phase3_summary_2026-10-21.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "rebuild-v10-asr-coordinates-v1"
SUMMARY_SCHEMA = "first-person-v10-asr-rebuild-summary-v1"
SPAN_ROW_SCHEMA = "first-person-v10-asr-rebuild-span-v1"
PARENT_ROW_SCHEMA = "first-person-v10-asr-rebuild-parent-v1"

#: Versioned normalization. Unicode-aware on purpose: the ASCII-only builder
#: normalizer cannot tokenize Devanagari or Urdu and would silently mark those
#: spans unverifiable.
NORMALIZATION_VERSION = "fp-norm-unicode-v1"

#: Versioned coordinate space: word indices into the timed artifact's word list.
COORDINATE_SPACE_VERSION = "fp-coords-v1"

#: The rebuilt corpus is a different corpus: the source-transcript identity and
#: the coordinate space both change, so it declares its own corpus version and
#: its ids cannot collide with the live collection's.
DEFAULT_CORPUS_VERSION = "fp-context-transcript-v2"

#: Artifact roots searched for ``transcripts_B/{video_id}.json``.
DEFAULT_ASR_ROOTS = (
    "mass_ingest_2026-10",
    "pilot50_2026-09-25",
    "bakeoff_2026-09-25",
    "audio_2026-09/pilot20_run",
    "shadow_validity_2026-10-11",
)

EXIT_OK = 0
EXIT_RELEASE_BLOCKED = 1
EXIT_INVALID_INPUT = 2

POLICY_EXACT = "exact"
POLICY_COVERAGE = "coverage"
RECONSTRUCTION_POLICIES = (POLICY_EXACT, POLICY_COVERAGE)

TIER_EXACT = "exact"
TIER_VARIANT = "variant"

_PUNCT_CATEGORIES = ("P", "S")


# ---------------------------------------------------------------------------
# Backend package resolution (so the contract's id helpers are the only ones)
# ---------------------------------------------------------------------------
def _resolve_backend_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "domain" / "first_person_context.py").is_file():
            return candidate
        nested = candidate / "backend"
        if (nested / "domain" / "first_person_context.py").is_file():
            return nested
    raise RuntimeError(f"cannot locate the backend package root from {here}")


_BACKEND = _resolve_backend_root()
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from domain.first_person_context import (  # noqa: E402
    clip_text_hash,
    make_parent_unit_id,
    make_source_span_id,
)


# ---------------------------------------------------------------------------
# Text handling
# ---------------------------------------------------------------------------
def normalize_text(text: str) -> str:
    """Versioned, Unicode-aware normalization (``fp-norm-unicode-v1``).

    NFKC -> lowercase -> comma-joined numbers -> hyphen/slash to space ->
    smart quotes and apostrophes dropped -> every remaining punctuation or
    symbol character to space -> whitespace collapsed.

    Letters of any script survive (``str.isalnum`` is True for Devanagari and
    Arabic letters), so a non-Latin span is tokenized rather than erased.
    """
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"(\d+)\s*,\s*(\d+)", r"\1\2", t)
    t = re.sub(r"[-—–/]", " ", t)
    t = re.sub(r"[\u2018\u2019\u201c\u201d']", "", t)
    out: list[str] = []
    for ch in t:
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        elif unicodedata.category(ch)[0] in _PUNCT_CATEGORIES:
            out.append(" ")
        else:
            out.append(ch)
    return " ".join("".join(out).split())


def tokenize(text: str) -> list[str]:
    """Normalized tokens of ``text`` under ``fp-norm-unicode-v1``."""
    return normalize_text(text).split()


_ASCII_NORM_RE = re.compile(r"[^a-z0-9 ]")


def _ascii_tokens(text: str) -> list[str]:
    """The builder's ASCII-only tokenization, used only for reporting.

    Kept so the summary can show how many spans the old ASCII-only checker
    could not tokenize at all — the multilingual gap this rebuild closes.
    """
    t = re.sub(r"(\d+)\s*,\s*(\d+)", r"\1\2", text.lower())
    t = re.sub(r"[-—–/]", " ", t)
    t = re.sub(r"[\u2018\u2019\u201c\u201d']", "", t)
    return _ASCII_NORM_RE.sub("", t).strip().split()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_finite_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Locator
# ---------------------------------------------------------------------------
def locate_span(
    span_tokens: list[str],
    timed_tokens: list[str],
    *,
    probe: int = 6,
) -> tuple[int, int, float]:
    """Locate ``span_tokens`` inside ``timed_tokens``.

    Returns ``(start_token, end_token, similarity)``; ``(-1, -1, 0.0)`` when the
    span cannot be located. The probe match plus a multi-anchor fallback
    mirrors the corpus builder's own locator, but over the Unicode token space
    and with a bounded set of window-length deltas: the display transcript and
    the voted transcript differ by a word here and there, so a span whose text
    is a few tokens longer or shorter than its region must still be located.
    """
    n, m = len(span_tokens), len(timed_tokens)
    if not n or not m:
        return -1, -1, 0.0
    deltas = (0, -1, 1, -2, 2, -3, 3, -4, 4)
    if n < probe:
        for index in range(m - n + 1):
            if timed_tokens[index : index + n] == span_tokens:
                return index, index + n, 1.0
        return -1, -1, 0.0

    head = span_tokens[:probe]
    best_start, best_end, best_ratio = -1, -1, 0.0
    for index in range(m - probe + 1):
        if timed_tokens[index : index + probe] != head:
            continue
        for delta in deltas:
            end = index + n + delta
            if end <= index or end > m:
                continue
            window = timed_tokens[index:end]
            ratio = SequenceMatcher(None, span_tokens, window, autojunk=False).ratio()
            if ratio > best_ratio:
                best_start, best_end, best_ratio = index, end, ratio
                if ratio >= 0.98:
                    return best_start, best_end, best_ratio
    if best_ratio >= 0.95:
        return best_start, best_end, best_ratio

    candidates: set[int] = set()
    if best_start >= 0:
        candidates.add(best_start)
    for anchor_len in [5, 4, 3] if n >= 5 else [n]:
        for offset in range(min(12, max(1, n - anchor_len + 1))):
            anchor = span_tokens[offset : offset + anchor_len]
            if len(anchor) < anchor_len:
                continue
            for index in range(m - anchor_len + 1):
                if timed_tokens[index : index + anchor_len] == anchor:
                    guess = index - offset
                    if -10 <= guess < m:
                        candidates.add(max(0, guess))
        if len(candidates) >= 3:
            break
    for start in sorted(candidates):
        for delta in (0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5, -6, 6, -8, 8, -10, 10, -15, 15):
            end = start + n + delta
            if end <= start or end > m:
                continue
            window = timed_tokens[start:end]
            ratio = SequenceMatcher(None, span_tokens, window, autojunk=False).ratio()
            if ratio > best_ratio:
                best_start, best_end, best_ratio = start, end, ratio
                if ratio >= 0.98:
                    return best_start, best_end, best_ratio
    return best_start, best_end, best_ratio


def token_coverage(span_tokens: list[str], window_tokens: list[str]) -> float:
    """Fraction of ``span_tokens`` present in ``window_tokens`` (order-aware)."""
    if not span_tokens or not window_tokens:
        return 0.0
    matcher = SequenceMatcher(None, window_tokens, span_tokens, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / float(len(span_tokens))


# ---------------------------------------------------------------------------
# RIFF/WAVE inspection (stdlib only)
# ---------------------------------------------------------------------------
def inspect_wav(path: Path) -> dict[str, Any] | None:
    """Inspect a RIFF/WAVE file header.

    Returns the declared sample rate, channels, bit depth, data size, derived
    duration and whether the declared audio is actually present in the file.
    A header-only stub reports ``audio_complete: false`` — its declared
    duration exists but there is no audio behind it, so it must never be used
    to justify a citation window or an ECAPA slice.
    """
    try:
        file_size = path.stat().st_size
        with path.open("rb") as handle:
            header = handle.read(12)
            if len(header) < 12 or header[0:4] != b"RIFF" or header[8:12] != b"WAVE":
                return None
            channels = sample_rate = bits = None
            data_bytes: int | None = None
            data_offset: int | None = None
            offset = 12
            while True:
                handle.seek(offset)
                chunk_header = handle.read(8)
                if len(chunk_header) < 8:
                    break
                chunk_id = chunk_header[0:4]
                chunk_size = int.from_bytes(chunk_header[4:8], "little")
                body_offset = offset + 8
                if chunk_id == b"fmt ":
                    fmt = handle.read(min(chunk_size, 16))
                    if len(fmt) >= 16:
                        channels = int.from_bytes(fmt[2:4], "little")
                        sample_rate = int.from_bytes(fmt[4:8], "little")
                        bits = int.from_bytes(fmt[14:16], "little")
                elif chunk_id == b"data":
                    data_bytes = chunk_size
                    data_offset = body_offset
                    break
                offset = body_offset + chunk_size + (chunk_size % 2)
    except OSError:
        return None

    if not sample_rate or not channels or not bits or data_bytes is None:
        return None
    bytes_per_second = float(sample_rate) * float(channels) * (float(bits) / 8.0)
    if bytes_per_second <= 0:
        return None
    duration_ms = int(round((float(data_bytes) / bytes_per_second) * 1000.0))
    present = data_offset is not None and (file_size - data_offset) >= data_bytes
    return {
        "path": str(path),
        "sample_rate": sample_rate,
        "channels": channels,
        "bits_per_sample": bits,
        "data_bytes": data_bytes,
        "duration_ms": duration_ms,
        "file_bytes": file_size,
        "audio_complete": bool(present),
    }


# ---------------------------------------------------------------------------
# Artifact discovery
# ---------------------------------------------------------------------------
class _Artifacts:
    """Resolved, hashed source artifacts for one video."""

    def __init__(self, *, timed_path: Path | None, audio: dict[str, Any] | None) -> None:
        self.timed_path = timed_path
        self.audio = audio


def _resolve_audio(
    video_id: str, attr_root: Path, asr_roots: Iterable[str]
) -> dict[str, Any] | None:
    """Find a WAV that actually contains audio for ``video_id``.

    Preference order: the consolidated archive, then each ASR root's ``audio``
    directory. A header-only stub is skipped (and reported), because its
    declared duration has no audio behind it.
    """
    candidates: list[Path] = []
    archive = attr_root / "audio_archive" / "wavs" / f"{video_id}.wav"
    if archive.is_file():
        candidates.append(archive)
    for root in asr_roots:
        candidate = attr_root / root / "audio" / f"{video_id}.wav"
        if candidate.is_file():
            candidates.append(candidate)
    stub: dict[str, Any] | None = None
    for candidate in candidates:
        info = inspect_wav(candidate)
        if info is None:
            continue
        if info["audio_complete"]:
            info["source"] = "complete_wav"
            return info
        stub = dict(info, source="stub_header_only")
    return stub


class _VideoIndex:
    """Lazily-resolved, hashed per-video artifacts."""

    def __init__(self, attr_root: Path, asr_roots: tuple[str, ...]) -> None:
        self.attr_root = attr_root
        self.asr_roots = asr_roots
        self._timed: dict[str, tuple[Path, list[dict[str, Any]], str] | None] = {}
        self._audio: dict[str, dict[str, Any] | None] = {}

    def timed(self, video_id: str) -> tuple[Path, list[dict[str, Any]], str] | None:
        if video_id in self._timed:
            return self._timed[video_id]
        found: tuple[Path, list[dict[str, Any]], str] | None = None
        for root in self.asr_roots:
            candidate = self.attr_root / root / "transcripts_B" / f"{video_id}.json"
            if not candidate.is_file():
                continue
            try:
                raw = candidate.read_bytes()
                data = json.loads(raw.decode("utf-8"))
            except (OSError, ValueError, UnicodeDecodeError):
                continue
            if not isinstance(data, list) or not data:
                continue
            if not all(isinstance(entry, dict) for entry in data):
                continue
            found = (candidate, data, _sha256_bytes(raw))
            break
        self._timed[video_id] = found
        return found

    def raw_meta(self, video_id: str, suffix: str) -> dict[str, Any] | None:
        for root in self.asr_roots:
            candidate = self.attr_root / root / "raw" / f"{video_id}{suffix}.json"
            if not candidate.is_file():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                return {
                    "path": str(candidate),
                    "sha256": _sha256_file(candidate),
                    "ok": data.get("ok"),
                    "model": data.get("model"),
                }
        return None

    def audio(self, video_id: str) -> dict[str, Any] | None:
        if video_id not in self._audio:
            self._audio[video_id] = _resolve_audio(video_id, self.attr_root, self.asr_roots)
        return self._audio[video_id]


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------
class InputError(Exception):
    """Raised when an input cannot be trusted. Always fatal (exit 2)."""


def _load_points(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        rows: list[Any] = []
        for number, line in enumerate(raw.splitlines(), 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise InputError(f"{path}: line {number} is not valid JSON: {exc}") from exc
        if not rows:
            raise InputError(f"{path}: not valid JSON and not valid JSONL")
        data = rows

    raw_points: Any = None
    if isinstance(data, list):
        raw_points = data
    elif isinstance(data, dict):
        for key in ("result", "points", "records", "items"):
            value = data.get(key)
            if isinstance(value, dict):
                value = value.get("points")
            if isinstance(value, list):
                raw_points = value
                break
        else:
            if "payload" in data or "id" in data or "source_span_id" in data:
                raw_points = [data]
            else:
                raise InputError(f"{path}: no point list found (expected 'result.points')")
    else:
        raise InputError(f"{path}: unsupported top-level JSON type {type(data).__name__}")

    points: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw_points):
        if not isinstance(entry, dict):
            raise InputError(f"{path}: point #{index} is not an object")
        payload = entry.get("payload")
        body = payload if isinstance(payload, dict) else entry
        point_id = str(
            entry.get("id")
            if isinstance(payload, dict)
            else (entry.get("id") or entry.get("_point_id") or "")
        )
        span_id = str(body.get("source_span_id") or "")
        key = span_id or point_id
        if key in seen:
            raise InputError(f"{path}: duplicate record {key!r} at position {index}")
        seen.add(key)
        points.append({"id": point_id, "payload": body})
    return points


# ---------------------------------------------------------------------------
# Rebuild
# ---------------------------------------------------------------------------
def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and float(value).is_integer():
        return int(value)
    return None


def _live_span_facts(payload: dict[str, Any], index: _VideoIndex) -> dict[str, Any]:
    """Facts about the live payload, used for the 'before' column."""
    video_id = str(payload.get("video_id") or "")
    timed = index.timed(video_id)
    audio = index.audio(video_id)
    word_count = len(timed[1]) if timed else 0
    word_start = _as_int(payload.get("word_start"))
    word_end = _as_int(payload.get("word_end"))
    start_ms = _as_int(payload.get("start_ms"))
    end_ms = _as_int(payload.get("end_ms"))

    coords_in_range = bool(
        timed
        and word_start is not None
        and word_end is not None
        and word_start >= 0
        and word_end > word_start
        and word_end <= word_count
    )
    window_ordered = bool(start_ms is not None and end_ms is not None and end_ms > start_ms)
    duration_ms = audio["duration_ms"] if audio else None
    within_audio = bool(
        duration_ms is not None
        and start_ms is not None
        and end_ms is not None
        and end_ms <= duration_ms
    )
    asr_extent_ms = (
        int(round(max(float(entry.get("end", 0.0)) for entry in timed[1]) * 1000.0))
        if timed
        else None
    )
    beyond_asr_extent = bool(
        asr_extent_ms is not None and end_ms is not None and end_ms > asr_extent_ms
    )

    span_tokens = tokenize(str(payload.get("verbatim_text") or ""))
    ascii_tokens = _ascii_tokens(str(payload.get("verbatim_text") or ""))
    timed_tokens: list[str] = []
    if timed:
        for entry in timed[1]:
            timed_tokens.extend(tokenize(str(entry.get("w", ""))))
    if timed and start_ms is not None and end_ms is not None:
        window_tokens: list[str] = []
        for entry in timed[1]:
            w_start = int(round(float(entry.get("start", 0.0)) * 1000.0))
            w_end = int(round(float(entry.get("end", 0.0)) * 1000.0))
            if w_end < start_ms or w_start > end_ms:
                continue
            window_tokens.extend(tokenize(str(entry.get("w", ""))))
        window_coverage = token_coverage(span_tokens, window_tokens)
        overlap = bool(window_tokens)
    else:
        window_coverage = 0.0
        overlap = False

    return {
        "word_count": word_count,
        "word_start": word_start,
        "word_end": word_end,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "coordinates_in_range": coords_in_range,
        "window_ordered": window_ordered,
        "audio_duration_ms": duration_ms,
        "audio_complete": bool(audio["audio_complete"]) if audio else False,
        "audio_source": audio["source"] if audio else None,
        "within_audio_duration": within_audio,
        "asr_aligned_extent_ms": asr_extent_ms,
        "beyond_asr_aligned_extent": beyond_asr_extent,
        "window_has_overlap": overlap,
        "window_token_coverage": round(window_coverage, 6),
        "window_token_coverage_zero": bool(window_coverage == 0.0 and span_tokens),
        "span_token_count": len(span_tokens),
        "span_ascii_token_count": len(ascii_tokens),
        "multilingual_unverifiable_by_ascii": bool(span_tokens and not ascii_tokens),
        "asr_artifact_present": timed is not None,
    }


def rebuild_span(
    payload: dict[str, Any],
    index: _VideoIndex,
    *,
    corpus_version: str,
    coverage_floor: float,
) -> dict[str, Any]:
    """Rebuild one span from the immutable word-timed artifact."""
    video_id = str(payload.get("video_id") or "")
    guru_id = str(payload.get("guru_id") or payload.get("teacher_id") or "")
    span_text = str(payload.get("verbatim_text") or payload.get("span_text") or "")
    live_span_id = str(payload.get("source_span_id") or "")
    live_parent_id = str(payload.get("parent_unit_id") or "")

    row: dict[str, Any] = {
        "schema": SPAN_ROW_SCHEMA,
        "coordinate_space_version": COORDINATE_SPACE_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "corpus_version": corpus_version,
        "live_source_span_id": live_span_id,
        "live_parent_unit_id": live_parent_id,
        "live_point_id": str(payload.get("id") or ""),
        "video_id": video_id,
        "guru_id": guru_id,
        "source_asset_id": str(payload.get("source_asset_id") or video_id),
        "turn_id": str(payload.get("turn_id") or ""),
        "turn_index": _as_int(payload.get("turn_index")),
        "source_span_index": _as_int(payload.get("source_span_index")),
        "previous_span_id": payload.get("previous_span_id"),
        "next_span_id": payload.get("next_span_id"),
        "live_verbatim_text": span_text,
        "live_start_ms": _as_int(payload.get("start_ms")),
        "live_end_ms": _as_int(payload.get("end_ms")),
        "live_word_start": _as_int(payload.get("word_start")),
        "live_word_end": _as_int(payload.get("word_end")),
        "live_source_text_hash": str(payload.get("source_text_hash") or ""),
        "live_transcript_hash": str(payload.get("transcript_hash") or ""),
        "live_corpus_version": str(payload.get("corpus_version") or ""),
        "quarantine_reasons": [],
    }

    def _quarantine(reason: str) -> None:
        if reason not in row["quarantine_reasons"]:
            row["quarantine_reasons"].append(reason)

    timed = index.timed(video_id)
    if timed is None:
        row["timed_transcript_path"] = None
        _quarantine("asr_artifact_missing")
        row["valid"] = False
        return row
    timed_path, timed_entries, timed_sha = timed
    words = [str(entry.get("w", "")) for entry in timed_entries]
    starts = [float(entry.get("start", 0.0)) for entry in timed_entries]
    ends = [float(entry.get("end", 0.0)) for entry in timed_entries]

    row["timed_transcript_path"] = str(timed_path)
    row["timed_transcript_sha256"] = timed_sha
    row["timed_word_count"] = len(words)
    row["timed_asr_aligned_extent_ms"] = int(round(max(ends) * 1000.0)) if ends else None
    align_meta = index.raw_meta(video_id, "_align")
    parakeet_meta = index.raw_meta(video_id, "_parakeet")
    row["timed_alignment_ok"] = (align_meta or {}).get("ok")
    row["timed_alignment_sha256"] = (align_meta or {}).get("sha256")
    row["timed_asr_model"] = (parakeet_meta or {}).get("model")

    span_tokens = tokenize(span_text)
    row["span_token_count"] = len(span_tokens)
    row["span_ascii_token_count"] = len(_ascii_tokens(span_text))
    row["span_multilingual"] = bool(span_tokens and not _ascii_tokens(span_text))
    if not span_tokens:
        _quarantine("span_not_tokenizable")
        row["valid"] = False
        return row

    timed_tokens: list[str] = []
    timed_word_of_token: list[int] = []
    for index_i, word in enumerate(words):
        for token in tokenize(word):
            timed_tokens.append(token)
            timed_word_of_token.append(index_i)
    row["timed_token_count"] = len(timed_tokens)

    start_token, end_token, ratio = locate_span(span_tokens, timed_tokens)
    row["locator_start_token"] = start_token
    row["locator_end_token"] = end_token
    row["locator_similarity"] = round(ratio, 6)
    if start_token < 0 or end_token <= start_token:
        _quarantine("span_not_located_in_asr")
        row["valid"] = False
        return row
    if end_token > len(timed_tokens):
        _quarantine("span_range_overflow")
        row["valid"] = False
        return row

    word_start = timed_word_of_token[start_token]
    word_end = timed_word_of_token[end_token - 1] + 1
    row["word_start"] = word_start
    row["word_end"] = word_end
    row["word_range_in_bounds"] = bool(0 <= word_start < word_end <= len(words))
    if not row["word_range_in_bounds"]:
        _quarantine("word_coordinates_out_of_range")
    if word_end <= word_start:
        _quarantine("word_end_not_after_word_start")

    audio_start_ms = int(round(min(starts[word_start:word_end]) * 1000.0))
    audio_end_ms = int(round(max(ends[word_start:word_end]) * 1000.0))
    row["audio_start_ms"] = audio_start_ms
    row["audio_end_ms"] = audio_end_ms
    row["audio_window_ordered"] = bool(audio_end_ms > audio_start_ms)
    if not row["audio_window_ordered"]:
        _quarantine("audio_end_not_after_audio_start")

    reconstructed = " ".join(words[word_start:word_end])
    row["reconstructed_text"] = reconstructed
    row["source_text_hash"] = clip_text_hash(reconstructed)
    row["text_hash_matches_live"] = bool(row["source_text_hash"] == row["live_source_text_hash"])

    span_normalized = normalize_text(span_text)
    reconstructed_normalized = normalize_text(reconstructed)
    row["reconstruction_exact"] = bool(span_normalized == reconstructed_normalized)
    row["reconstruction_ratio"] = round(token_coverage(span_tokens, tokenize(reconstructed)), 6)
    row["reconstruction_tier"] = TIER_EXACT if row["reconstruction_exact"] else TIER_VARIANT
    row["transcription_variant"] = not row["reconstruction_exact"]

    # The cited window must cover the span text (multilingual-aware).
    window_tokens: list[str] = []
    for index_i in range(word_start, word_end):
        window_tokens.extend(tokenize(words[index_i]))
    row["window_token_coverage"] = round(token_coverage(span_tokens, window_tokens), 6)
    row["window_has_overlap"] = bool(window_tokens)
    if not row["window_has_overlap"]:
        _quarantine("audio_window_no_overlap")
    if row["window_token_coverage"] < coverage_floor:
        _quarantine("audio_window_coverage_below_floor")

    # Archived audio bounds.
    audio = index.audio(video_id)
    row["archived_audio_path"] = audio["path"] if audio else None
    row["archived_audio_sha256"] = _sha256_file(Path(audio["path"])) if audio else None
    row["archived_audio_duration_ms"] = audio["duration_ms"] if audio else None
    row["archived_audio_complete"] = bool(audio["audio_complete"]) if audio else False
    row["archived_audio_source"] = audio["source"] if audio else None
    if audio is None:
        _quarantine("archived_audio_missing")
    elif not audio["audio_complete"]:
        _quarantine("archived_audio_truncated")
    elif audio_end_ms > int(audio["duration_ms"]):
        _quarantine("audio_end_beyond_archived_audio")
    if audio_start_ms < 0:
        _quarantine("audio_start_before_zero")

    # Deterministic identity.
    row["transcript_hash"] = timed_sha
    rebuilt_span_id = make_source_span_id(
        guru_id=guru_id,
        video_id=video_id,
        corpus_version=corpus_version,
        word_start=word_start,
        word_end=word_end,
        transcript_hash=timed_sha,
    )
    row["source_span_id"] = rebuilt_span_id
    row["id_rederives"] = bool(
        rebuilt_span_id
        == make_source_span_id(
            guru_id=guru_id,
            video_id=video_id,
            corpus_version=corpus_version,
            word_start=word_start,
            word_end=word_end,
            transcript_hash=timed_sha,
        )
    )
    if not row["id_rederives"]:
        _quarantine("source_span_id_not_deterministic")

    # Identity comparison against the live collection.
    same_space_id = make_source_span_id(
        guru_id=guru_id,
        video_id=video_id,
        corpus_version=row["live_corpus_version"] or corpus_version,
        word_start=word_start,
        word_end=word_end,
        transcript_hash=row["live_transcript_hash"] or timed_sha,
    )
    row["source_span_id_in_live_corpus_space"] = same_space_id
    row["coordinates_changed_vs_live"] = bool(
        word_start != row["live_word_start"] or word_end != row["live_word_end"]
    )
    row["transcript_hash_changed_vs_live"] = bool(timed_sha != row["live_transcript_hash"])

    row["valid"] = not row["quarantine_reasons"]
    return row


def rebuild(
    *,
    v10_points: list[dict[str, Any]],
    index: _VideoIndex,
    corpus_version: str,
    coverage_floor: float,
    policy: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Rebuild every v10 child; split into candidate / variant / quarantine."""
    candidate: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    live_facts: dict[str, dict[str, Any]] = {}
    rebuilt_by_live_span: dict[str, dict[str, Any]] = {}

    for point in v10_points:
        payload = point["payload"]
        live_span_id = str(payload.get("source_span_id") or "")
        live_facts[live_span_id] = _live_span_facts(payload, index)
        row = rebuild_span(
            payload, index, corpus_version=corpus_version, coverage_floor=coverage_floor
        )
        row["live_facts"] = live_facts[live_span_id]
        rebuilt_by_live_span[live_span_id] = row
        # A transcription variant is recorded as a reason on every affected
        # span, so the reason counts describe the whole population and not
        # only the first check that happened to fail.
        if row.get("reconstruction_tier") == TIER_VARIANT:
            row["transcription_variant"] = True
            variants.append(row)
            if policy == POLICY_EXACT:
                if "reconstruction_variant_not_exact" not in row["quarantine_reasons"]:
                    row["quarantine_reasons"].append("reconstruction_variant_not_exact")
                row["valid"] = False
                row["admitted_to_candidate"] = False
                quarantine.append(row)
                continue
            row["admitted_to_candidate"] = True
        if not row.get("valid"):
            row.setdefault("admitted_to_candidate", False)
            quarantine.append(row)
            continue
        row["admitted_to_candidate"] = True
        candidate.append(row)

    # A deterministic id must identify exactly one source span. When two or
    # more DISTINCT source spans produce the same id, EVERY member is
    # quarantined: keeping one and dropping the other would absorb the defect
    # and make a broken identity look like a healthy corpus.
    unique_rows: list[dict[str, Any]] = []
    seen_row_objects: set[int] = set()
    for bucket in (candidate, variants, quarantine):
        for row in bucket:
            if id(row) not in seen_row_objects:
                seen_row_objects.add(id(row))
                unique_rows.append(row)

    id_members: dict[str, list[dict[str, Any]]] = {}
    for row in unique_rows:
        id_members.setdefault(str(row.get("source_span_id") or ""), []).append(row)

    collisions: list[dict[str, Any]] = []
    for span_id, members in sorted(id_members.items()):
        if not span_id or len(members) < 2:
            continue
        distinct_live = {str(row.get("live_source_span_id") or "") for row in members}
        collisions.append(
            {
                "collided_source_span_id": span_id,
                "member_count": len(members),
                "distinct_live_source_span_ids": sorted(distinct_live),
                "cause": "incomplete_deterministic_id_namespace",
                "resolution_status": "unresolved",
            }
        )
        for row in members:
            if "deterministic_id_collision" not in row["quarantine_reasons"]:
                row["quarantine_reasons"].append("deterministic_id_collision")
            row["deterministic_id_collision"] = True
            row["valid"] = False
            row["admitted_to_candidate"] = False
            if row not in quarantine:
                quarantine.append(row)
            if row in candidate:
                candidate.remove(row)

    parents = _rebuild_parents(candidate, quarantine, corpus_version)

    live_parent_ids = {
        str(point["payload"].get("parent_unit_id") or "")
        for point in v10_points
        if str(point["payload"].get("parent_unit_id") or "")
    }
    rebuilt_parent_ids = {parent["live_parent_unit_id"] for parent in parents}

    summary = _build_summary(
        candidate=candidate,
        variants=variants,
        quarantine=quarantine,
        parents=parents,
        live_facts=live_facts,
        corpus_version=corpus_version,
        coverage_floor=coverage_floor,
        policy=policy,
        v10_children=len(v10_points),
    )
    summary["totals"]["live_parent_units"] = len(live_parent_ids)
    summary["totals"]["deterministic_id_collisions"] = len(collisions)
    summary["totals"]["deterministic_id_collision_members"] = sum(
        int(c["member_count"]) for c in collisions
    )
    summary["deterministic_id_collisions"] = collisions
    summary["totals"]["live_parent_units_fully_quarantined"] = len(
        live_parent_ids - rebuilt_parent_ids
    )
    summary["totals"]["parent_groups_preserved"] = len(rebuilt_parent_ids & live_parent_ids)
    return candidate, variants, quarantine, parents, summary


def _rebuild_parents(
    candidate: list[dict[str, Any]],
    quarantine: list[dict[str, Any]],
    corpus_version: str,
) -> list[dict[str, Any]]:
    """Rebuild parent units over the live grouping, re-derived from children.

    The live parent *grouping* is preserved (which spans belong together is a
    serving decision, not a coordinate decision); only the identity and window
    fields are re-derived from the rebuilt children.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidate:
        groups[row["live_parent_unit_id"]].append(row)

    parents: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for live_parent_id in sorted(groups):
        children = sorted(
            groups[live_parent_id],
            key=lambda item: (item["word_start"], item["word_end"], item["source_span_id"]),
        )
        first_word = min(child["word_start"] for child in children)
        last_word = max(child["word_end"] for child in children)
        guru_id = children[0]["guru_id"]
        video_id = children[0]["video_id"]
        parent_unit_id = make_parent_unit_id(
            guru_id=guru_id,
            video_id=video_id,
            corpus_version=corpus_version,
            first_word_index=first_word,
            last_word_index=last_word,
        )
        if parent_unit_id in seen:
            for child in children:
                child.setdefault("quarantine_reasons", []).append("duplicate_parent_unit_id")
                child["valid"] = False
            quarantine.extend(children)
            continue
        seen[parent_unit_id] = live_parent_id
        parents.append(
            {
                "schema": PARENT_ROW_SCHEMA,
                "coordinate_space_version": COORDINATE_SPACE_VERSION,
                "normalization_version": NORMALIZATION_VERSION,
                "corpus_version": corpus_version,
                "parent_unit_id": parent_unit_id,
                "live_parent_unit_id": live_parent_id,
                "guru_id": guru_id,
                "video_id": video_id,
                "first_word_index": first_word,
                "last_word_index": last_word,
                "start_ms": min(child["audio_start_ms"] for child in children),
                "end_ms": max(child["audio_end_ms"] for child in children),
                "ordered_source_span_ids": [child["source_span_id"] for child in children],
                "parent_text_hash": clip_text_hash(
                    " ".join(child["reconstructed_text"] for child in children)
                ),
                "child_count": len(children),
                "id_rederives": bool(
                    parent_unit_id
                    == make_parent_unit_id(
                        guru_id=guru_id,
                        video_id=video_id,
                        corpus_version=corpus_version,
                        first_word_index=first_word,
                        last_word_index=last_word,
                    )
                ),
            }
        )
    return parents


def _build_summary(
    *,
    candidate: list[dict[str, Any]],
    variants: list[dict[str, Any]],
    quarantine: list[dict[str, Any]],
    parents: list[dict[str, Any]],
    live_facts: dict[str, dict[str, Any]],
    corpus_version: str,
    coverage_floor: float,
    policy: str,
    v10_children: int,
) -> dict[str, Any]:
    total = v10_children

    before = Counter()
    after = Counter()
    reasons = Counter()

    # The key set is fixed so a zero is reported as 0, not as a missing key.
    before_keys = (
        "total",
        "valid_coordinates",
        "invalid_coordinates",
        "ordered_audio_window",
        "within_archived_audio",
        "out_of_bounds_audio_window",
        "beyond_asr_aligned_extent",
        "audio_window_with_overlap",
        "audio_window_no_overlap",
        "audio_window_zero_coverage",
        "audio_window_coverage_ok",
        "audio_window_coverage_fail",
        "multilingual_unverifiable_by_ascii_checker",
        "asr_artifact_missing",
        "archived_audio_incomplete",
    )
    after_keys = (
        "total",
        "valid_coordinates",
        "invalid_coordinates",
        "ordered_audio_window",
        "within_archived_audio",
        "out_of_bounds_audio_window",
        "audio_window_with_overlap",
        "audio_window_no_overlap",
        "audio_window_zero_coverage",
        "audio_window_coverage_ok",
        "audio_window_coverage_fail",
        "multilingual_span",
        "multilingual_span_exact_reconstruction",
        "deterministic_id_ok",
        "deterministic_id_mismatch",
        "coordinates_changed_vs_live",
        "transcript_hash_changed_vs_live",
    )
    for key in before_keys:
        before[key] = 0
    for key in after_keys:
        after[key] = 0
    for row in quarantine:
        for reason in row.get("quarantine_reasons", []):
            reasons[reason] += 1

    for facts in live_facts.values():
        before["total"] += 1
        if facts["coordinates_in_range"]:
            before["valid_coordinates"] += 1
        else:
            before["invalid_coordinates"] += 1
        if facts["window_ordered"]:
            before["ordered_audio_window"] += 1
        if facts["within_audio_duration"]:
            before["within_archived_audio"] += 1
        else:
            before["out_of_bounds_audio_window"] += 1
        if facts["beyond_asr_aligned_extent"]:
            before["beyond_asr_aligned_extent"] += 1
        if facts["window_has_overlap"]:
            before["audio_window_with_overlap"] += 1
        else:
            before["audio_window_no_overlap"] += 1
        if facts["window_token_coverage_zero"]:
            before["audio_window_zero_coverage"] += 1
        if facts["multilingual_unverifiable_by_ascii"]:
            before["multilingual_unverifiable_by_ascii_checker"] += 1
        before["archived_audio_source:" + str(facts["audio_source"])] += 1
        if facts["window_token_coverage"] >= 0.90:
            before["audio_window_coverage_ok"] += 1
        else:
            before["audio_window_coverage_fail"] += 1
        if not facts["asr_artifact_present"]:
            before["asr_artifact_missing"] += 1
        if not facts["audio_complete"]:
            before["archived_audio_incomplete"] += 1

    for row in candidate:
        after["total"] += 1
        if row.get("word_range_in_bounds"):
            after["valid_coordinates"] += 1
        else:
            after["invalid_coordinates"] += 1
        if row.get("audio_window_ordered"):
            after["ordered_audio_window"] += 1
        if row.get("archived_audio_complete") and row.get("audio_end_ms") is not None:
            after["within_archived_audio"] += 1
        else:
            after["out_of_bounds_audio_window"] += 1
        if row.get("window_has_overlap"):
            after["audio_window_with_overlap"] += 1
        else:
            after["audio_window_no_overlap"] += 1
        if row.get("window_token_coverage", 1.0) == 0.0:
            after["audio_window_zero_coverage"] += 1
        if row.get("span_multilingual"):
            after["multilingual_span"] += 1
        if row.get("span_multilingual") and row.get("reconstruction_tier") == TIER_EXACT:
            after["multilingual_span_exact_reconstruction"] += 1
        after["archived_audio_source:" + str(row.get("archived_audio_source"))] += 1
        if row.get("window_token_coverage", 0.0) >= coverage_floor:
            after["audio_window_coverage_ok"] += 1
        else:
            after["audio_window_coverage_fail"] += 1
        if row.get("id_rederives"):
            after["deterministic_id_ok"] += 1
        else:
            after["deterministic_id_mismatch"] += 1
        if row.get("coordinates_changed_vs_live"):
            after["coordinates_changed_vs_live"] += 1
        if row.get("transcript_hash_changed_vs_live"):
            after["transcript_hash_changed_vs_live"] += 1

    quarantine_rows = sum(1 for row in quarantine if not row.get("valid"))
    multilingual_total = sum(1 for row in candidate + quarantine if row.get("span_multilingual"))
    release_reasons: list[str] = []
    if quarantine_rows:
        release_reasons.append(
            f"{quarantine_rows} v10 spans could not be rebuilt from the word-timed artifact"
        )
    if variants and policy == POLICY_EXACT:
        release_reasons.append(
            f"{len(variants)} spans rebuild only as transcription variants and are quarantined "
            "under the 'exact' reconstruction policy"
        )
    if after["deterministic_id_mismatch"]:
        release_reasons.append(
            f"{after['deterministic_id_mismatch']} rebuilt ids do not re-derive deterministically"
        )
    release_reasons.append(
        "the rebuilt candidate has NOT been written to any collection; Phase 2 still has no "
        "per-span acoustic evidence and the harness stays disabled"
    )

    return {
        "schema": SUMMARY_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "coordinate_space_version": COORDINATE_SPACE_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "corpus_version": corpus_version,
        "reconstruction_policy": policy,
        "coverage_floor": coverage_floor,
        "release_blocking": True,
        "release_blocking_reasons": release_reasons,
        "totals": {
            "v10_children": total,
            "candidate_spans": len(candidate),
            "exact_candidate_spans": sum(
                1 for row in candidate if row.get("reconstruction_tier") == TIER_EXACT
            ),
            "variant_spans": len(variants),
            "variant_spans_admitted": sum(
                1 for row in candidate if row.get("reconstruction_tier") == TIER_VARIANT
            ),
            "quarantined_spans": len(quarantine),
            "multilingual_spans_total": multilingual_total,
            "rebuilt_parent_units": len(parents),
        },
        "before": dict(sorted(before.items())),
        "after": dict(sorted(after.items())),
        "quarantine_reasons": dict(sorted(reasons.items())),
        "note": (
            "'before' is measured on the live payload with the same validators; "
            "'after' is measured on the rebuilt candidate. 'within_archived_audio' uses the "
            "complete archived WAV; 'beyond_asr_aligned_extent' uses the last aligned word of "
            "the word-timed artifact, which is the stricter ASR-derived extent."
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only rebuild of the v10 ASR word coordinates and audio windows.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--v10-points", required=True, help="Export of the v10 children.")
    parser.add_argument(
        "--attr-root",
        default=os.getenv("ATTR_ROOT", "/Users/harshodaikolluru/mukthiguru_attribution_data"),
    )
    parser.add_argument("--asr-roots", nargs="*", default=list(DEFAULT_ASR_ROOTS))
    parser.add_argument("--corpus-version", default=DEFAULT_CORPUS_VERSION)
    parser.add_argument("--coverage-floor", type=float, default=0.90)
    parser.add_argument(
        "--reconstruction-policy",
        choices=RECONSTRUCTION_POLICIES,
        default=POLICY_EXACT,
        help=(
            "exact (default) admits only spans whose reconstruction reproduces the span "
            "text exactly; coverage also admits spans that cover it above the floor."
        ),
    )
    parser.add_argument("--out", required=True, help="Candidate spans JSONL path.")
    parser.add_argument("--parents", default=None, help="Rebuilt parent units JSONL path.")
    parser.add_argument("--quarantine", default=None, help="Quarantined spans JSONL path.")
    parser.add_argument("--variants", default=None, help="Transcription-variant spans JSONL path.")
    parser.add_argument("--summary", required=True, help="Summary JSON path.")
    parser.add_argument("--generated-at-utc", default=None)
    parser.add_argument(
        "--apply-to-qdrant",
        action="store_true",
        help="REJECTED. This script has no write mode; it only emits a candidate package.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.apply_to_qdrant:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "reason": "this script has no write mode; the candidate is a file package",
                    "script_version": SCRIPT_VERSION,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    try:
        points = _load_points(Path(args.v10_points))
    except InputError as exc:
        print(
            json.dumps(
                {"status": "invalid_input", "error": str(exc), "script_version": SCRIPT_VERSION},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    index = _VideoIndex(Path(args.attr_root), tuple(args.asr_roots))
    candidate, variants, quarantine, parents, summary = rebuild(
        v10_points=points,
        index=index,
        corpus_version=args.corpus_version,
        coverage_floor=args.coverage_floor,
        policy=args.reconstruction_policy,
    )

    summary["inputs"] = {
        "v10_points": {
            "path": str(Path(args.v10_points).resolve()),
            "sha256": _sha256_file(Path(args.v10_points)),
            "bytes": Path(args.v10_points).stat().st_size,
        },
        "attr_root": str(Path(args.attr_root).resolve()),
        "asr_roots": list(args.asr_roots),
    }
    summary["generated_at_utc"] = (
        args.generated_at_utc if args.generated_at_utc else _dt.datetime.now(_dt.UTC).isoformat()
    )

    def _write_jsonl(path: str | None, rows: list[dict[str, Any]]) -> str | None:
        if not path:
            return None
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        return str(target)

    out_path = _write_jsonl(args.out, candidate)
    parents_path = _write_jsonl(args.parents, parents)
    quarantine_path = _write_jsonl(args.quarantine, quarantine)
    variants_path = _write_jsonl(args.variants, variants)

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "script_version": SCRIPT_VERSION,
                "reconstruction_policy": args.reconstruction_policy,
                "corpus_version": args.corpus_version,
                "totals": summary["totals"],
                "before": summary["before"],
                "after": summary["after"],
                "quarantine_reasons": summary["quarantine_reasons"],
                "release_blocking": summary["release_blocking"],
                "out": out_path,
                "parents": parents_path,
                "quarantine": quarantine_path,
                "variants": variants_path,
                "summary": str(summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return EXIT_RELEASE_BLOCKED if summary["release_blocking"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
