#!/usr/bin/env python3
"""Reconcile archived legacy ECAPA speaker verdicts against first-person v10 spans.

**Read-only.** This script never writes to Qdrant, never mutates an input
manifest, never sets ``speaker_verified``, and never upgrades a payload. It
emits a per-span report (JSONL) plus a machine-readable summary (JSON) that
quantifies how much of the live v10 collection can be joined to the archived
acoustic evidence, and — more importantly — how much cannot.

Why this exists
---------------
``docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md`` blocker **B1**: the
live ``first_person_v10`` collection carries ``speaker_verified=true`` on 2,737
children, while the archived ECAPA verdict file holds 1,173 records keyed by
**legacy v9 point ids**. The direct overlap between those keys and the v10
point ids / ``source_span_id`` values is zero, so no span-keyed acoustic
verdict exists for any child. This script measures exactly that gap, per span,
without touching anything.

``safe_to_upgrade`` semantics (read this before trusting the number)
---------------------------------------------------------------------
``safe_to_upgrade`` means *"a legacy verdict is unambiguously joinable to this
span"*. It does **not** mean *"this span has independent per-span acoustic
evidence"*. The two are different, and the repository treats them differently:

* ``--verdict-schema-policy release_grade`` (default) additionally requires the
  verdict record to carry release-grade provenance (model revision, calibration
  revision, per-span audio identity, span id, timestamps, cosine floor and
  margin threshold). The archived legacy file predates the impostor-calibrated
  verifier and carries none of that, so ``safe_to_upgrade`` is ``false`` for
  every row — which is the honest answer, not a bug.
* ``--verdict-schema-policy legacy_v1`` accepts the older verdict schema. It
  exists so the *joinable* population can be compared against prior reports.
  It is **not** sufficient for release; the summary says so explicitly.

Even a ``safe_to_upgrade=true`` row only means *"look again at this span in
Phase 2"*. Phase 2 must re-run ECAPA over each span's own ``[start_ms, end_ms]``
slice. Absence of evidence is never converted into evidence.

Exit codes
----------
=====  ===================================================================
0      Report produced and no release-blocking condition was found.
1      Report produced; release-blocking conditions exist (ordinary missing
       coverage, ambiguity, identity conflicts, invalid records). This is the
       documented release-blocking status.
2      No trustworthy report could be produced: an input file is unreadable or
       unparseable, an export violates a structural invariant (duplicate point
       ids), or a write mode was requested. Fail closed.
=====  ===================================================================

Usage
-----
    python -m scripts.ops.reconcile_v10_ecapa_verdicts \\
        --v10-points .work/fp_context/v10_points_export.json \\
        --legacy-points .work/fp_context/v9_points.json \\
        --verdicts .work/fp_context/speaker_verdicts.json \\
        --asr-manifest .work/fp_context/asr_manifest_existing.json \\
        --out .work/public_release/reconciliation_v10_ecapa.jsonl \\
        --summary .work/public_release/reconciliation_v10_ecapa.summary.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "reconcile-v10-ecapa-verdicts-v1"
SUMMARY_SCHEMA = "first-person-v10-ecapa-reconciliation-summary-v1"
ROW_SCHEMA = "first-person-v10-ecapa-reconciliation-row-v1"

#: Versioned text normalization. Bump together with the builder's ``_norm``.
NORMALIZATION_VERSION = "fp-norm-v1"

EXIT_OK = 0
EXIT_RELEASE_BLOCKED = 1
EXIT_INVALID_INPUT = 2

# --- match classes ---------------------------------------------------------
MATCH_EXACT_SPAN_ID = "exact_span_id"
MATCH_EXACT_POINT_ID = "exact_point_id"
MATCH_UNIQUE_IDENTITY = "unique_identity_match"
MATCH_AMBIGUOUS_IDENTITY = "ambiguous_identity_match"
MATCH_MISSING_LEGACY_POINT = "missing_legacy_point"
MATCH_MISSING_VERDICT = "missing_verdict"
MATCH_IDENTITY_CONFLICT = "identity_conflict"
MATCH_INVALID_INPUT = "invalid_input"

MATCH_CLASSES = (
    MATCH_EXACT_SPAN_ID,
    MATCH_EXACT_POINT_ID,
    MATCH_UNIQUE_IDENTITY,
    MATCH_AMBIGUOUS_IDENTITY,
    MATCH_MISSING_LEGACY_POINT,
    MATCH_MISSING_VERDICT,
    MATCH_IDENTITY_CONFLICT,
    MATCH_INVALID_INPUT,
)

#: Verdict-schema policies. ``release_grade`` is the default and the only one
#: that may ever be cited as release evidence.
POLICY_RELEASE_GRADE = "release_grade"
POLICY_LEGACY_V1 = "legacy_v1"
VERDICT_SCHEMA_POLICIES = (POLICY_RELEASE_GRADE, POLICY_LEGACY_V1)

_NORM_RE = re.compile(r"[^a-z0-9 ]")


# ---------------------------------------------------------------------------
# Text handling
# ---------------------------------------------------------------------------
def normalize_text(text: str) -> str:
    """Versioned text normalization (``fp-norm-v1``).

    This mirrors ``scripts/ops/build_fp_context_from_v9.py::_norm`` so the
    identity hash computed here is comparable with the builder's. It is
    deliberately ASCII-only, exactly like the builder: a Devanagari span
    normalizes to the empty string and is therefore reported as an
    unverifiable text hash rather than silently hashed to something else.

    ``backend/tests/test_reconcile_v10_ecapa_verdicts.py`` pins this function
    against the builder so the two cannot drift.
    """
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


def clip_text_hash(text: str) -> str:
    """Clip-level hash. Mirrors ``domain.first_person_context.clip_text_hash``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalized_text_hash(text: str) -> str:
    """Hash of the normalized text. Used for cross-version identity matching."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    return _is_number(value) and math.isfinite(float(value))


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------
class InputError(Exception):
    """Raised when an input cannot be trusted. Always fatal (exit 2)."""


class _Point:
    """A normalized point row: an id plus a flat payload mapping."""

    __slots__ = ("point_id", "payload")

    def __init__(self, point_id: str, payload: dict[str, Any]) -> None:
        self.point_id = point_id
        self.payload = payload

    def get(self, *names: str, default: Any = None) -> Any:
        for name in names:
            if name in self.payload and self.payload[name] is not None:
                return self.payload[name]
        return default


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc


def _parse_json_or_jsonl(path: Path) -> Any:
    raw = _read_text(path)
    try:
        return json.loads(raw)
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
        return rows


def _load_points(path: Path) -> list[_Point]:
    """Load a Qdrant-style point export (JSON object, JSON list, or JSONL)."""
    data = _parse_json_or_jsonl(path)

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
            # A single point object (a one-line JSONL file parses as an object).
            if "payload" in data or "id" in data or "source_span_id" in data:
                raw_points = [data]
            else:
                raise InputError(f"{path}: no point list found (expected 'result.points')")
    else:
        raise InputError(f"{path}: unsupported top-level JSON type {type(data).__name__}")

    points: list[_Point] = []
    seen: dict[str, int] = {}
    for index, entry in enumerate(raw_points):
        if not isinstance(entry, dict):
            raise InputError(f"{path}: point #{index} is not an object")
        payload = entry.get("payload")
        if isinstance(payload, dict):
            raw_id = entry.get("id") or entry.get("point_id") or entry.get("_point_id")
            body = payload
        else:
            body = entry
            raw_id = entry.get("id") or entry.get("point_id") or entry.get("_point_id")
        if raw_id is None:
            raise InputError(f"{path}: point #{index} has no id")
        point_id = str(raw_id)
        if point_id in seen:
            raise InputError(
                f"{path}: duplicate point id {point_id!r} at positions "
                f"{seen[point_id]} and {index} — the export is structurally corrupt"
            )
        seen[point_id] = index
        points.append(_Point(point_id, body))
    return points


def _load_verdicts(path: Path) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Load the legacy ECAPA verdict file.

    Returns ``(verdicts_by_key, archive_metadata, malformed_record_keys)``.
    """
    data = _parse_json_or_jsonl(path)
    if not isinstance(data, dict):
        raise InputError(f"{path}: verdict file must be a JSON object")

    if isinstance(data.get("items"), dict):
        items = data["items"]
        archive = {k: v for k, v in data.items() if k != "items"}
    elif all(isinstance(v, dict) for v in data.values()) and data:
        items = data
        archive = {}
    else:
        raise InputError(f"{path}: verdict file has no 'items' mapping")

    verdicts: dict[str, Any] = {}
    malformed: list[str] = []
    for key in sorted(items):
        record = items[key]
        if not isinstance(record, dict):
            malformed.append(key)
            continue
        verdicts[key] = record
    return verdicts, archive, malformed


def _load_optional_mapping(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = _parse_json_or_jsonl(path)
    if not isinstance(data, dict):
        raise InputError(f"{path}: expected a JSON object keyed by record id")
    return data


# ---------------------------------------------------------------------------
# Verdict schema validation
# ---------------------------------------------------------------------------
_LEGACY_REQUIRED = ("verified", "method", "cosine", "margin", "predicted_guru", "payload_guru")

#: Release-grade provenance that every *verified* verdict must carry.
#: Mirrors the B1 exit gate in
#: ``docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md``.
_RELEASE_GRADE_PER_RECORD = (
    "verified",
    "method",
    "model_revision",
    "calibration_revision",
    "source_span_id",
    "audio_sha256",
    "start_ms",
    "end_ms",
    "cosine",
    "margin",
    "cosine_floor",
    "margin_threshold",
    "timestamp",
)

_RELEASE_GRADE_ARCHIVE = ("calibration_available", "cosine_floor", "margin_threshold")


def _check_legacy_fields(record: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for field in _LEGACY_REQUIRED:
        if field not in record:
            problems.append(f"missing_field:{field}")
    if "verified" in record and not isinstance(record["verified"], bool):
        problems.append("invalid_type:verified")
    for field in ("cosine", "margin"):
        if field in record and not _is_finite_number(record[field]):
            problems.append(f"non_finite:{field}")
    if "method" in record and not str(record["method"]).strip():
        problems.append("empty_method")
    return problems


def _check_release_grade(
    record: dict[str, Any], archive: dict[str, Any]
) -> list[str]:
    problems = _check_legacy_fields(record)
    for field in _RELEASE_GRADE_PER_RECORD:
        if field not in record:
            problems.append(f"missing_provenance:{field}")
    for field in _RELEASE_GRADE_ARCHIVE:
        if field not in archive:
            problems.append(f"missing_archive_provenance:{field}")
    if archive.get("calibration_available") is not True:
        problems.append("calibration_not_available")
    if "cosine_floor" in archive and not _is_finite_number(archive.get("cosine_floor")):
        problems.append("non_finite:cosine_floor")
    if "margin_threshold" in archive and not _is_finite_number(archive.get("margin_threshold")):
        problems.append("non_finite:margin_threshold")
    return problems


def validate_verdict(
    record: dict[str, Any], archive: dict[str, Any], policy: str
) -> list[str]:
    """Return the list of schema problems for one verdict record (empty = ok)."""
    if policy == POLICY_RELEASE_GRADE:
        return _check_release_grade(record, archive)
    if policy == POLICY_LEGACY_V1:
        return _check_legacy_fields(record)
    raise InputError(f"unknown verdict schema policy {policy!r}")


# ---------------------------------------------------------------------------
# Row extraction
# ---------------------------------------------------------------------------
def _span_text(payload: dict[str, Any]) -> str:
    for name in ("verbatim_text", "span_text", "source_transcript_text"):
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and float(value).is_integer():
        return int(value)
    return None


class _Span:
    """A v10 child span, flattened for matching."""

    __slots__ = (
        "point_id",
        "source_span_id",
        "video_id",
        "source_asset_id",
        "guru_id",
        "start_ms",
        "end_ms",
        "word_start",
        "word_end",
        "text",
        "declared_text_hash",
        "source_url",
        "row",
    )

    def __init__(self, row: _Point) -> None:
        payload = row.payload
        self.row = row
        self.point_id = row.point_id
        self.source_span_id = str(payload.get("source_span_id") or "")
        self.video_id = str(payload.get("video_id") or "")
        self.source_asset_id = str(payload.get("source_asset_id") or payload.get("video_id") or "")
        self.guru_id = str(payload.get("guru_id") or payload.get("teacher_id") or "")
        self.start_ms = _int_or_none(payload.get("start_ms", payload.get("audio_start_ms")))
        self.end_ms = _int_or_none(payload.get("end_ms", payload.get("audio_end_ms")))
        self.word_start = _int_or_none(payload.get("word_start"))
        self.word_end = _int_or_none(payload.get("word_end"))
        self.text = _span_text(payload)
        self.declared_text_hash = str(
            payload.get("source_text_hash") or payload.get("transcript_hash") or ""
        )
        self.source_url = str(payload.get("source_url") or payload.get("video_url") or "")

    @property
    def valid(self) -> bool:
        return bool(self.source_span_id) and bool(self.video_id) and bool(self.text)

    @property
    def computed_text_hash(self) -> str:
        return clip_text_hash(self.text)

    @property
    def computed_normalized_hash(self) -> str:
        return normalized_text_hash(self.text)


class _Legacy:
    """A legacy (v9) clip row, flattened for matching."""

    __slots__ = (
        "point_id",
        "video_id",
        "start_ms",
        "end_ms",
        "word_start",
        "word_end",
        "text",
        "declared_text_hash",
        "teacher_id",
        "source_url",
    )

    def __init__(self, row: _Point) -> None:
        payload = row.payload
        self.point_id = row.point_id
        self.video_id = str(payload.get("video_id") or "")
        self.start_ms = _int_or_none(payload.get("start_ms"))
        self.end_ms = _int_or_none(payload.get("end_ms"))
        self.word_start = _int_or_none(payload.get("word_start"))
        self.word_end = _int_or_none(payload.get("word_end"))
        self.text = _span_text(payload)
        self.declared_text_hash = str(
            payload.get("transcript_hash") or payload.get("source_text_hash") or ""
        )
        self.teacher_id = str(payload.get("teacher_id") or payload.get("guru_id") or "").lower()
        self.source_url = str(payload.get("source_url") or payload.get("video_url") or "")

    @property
    def computed_text_hash(self) -> str:
        return clip_text_hash(self.text)

    @property
    def computed_normalized_hash(self) -> str:
        return normalized_text_hash(self.text)


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------
class _LegacyIndex:
    """Deterministic lookup indexes over the legacy point export."""

    def __init__(self, legacy: list[_Legacy]) -> None:
        self.rows = legacy
        self.by_id = {row.point_id: row for row in legacy}
        self.by_strict: dict[tuple[Any, ...], list[str]] = defaultdict(list)
        self.by_relaxed: dict[tuple[Any, ...], list[str]] = defaultdict(list)
        self.by_words: dict[tuple[Any, ...], list[str]] = defaultdict(list)
        self.by_video_start: dict[tuple[Any, ...], list[str]] = defaultdict(list)
        for row in legacy:
            norm_hash = row.computed_normalized_hash
            if row.video_id and norm_hash and row.start_ms is not None:
                self.by_strict[
                    (row.video_id, norm_hash, row.start_ms, row.end_ms)
                ].append(row.point_id)
                self.by_relaxed[(row.video_id, norm_hash, row.start_ms)].append(row.point_id)
                self.by_video_start[(row.video_id, row.start_ms)].append(row.point_id)
            if (
                row.video_id
                and norm_hash
                and row.word_start is not None
                and row.word_end is not None
            ):
                self.by_words[
                    (row.video_id, norm_hash, row.word_start, row.word_end)
                ].append(row.point_id)

    def strict(self, key: tuple[Any, ...]) -> list[str]:
        return sorted(self.by_strict.get(key, ()))

    def relaxed(self, key: tuple[Any, ...]) -> list[str]:
        return sorted(self.by_relaxed.get(key, ()))

    def words(self, key: tuple[Any, ...]) -> list[str]:
        return sorted(self.by_words.get(key, ()))

    def video_start(self, key: tuple[Any, ...]) -> list[str]:
        return sorted(self.by_video_start.get(key, ()))


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------
class _Resolution:
    __slots__ = (
        "match_class",
        "legacy_point_id",
        "verdict_key",
        "candidate_count",
        "identity_fields",
        "reason",
        "conflict_fields",
    )

    def __init__(
        self,
        match_class: str,
        legacy_point_id: str | None = None,
        verdict_key: str | None = None,
        candidate_count: int = 0,
        identity_fields: tuple[str, ...] = (),
        reason: str | None = None,
        conflict_fields: tuple[str, ...] = (),
    ) -> None:
        self.match_class = match_class
        self.legacy_point_id = legacy_point_id
        self.verdict_key = verdict_key
        self.candidate_count = candidate_count
        self.identity_fields = identity_fields
        self.reason = reason
        self.conflict_fields = conflict_fields


def _resolve(
    span: _Span,
    index: _LegacyIndex,
    verdicts: dict[str, Any],
    tolerance_ms: int,
) -> _Resolution:
    """Resolve one v10 span against the legacy archive, in the documented order."""
    # 1. exact v10 source_span_id
    if span.source_span_id and span.source_span_id in verdicts:
        return _Resolution(
            MATCH_EXACT_SPAN_ID,
            legacy_point_id=None,
            verdict_key=span.source_span_id,
            candidate_count=1,
            identity_fields=("source_span_id",),
        )

    # 2. exact Qdrant point id
    if span.point_id and span.point_id in verdicts:
        return _Resolution(
            MATCH_EXACT_POINT_ID,
            legacy_point_id=None,
            verdict_key=span.point_id,
            candidate_count=1,
            identity_fields=("qdrant_point_id",),
        )

    norm_hash = span.computed_normalized_hash
    if not (span.video_id and norm_hash):
        return _Resolution(
            MATCH_INVALID_INPUT,
            reason="v10_span_missing_video_id_or_normalizable_text",
        )

    # 3. strict legacy identity tuple
    if span.start_ms is not None and span.end_ms is not None:
        strict = index.strict((span.video_id, norm_hash, span.start_ms, span.end_ms))
        if len(strict) == 1:
            return _Resolution(
                MATCH_UNIQUE_IDENTITY,
                legacy_point_id=strict[0],
                verdict_key=strict[0],
                candidate_count=1,
                identity_fields=(
                    "video_id",
                    "normalized_text_hash",
                    "start_ms",
                    "end_ms",
                ),
            )
        if len(strict) > 1:
            return _Resolution(
                MATCH_AMBIGUOUS_IDENTITY,
                candidate_count=len(strict),
                identity_fields=(
                    "video_id",
                    "normalized_text_hash",
                    "start_ms",
                    "end_ms",
                ),
                reason="duplicate_legacy_identity_key",
            )

    # 4. unique fallback on word coordinates (only when every field exists)
    if span.word_start is not None and span.word_end is not None:
        word_key = (span.video_id, norm_hash, span.word_start, span.word_end)
        words = index.words(word_key)
        if len(words) == 1:
            return _Resolution(
                MATCH_UNIQUE_IDENTITY,
                legacy_point_id=words[0],
                verdict_key=words[0],
                candidate_count=1,
                identity_fields=("video_id", "normalized_text_hash", "word_start", "word_end"),
                reason="word_coordinate_fallback",
            )
        if len(words) > 1:
            return _Resolution(
                MATCH_AMBIGUOUS_IDENTITY,
                candidate_count=len(words),
                identity_fields=("video_id", "normalized_text_hash", "word_start", "word_end"),
                reason="duplicate_legacy_word_identity_key",
            )

    # 5. relaxed identity (start only) — a unique hit here means the time bounds
    #    disagree, which is an identity conflict, never an upgrade.
    if span.start_ms is not None:
        relaxed = index.relaxed((span.video_id, norm_hash, span.start_ms))
        if len(relaxed) == 1:
            legacy_row = index.by_id[relaxed[0]]
            if legacy_row.end_ms is None or span.end_ms is None:
                conflict = ("end_ms",)
            else:
                conflict = ("end_ms",) if abs(legacy_row.end_ms - span.end_ms) > tolerance_ms else ()
            if conflict:
                return _Resolution(
                    MATCH_IDENTITY_CONFLICT,
                    legacy_point_id=relaxed[0],
                    verdict_key=relaxed[0],
                    candidate_count=1,
                    identity_fields=("video_id", "normalized_text_hash", "start_ms"),
                    reason="time_bound_mismatch",
                    conflict_fields=conflict,
                )
        elif len(relaxed) > 1:
            return _Resolution(
                MATCH_AMBIGUOUS_IDENTITY,
                candidate_count=len(relaxed),
                identity_fields=("video_id", "normalized_text_hash", "start_ms"),
                reason="duplicate_legacy_relaxed_identity_key",
            )

    # 6. video + start, text hash disagrees -> text-hash conflict
    if span.start_ms is not None:
        by_video = index.video_start((span.video_id, span.start_ms))
        if len(by_video) == 1:
            return _Resolution(
                MATCH_IDENTITY_CONFLICT,
                legacy_point_id=by_video[0],
                verdict_key=by_video[0],
                candidate_count=1,
                identity_fields=("video_id", "start_ms"),
                reason="text_hash_mismatch",
                conflict_fields=("normalized_text_hash",),
            )
        if len(by_video) > 1:
            return _Resolution(
                MATCH_AMBIGUOUS_IDENTITY,
                candidate_count=len(by_video),
                identity_fields=("video_id", "start_ms"),
                reason="duplicate_legacy_video_start_key",
            )

    # 7. nothing matched
    return _Resolution(
        MATCH_MISSING_LEGACY_POINT,
        candidate_count=0,
        identity_fields=("video_id", "normalized_text_hash", "start_ms", "end_ms"),
        reason="no_legacy_point_matches_any_identity_path",
    )


def _verdict_for(
    resolution: _Resolution, verdicts: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    if resolution.verdict_key is None:
        return None, "no_verdict_key"
    record = verdicts.get(resolution.verdict_key)
    if record is None:
        return None, "no_verdict_for_matched_key"
    return record, None


def reconcile(
    *,
    v10_points: list[_Point],
    legacy_points: list[_Point],
    verdicts: dict[str, Any],
    archive: dict[str, Any],
    malformed_verdict_keys: list[str],
    asr_manifest: dict[str, Any],
    policy: str,
    tolerance_ms: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reconcile every v10 child against the legacy archive."""
    spans = [_Span(row) for row in v10_points]
    legacy = [_Legacy(row) for row in legacy_points]
    index = _LegacyIndex(legacy)

    rows: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    schema_problem_counts: Counter[str] = Counter()
    safe_upgrade_count = 0
    identity_join_ok = 0
    unique_legacy_joins = 0
    verdict_attached = 0
    verdict_verified_true = 0
    text_checks: Counter[str] = Counter()
    video_checks: Counter[str] = Counter()
    time_checks: Counter[str] = Counter()
    asr_checks: Counter[str] = Counter()
    invalid_spans = 0
    malformed_verdict_observed = 0

    malformed_set = set(malformed_verdict_keys)
    for span in sorted(spans, key=lambda item: (item.source_span_id, item.point_id)):
        if not span.valid:
            invalid_spans += 1
            class_counts[MATCH_INVALID_INPUT] += 1
            reasons["v10_row_missing_required_identity_field"] += 1
            rows.append(
                {
                    "schema": ROW_SCHEMA,
                    "source_span_id": span.source_span_id or None,
                    "v10_point_id": span.point_id,
                    "legacy_point_id": None,
                    "verdict_key": None,
                    "match_class": MATCH_INVALID_INPUT,
                    "candidate_count": 0,
                    "identity_fields_used": [],
                    "v10_video_id": span.video_id or None,
                    "v10_source_asset_id": span.source_asset_id or None,
                    "v10_start_ms": span.start_ms,
                    "v10_end_ms": span.end_ms,
                    "v10_word_start": span.word_start,
                    "v10_word_end": span.word_end,
                    "v10_guru_id": span.guru_id or None,
                    "computed_text_hash": span.computed_text_hash if span.text else None,
                    "declared_text_hash": span.declared_text_hash or None,
                    "computed_normalized_text_hash": (
                        span.computed_normalized_hash if span.text else None
                    ),
                    "legacy_video_id": None,
                    "legacy_start_ms": None,
                    "legacy_end_ms": None,
                    "legacy_declared_text_hash": None,
                    "legacy_computed_text_hash": None,
                    "legacy_teacher_id": None,
                    "legacy_source_url": None,
                    "verdict": None,
                    "verdict_malformed": False,
                    "verdict_schema_problems": ["v10_row_missing_required_identity_field"],
                    "text_hash_check": "not_evaluated",
                    "video_source_check": "not_evaluated",
                    "time_bound_check": "not_evaluated",
                    "asr_manifest_check": "not_evaluated",
                    "identity_join_ok": False,
                    "safe_to_upgrade": False,
                    "safe_to_upgrade_blockers": ["v10_row_missing_required_identity_field"],
                    "reason": "v10_row_missing_required_identity_field",
                    "conflict_fields": [],
                    "quarantine_recommended": True,
                }
            )
            continue

        resolution = _resolve(span, index, verdicts, tolerance_ms)

        verdict_record, verdict_error = _verdict_for(resolution, verdicts)
        if resolution.verdict_key is not None and resolution.verdict_key in malformed_set:
            # The verdict file holds a record for this key that is not a usable
            # object. It is quarantined, never silently treated as absent.
            verdict_record = None
        schema_problems: list[str] = []
        structural_problems: list[str] = []
        if verdict_record is not None:
            structural_problems = _check_legacy_fields(verdict_record)
            schema_problems = validate_verdict(verdict_record, archive, policy)
            for problem in schema_problems:
                schema_problem_counts[problem] += 1

        # --- identity agreement checks ------------------------------------
        legacy_row = index.by_id.get(resolution.legacy_point_id) if resolution.legacy_point_id else None

        text_check = "not_evaluated"
        if legacy_row is not None:
            if span.computed_text_hash != span.declared_text_hash:
                text_check = "v10_declared_hash_mismatch"
            elif legacy_row.declared_text_hash and (
                legacy_row.computed_text_hash != legacy_row.declared_text_hash
            ):
                text_check = "legacy_declared_hash_mismatch"
            elif span.computed_normalized_hash != legacy_row.computed_normalized_hash:
                text_check = "normalized_text_hash_mismatch"
            else:
                text_check = "pass"
        elif resolution.match_class == MATCH_EXACT_SPAN_ID:
            text_check = "not_evaluated_direct_span_id"
        elif resolution.match_class == MATCH_EXACT_POINT_ID:
            text_check = "not_evaluated_direct_point_id"

        video_check = "not_evaluated"
        if legacy_row is not None:
            if span.video_id != legacy_row.video_id:
                video_check = "video_id_mismatch"
            elif (
                span.source_url
                and legacy_row.source_url
                and span.source_url != legacy_row.source_url
            ):
                video_check = "source_url_mismatch"
            else:
                video_check = "pass"
        elif resolution.match_class in (MATCH_EXACT_SPAN_ID, MATCH_EXACT_POINT_ID):
            video_check = "not_evaluated_direct_key"

        time_check = "not_evaluated"
        if legacy_row is not None:
            if span.start_ms is None or legacy_row.start_ms is None:
                time_check = "start_ms_unavailable"
            elif abs(span.start_ms - legacy_row.start_ms) > tolerance_ms:
                time_check = "start_ms_mismatch"
            elif span.end_ms is None or legacy_row.end_ms is None:
                time_check = "end_ms_unavailable"
            elif abs(span.end_ms - legacy_row.end_ms) > tolerance_ms:
                time_check = "end_ms_mismatch"
            else:
                time_check = "pass"
        elif resolution.match_class in (MATCH_EXACT_SPAN_ID, MATCH_EXACT_POINT_ID):
            time_check = "not_evaluated_direct_key"

        asr_check = "not_available"
        asr_row = asr_manifest.get(span.source_span_id) if asr_manifest else None
        if asr_row is not None:
            asr_start = _int_or_none(asr_row.get("audio_start_ms"))
            asr_end = _int_or_none(asr_row.get("audio_end_ms"))
            if asr_start is None or asr_end is None:
                asr_check = "asr_manifest_missing_window"
            elif span.start_ms != asr_start or span.end_ms != asr_end:
                asr_check = "asr_manifest_window_mismatch"
            elif asr_row.get("alignment_ok") is not True:
                asr_check = "asr_manifest_alignment_not_ok"
            else:
                asr_check = "pass"

        text_checks[text_check] += 1
        video_checks[video_check] += 1
        time_checks[time_check] += 1
        asr_checks[asr_check] += 1

        # --- promote missing_verdict --------------------------------------
        match_class = resolution.match_class
        if (
            match_class == MATCH_UNIQUE_IDENTITY
            and verdict_record is None
            and resolution.legacy_point_id is not None
        ):
            match_class = MATCH_MISSING_VERDICT
        if structural_problems or (
            resolution.verdict_key is not None and resolution.verdict_key in malformed_set
        ):
            # A verdict record that cannot be parsed as a verdict is malformed
            # input, not a missing verdict. It is quarantined either way.
            match_class = MATCH_INVALID_INPUT
            malformed_verdict_observed += 1
            schema_problems = sorted(
                set(schema_problems) | set(structural_problems) | {"malformed_record"}
            )

        if verdict_record is not None and not structural_problems:
            verdict_attached += 1
            if verdict_record.get("verified") is True:
                verdict_verified_true += 1

        # The *identity* join is independent of whether a verdict record exists:
        # a uniquely matched legacy clip with no verdict still proves that the
        # v10 span has a legacy predecessor.
        join_ok = (
            resolution.candidate_count == 1
            and resolution.match_class
            in (MATCH_EXACT_SPAN_ID, MATCH_EXACT_POINT_ID, MATCH_UNIQUE_IDENTITY)
            and text_check in ("pass", "not_evaluated_direct_span_id", "not_evaluated_direct_point_id")
            and video_check in ("pass", "not_evaluated_direct_key")
            and time_check in ("pass", "not_evaluated_direct_key")
        )
        if join_ok:
            identity_join_ok += 1
        if (
            resolution.legacy_point_id is not None
            and resolution.candidate_count == 1
            and resolution.match_class
            in (MATCH_EXACT_SPAN_ID, MATCH_EXACT_POINT_ID, MATCH_UNIQUE_IDENTITY)
        ):
            unique_legacy_joins += 1

        blockers: list[str] = []
        if match_class not in (
            MATCH_EXACT_SPAN_ID,
            MATCH_EXACT_POINT_ID,
            MATCH_UNIQUE_IDENTITY,
        ):
            blockers.append(f"match_class:{match_class}")
        if resolution.candidate_count != 1:
            blockers.append("candidate_count_not_one")
        if text_check not in ("pass", "not_evaluated_direct_span_id", "not_evaluated_direct_point_id"):
            blockers.append(f"text_hash_check:{text_check}")
        if video_check not in ("pass", "not_evaluated_direct_key"):
            blockers.append(f"video_source_check:{video_check}")
        if time_check not in ("pass", "not_evaluated_direct_key"):
            blockers.append(f"time_bound_check:{time_check}")
        if asr_check not in ("pass", "not_available"):
            blockers.append(f"asr_manifest_check:{asr_check}")
        if verdict_record is None:
            blockers.append("verdict_absent")
        else:
            for problem in schema_problems:
                blockers.append(f"verdict_schema:{problem}")

        safe = join_ok and verdict_record is not None and not schema_problems and not blockers
        if safe:
            safe_upgrade_count += 1

        class_counts[match_class] += 1
        if resolution.reason:
            reasons[resolution.reason] += 1

        rows.append(
            {
                "schema": ROW_SCHEMA,
                "source_span_id": span.source_span_id,
                "v10_point_id": span.point_id,
                "legacy_point_id": resolution.legacy_point_id,
                "verdict_key": resolution.verdict_key,
                "match_class": match_class,
                "candidate_count": resolution.candidate_count,
                "identity_fields_used": list(resolution.identity_fields),
                "v10_video_id": span.video_id,
                "v10_source_asset_id": span.source_asset_id,
                "v10_start_ms": span.start_ms,
                "v10_end_ms": span.end_ms,
                "v10_word_start": span.word_start,
                "v10_word_end": span.word_end,
                "v10_guru_id": span.guru_id,
                "v10_source_url": span.source_url or None,
                "computed_text_hash": span.computed_text_hash,
                "declared_text_hash": span.declared_text_hash or None,
                "computed_normalized_text_hash": span.computed_normalized_hash,
                "legacy_video_id": legacy_row.video_id if legacy_row else None,
                "legacy_start_ms": legacy_row.start_ms if legacy_row else None,
                "legacy_end_ms": legacy_row.end_ms if legacy_row else None,
                "legacy_declared_text_hash": legacy_row.declared_text_hash or None
                if legacy_row
                else None,
                "legacy_computed_text_hash": legacy_row.computed_text_hash if legacy_row else None,
                "legacy_teacher_id": legacy_row.teacher_id if legacy_row else None,
                "legacy_source_url": legacy_row.source_url or None if legacy_row else None,
                "verdict": verdict_record,
                "verdict_malformed": bool(structural_problems)
                or (
                    resolution.verdict_key is not None
                    and resolution.verdict_key in malformed_set
                ),
                "verdict_schema_problems": schema_problems,
                "text_hash_check": text_check,
                "video_source_check": video_check,
                "time_bound_check": time_check,
                "asr_manifest_check": asr_check,
                "identity_join_ok": join_ok,
                "safe_to_upgrade": safe,
                "safe_to_upgrade_blockers": blockers,
                "reason": resolution.reason,
                "conflict_fields": list(resolution.conflict_fields),
                "quarantine_recommended": not safe,
            }
        )

    total = len(spans)
    direct_span = class_counts[MATCH_EXACT_SPAN_ID]
    direct_point = class_counts[MATCH_EXACT_POINT_ID]
    unique = class_counts[MATCH_UNIQUE_IDENTITY]
    ambiguous = class_counts[MATCH_AMBIGUOUS_IDENTITY]
    missing_point = class_counts[MATCH_MISSING_LEGACY_POINT]
    missing_verdict = class_counts[MATCH_MISSING_VERDICT]
    conflicts = class_counts[MATCH_IDENTITY_CONFLICT]
    invalid = class_counts[MATCH_INVALID_INPUT]

    unbacked = total - verdict_attached
    unverified = total - verdict_verified_true

    release_reasons: list[str] = []
    if total == 0:
        release_reasons.append("no_v10_children_supplied")
    if direct_span == 0:
        release_reasons.append(
            "no_verdict_is_keyed_by_v10_source_span_id (direct span-keyed coverage is zero)"
        )
    if direct_point == 0:
        release_reasons.append(
            "no_verdict_is_keyed_by_v10_qdrant_point_id (direct point-keyed coverage is zero)"
        )
    if missing_point:
        release_reasons.append(f"{missing_point} v10 spans have no legacy predecessor")
    if missing_verdict:
        release_reasons.append(
            f"{missing_verdict} v10 spans map to a legacy clip that carries no acoustic verdict"
        )
    if ambiguous:
        release_reasons.append(f"{ambiguous} v10 spans match more than one legacy candidate")
    if conflicts:
        release_reasons.append(f"{conflicts} v10 spans have conflicting legacy identity evidence")
    if invalid:
        release_reasons.append(f"{invalid} v10 spans could not be evaluated")
    if malformed_verdict_keys:
        release_reasons.append(
            f"{len(malformed_verdict_keys)} verdict records are malformed and were quarantined"
        )
    if safe_upgrade_count < total:
        release_reasons.append(
            f"only {safe_upgrade_count}/{total} spans satisfy the "
            f"'{policy}' verdict-schema policy"
        )
    release_reasons.append(
        "no per-span acoustic evidence exists in this workspace; Phase 2 must re-run "
        "ECAPA over each span's own audio window"
    )

    summary = {
        "schema": SUMMARY_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "verdict_schema_policy": policy,
        "release_blocking": True,
        "release_blocking_reasons": release_reasons,
        "totals": {
            "v10_children": total,
            "rows_emitted": len(rows),
            "legacy_points": len(legacy),
            "verdict_records": len(verdicts),
            "malformed_verdict_records": len(malformed_verdict_keys) + malformed_verdict_observed,
            "malformed_verdict_records_not_objects": len(malformed_verdict_keys),
            "v10_spans_without_any_verdict": unbacked,
            "v10_spans_without_verified_true_verdict": unverified,
        },
        "match_class_counts": {name: class_counts.get(name, 0) for name in MATCH_CLASSES},
        "direct_span_id_coverage": {
            "v10_source_span_ids_present_in_verdict_file": direct_span,
            "pct_of_v10_children": round(100.0 * direct_span / total, 4) if total else None,
        },
        "direct_point_id_coverage": {
            "v10_qdrant_point_ids_present_in_verdict_file": direct_point,
            "pct_of_v10_children": round(100.0 * direct_point / total, 4) if total else None,
        },
        "legacy_identity_coverage": {
            "unique_legacy_points_resolved": unique_legacy_joins,
            "unique_identity_matches": unique,
            "ambiguous_identity_matches": ambiguous,
            "missing_legacy_point": missing_point,
            "identity_join_ok": identity_join_ok,
            "pct_identity_join_ok": round(100.0 * identity_join_ok / total, 4) if total else None,
        },
        "verdict_coverage": {
            "spans_with_any_verdict": verdict_attached,
            "spans_with_verified_true": verdict_verified_true,
            "spans_without_any_verdict": unbacked,
            "spans_without_verified_true": unverified,
            "pct_with_verified_true": round(100.0 * verdict_verified_true / total, 4)
            if total
            else None,
        },
        "safe_to_upgrade": {
            "count": safe_upgrade_count,
            "pct_of_v10_children": round(100.0 * safe_upgrade_count / total, 4) if total else None,
            "semantics": (
                "A legacy verdict is unambiguously joinable to this span. This is NOT "
                "independent per-span acoustic evidence."
            ),
            "policy_note": (
                "Under the 'release_grade' policy a verdict must carry model revision, "
                "calibration revision, per-span audio identity, span id, timestamps, "
                "cosine floor and margin threshold. The archived legacy verdict file "
                "predates the impostor-calibrated verifier and carries none of that, so "
                "safe_to_upgrade is false for every row under the default policy."
            ),
        },
        "quarantine": {
            "spans_recommended_for_quarantine": sum(1 for row in rows if row["quarantine_recommended"]),
            "spans_with_identity_join_ok": identity_join_ok,
        },
        "ambiguous_count": ambiguous,
        "conflicting_count": conflicts,
        "missing_count": missing_point + missing_verdict,
        "invalid_count": invalid,
        "check_outcomes": {
            "text_hash_check": dict(sorted(text_checks.items())),
            "video_source_check": dict(sorted(video_checks.items())),
            "time_bound_check": dict(sorted(time_checks.items())),
            "asr_manifest_check": dict(sorted(asr_checks.items())),
            "verdict_schema_problems": dict(sorted(schema_problem_counts.items())),
        },
        "reasons": dict(sorted(reasons.items())),
        "independent_per_span_evidence": {
            "available": False,
            "reason": (
                "This run only reconciles the archived legacy archive. It produces no new "
                "acoustic measurement. Per-span evidence requires Phase 2 (ECAPA over each "
                "span's own [start_ms, end_ms] slice with a held-out impostor calibration)."
            ),
        },
        "malformed_verdict_keys_sample": sorted(malformed_verdict_keys)[:10],
    }
    return rows, summary


# ---------------------------------------------------------------------------
# Qdrant read-only access
# ---------------------------------------------------------------------------
def _qdrant_scroll(base_url: str, collection: str) -> list[_Point]:
    """Scroll every point of a collection. READ-ONLY by construction.

    The only request issued is a scroll against ``/points/scroll``; no upsert,
    delete, alias or collection-management call exists in this module.
    """
    points: list[_Point] = []
    offset: Any = None
    while True:
        body: dict[str, Any] = {"limit": 256, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        request = urllib.request.Request(
            base_url.rstrip("/") + f"/collections/{collection}/points/scroll",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.load(response)
        if not isinstance(payload, dict):
            raise InputError("Qdrant returned a non-object response")
        result = payload.get("result") or {}
        for entry in result.get("points", []) or []:
            if isinstance(entry, dict):
                points.append(
                    _Point(str(entry.get("id")), dict(entry.get("payload") or {}))
                )
        offset = result.get("next_page_offset")
        if offset is None:
            return points


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only reconciliation of archived legacy ECAPA verdicts against v10 spans.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--v10-points",
        default=None,
        help="Export of the v10 children (JSON/JSONL). Preferred: no network access at all.",
    )
    parser.add_argument(
        "--qdrant-url",
        default=None,
        help="Read-only Qdrant URL. Only used when --v10-points is absent.",
    )
    parser.add_argument("--collection", default="first_person_v10")
    parser.add_argument("--legacy-points", required=True, help="Export of the legacy (v9) points.")
    parser.add_argument("--verdicts", required=True, help="Archived legacy ECAPA verdict JSON.")
    parser.add_argument(
        "--asr-manifest",
        default=None,
        help="Optional ASR/source-span manifest used for stronger identity validation.",
    )
    parser.add_argument("--out", required=True, help="Output JSONL path (one row per v10 child).")
    parser.add_argument("--summary", required=True, help="Output summary JSON path.")
    parser.add_argument(
        "--verdict-schema-policy",
        choices=VERDICT_SCHEMA_POLICIES,
        default=POLICY_RELEASE_GRADE,
        help=(
            "release_grade (default) requires full provenance on every verdict; "
            "legacy_v1 accepts the older archive schema and is NOT release evidence."
        ),
    )
    parser.add_argument("--time-tolerance-ms", type=int, default=0)
    parser.add_argument(
        "--generated-at-utc",
        default=None,
        help="Pin the summary timestamp so repeated runs are byte-identical.",
    )
    parser.add_argument(
        "--apply-upgrades",
        action="store_true",
        help="REJECTED. This script has no write mode and can never upgrade a payload.",
    )
    parser.add_argument(
        "--write-mode",
        action="store_true",
        help="REJECTED. This script is read-only.",
    )
    return parser


def _resolve_generated_at(value: str | None) -> str:
    if value:
        return value
    return _dt.datetime.now(_dt.UTC).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.apply_upgrades or args.write_mode:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "reason": "this script is read-only; write mode does not exist",
                    "script_version": SCRIPT_VERSION,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    try:
        if args.v10_points:
            v10_points = _load_points(Path(args.v10_points))
            v10_source = {
                "kind": "file",
                "path": str(Path(args.v10_points).resolve()),
                "sha256": _sha256_file(Path(args.v10_points)),
                "bytes": Path(args.v10_points).stat().st_size,
            }
        else:
            if not args.qdrant_url:
                raise InputError("--v10-points is required (or --qdrant-url for a read-only read)")
            raw = _qdrant_scroll(args.qdrant_url, args.collection)
            v10_points = [
                row for row in raw if (row.payload.get("record_type") or "") != "parent_unit"
            ]
            v10_source = {
                "kind": "qdrant_read_only",
                "url": args.qdrant_url,
                "collection": args.collection,
                "sha256": None,
                "bytes": None,
            }

        legacy_points = _load_points(Path(args.legacy_points))
        verdicts, archive, malformed = _load_verdicts(Path(args.verdicts))
        asr_manifest = _load_optional_mapping(
            Path(args.asr_manifest) if args.asr_manifest else None
        )
    except InputError as exc:
        print(
            json.dumps(
                {
                    "status": "invalid_input",
                    "error": str(exc),
                    "script_version": SCRIPT_VERSION,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(
            json.dumps(
                {
                    "status": "invalid_input",
                    "error": f"{type(exc).__name__}: {exc}",
                    "script_version": SCRIPT_VERSION,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT

    rows, summary = reconcile(
        v10_points=v10_points,
        legacy_points=legacy_points,
        verdicts=verdicts,
        archive=archive,
        malformed_verdict_keys=malformed,
        asr_manifest=asr_manifest,
        policy=args.verdict_schema_policy,
        tolerance_ms=args.time_tolerance_ms,
    )

    summary["inputs"] = {
        "v10_points": v10_source,
        "legacy_points": {
            "path": str(Path(args.legacy_points).resolve()),
            "sha256": _sha256_file(Path(args.legacy_points)),
            "bytes": Path(args.legacy_points).stat().st_size,
        },
        "verdicts": {
            "path": str(Path(args.verdicts).resolve()),
            "sha256": _sha256_file(Path(args.verdicts)),
            "bytes": Path(args.verdicts).stat().st_size,
        },
        "asr_manifest": (
            {
                "path": str(Path(args.asr_manifest).resolve()),
                "sha256": _sha256_file(Path(args.asr_manifest)),
                "bytes": Path(args.asr_manifest).stat().st_size,
            }
            if args.asr_manifest
            else None
        ),
    }
    summary["generated_at_utc"] = _resolve_generated_at(args.generated_at_utc)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "script_version": SCRIPT_VERSION,
                "verdict_schema_policy": args.verdict_schema_policy,
                "v10_children": summary["totals"]["v10_children"],
                "rows_emitted": summary["totals"]["rows_emitted"],
                "match_class_counts": summary["match_class_counts"],
                "safe_to_upgrade": summary["safe_to_upgrade"]["count"],
                "identity_join_ok": summary["legacy_identity_coverage"]["identity_join_ok"],
                "spans_without_any_verdict": summary["totals"]["v10_spans_without_any_verdict"],
                "spans_without_verified_true_verdict": summary["totals"][
                    "v10_spans_without_verified_true_verdict"
                ],
                "release_blocking": summary["release_blocking"],
                "out": str(out_path),
                "summary": str(summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return EXIT_RELEASE_BLOCKED if summary["release_blocking"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
