#!/usr/bin/env python3
"""Read-only data-quality scorecard for a first-person (fp-context-v1) points export.

**Read-only.** Never connects to Qdrant, never writes to a store, never edits
``verbatim_text`` or any hash. It reads one exported points file (and optionally
an older export to measure drift) and writes a JSON report plus, optionally, a
Markdown summary.

Why this exists
---------------
The other audits in ``scripts/ops`` answer one question each (boundaries,
speaker-verdict joins, strict contract). This is the single scorecard that
measures the data on the standard data-quality dimensions, with a fixed
threshold per check, so "how clean is the corpus" is one reproducible number set
that can be compared across exports and wired into a gate:

  completeness  required fields present and non-empty
  validity      types, hex ids, enum values
  integrity     sha256(verbatim_text) == source_text_hash; asr_cleaner applied (stored text is a fixed point of the cleaner)
  uniqueness    point id / source_span_id / (video, start, end); duplicate text
  consistency   boundary labels agree with the generic boundary detector;
                prev/next chain is closed and symmetric
  accuracy      edits of verbatim_text against the raw ASR text; speech rate
                (words per second) as a text/audio-window mismatch proxy
  evidence      speaker_verified is backed by a recorded verification method
  timeliness    export age; single corpus/ASR/schema lineage
  coverage      per-video and per-teacher concentration; opening-of-video clips

Severity: BLOCKER and HIGH failures make the exit code 1. MEDIUM and INFO never
do. Thresholds are *targets*, not a snapshot of today's defects: a check that
fails today is meant to fail until the data is fixed.

Exit codes
----------
0   every BLOCKER and HIGH check passes
1   report produced, at least one BLOCKER/HIGH check fails
2   input unreadable or contains no retrieval children (fail closed)

Usage
-----
    python -m scripts.ops.fp_data_quality_scorecard \\
        --points audits/evidence/public_release_v10_points_export_2026-10-21.json \\
        --out .work/dq/scorecard.json --md-out .work/dq/scorecard.md
    # drift against an older export:
    ... --baseline older_export.json
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import difflib
import hashlib
import json
import math
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

from ingest.verbatim.asr_cleaner import clean_verbatim_text  # noqa: E402
from ingest.verbatim.boundaries import boundary_defects  # noqa: E402

SCHEMA = "fp-data-quality-scorecard-v1"
EXAMPLE_CAP = 5
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SPEAKER_ROLES = {"guru", "host", "guest", "unknown"}
BOUNDARY_STATUSES = {"verified", "repaired", "uncertain"}
COMPLETENESS_STATUSES = {"complete", "fragment", "uncertain"}
REQUIRED_FIELDS = (
    "source_span_id",
    "video_id",
    "guru_id",
    "start_ms",
    "end_ms",
    "word_start",
    "word_end",
    "speaker_role",
    "speaker_verified",
    "verbatim_text",
    "source_transcript_text",
    "source_text_hash",
    "boundary_status",
    "completeness_status",
    "corpus_version",
    "schema_version",
    "asr_engine",
    "asr_model_version",
    "rights_cleared",
    "source_url",
)
LINEAGE_FIELDS = (
    "schema_version",
    "corpus_version",
    "asr_engine",
    "asr_model_version",
    "retrieval_text_version",
)

# Check id -> (dimension, severity, description, target, comparator).
# ``target`` is the maximum allowed value of the measured rate/count (or the
# minimum, when the comparator is "min").
DEFAULT_THRESHOLDS: dict[str, float] = {
    "missing_required_fields": 0,
    "invalid_values": 0,
    "text_hash_mismatch": 0,
    "script_mixed_or_loop": 0,
    "asr_clean_not_idempotent": 0,
    "asr_cleaner_two_pass_unstable": 0,
    "duplicate_identity": 0,
    "duplicate_text_rate": 0.005,
    "contained_in_other_span_rate": 0.05,
    "broken_chain": 0,
    "invalid_time_window": 0,
    "duration_out_of_band_rate": 0.05,
    "speech_rate_out_of_band_rate": 0.02,
    "short_text_rate": 0.02,
    "boundary_defect_rate": 0.10,
    "boundary_label_disagreement_rate": 0.02,
    "unverified_boundary_label_rate": 0.10,
    "text_edited_vs_source_rate": 0.10,
    "heavily_edited_vs_source_rate": 0.01,
    "speaker_verified_without_method": 0,
    "lineage_variants": 1,
    "export_age_days": 7,
    "max_video_share": 0.02,
    "min_guru_share": 0.30,
    "opening_clip_rate": 0.05,
    "strict_clean_rate": 0.60,
}
DURATION_BAND_S = (8.0, 60.0)
SPEECH_RATE_BAND = (1.0, 5.0)  # words per second; English speech sits near 2-3
MIN_WORDS = 15  # Tier 2 content floor (CLAUDE.md FP invariant 14)
OPENING_MS = 5_000
HEAVY_EDIT_RATIO = 0.15  # share of tokens changed vs raw ASR text


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
class InputError(Exception):
    """Unreadable or structurally unusable input."""


def _from_tier_row(r: dict[str, Any]) -> dict[str, Any]:
    """Map a corpus-tier / rebuilt-candidate row (``text``, ``audio_*_ms``,
    ``speaker_verdict``) onto the payload field names. Fields the row does not
    carry stay absent or ``uncertain``: the scorecard never invents a label."""
    verified = r.get("speaker_verdict") == "verified"
    return {
        "record_type": "retrieval_child",
        "source_span_id": r.get("source_span_id"),
        "video_id": r.get("video_id"),
        "guru_id": r.get("guru_id"),
        "start_ms": r.get("audio_start_ms"),
        "end_ms": r.get("audio_end_ms"),
        "word_start": r.get("word_start"),
        "word_end": r.get("word_end"),
        "speaker_role": "guru",
        "speaker_verified": verified,
        "voice_verification_method": (
            f"{r.get('speaker_model')}@{r.get('speaker_model_revision')}" if verified else None
        ),
        "verbatim_text": r.get("text"),
        "source_transcript_text": r.get("text") if r.get("reconstruction_exact") else None,
        "source_text_hash": r.get("source_text_hash"),
        "boundary_status": "uncertain",
        "completeness_status": "uncertain",
        "corpus_version": r.get("corpus_version"),
        "schema_version": r.get("schema"),
        "asr_engine": "timed_alignment" if r.get("timed_asr_model") else None,
        "asr_model_version": r.get("timed_asr_model"),
        "rights_cleared": str(r.get("rights_status", "")).startswith("confirmed"),
        "source_url": r.get("canonical_source_url"),
        # prev/next links point outside a tier subset, so they are not carried
        # over: the chain check is only meaningful on a full collection.
    }


def _payload_of(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    if "text" in row and "audio_start_ms" in row and "verbatim_text" not in row:
        return _from_tier_row(row)
    pl = row.get("payload") if isinstance(row.get("payload"), dict) else row
    out = dict(pl)
    if "id" in row and "point_id" not in out:
        out["point_id"] = str(row["id"])
    return out


def load_points(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (retrieval-child payloads, export metadata). Accepts the export
    envelope, a bare list of points/payloads, or JSONL."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    meta: dict[str, Any] = {}
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            raise InputError(f"{path} is neither JSON nor JSONL: {exc}") from exc
    if isinstance(data, dict) and not ({"result", "points"} & data.keys()):
        data = [data]  # a single row (one-line JSONL parses as one object)
    elif isinstance(data, dict):
        meta = {k: v for k, v in data.items() if k not in ("result", "points")}
        res = data.get("result", data)
        data = res.get("points", []) if isinstance(res, dict) else res
    if not isinstance(data, list):
        raise InputError(f"{path}: expected a list of points")
    rows = [p for p in (_payload_of(r) for r in data) if p is not None]
    children = [p for p in rows if p.get("record_type", "retrieval_child") == "retrieval_child"]
    meta["rows_total"] = len(rows)
    meta["rows_non_child"] = len(rows) - len(children)
    if not children:
        raise InputError(f"{path}: no retrieval_child records")
    return children, meta


# ---------------------------------------------------------------------------
# Check plumbing
# ---------------------------------------------------------------------------
def _sid(p: dict[str, Any]) -> str:
    return str(p.get("source_span_id") or p.get("point_id") or "")[:12]


def _json_safe(value: Any) -> Any:
    """Replace non-finite floats with None so strict JSON can always be emitted.

    ``_result`` already does this for ``measured``; this covers the rest of the
    report, including numbers captured inside ``examples`` by ``_example``.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _example(p: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "span": _sid(p),
        "video_id": p.get("video_id"),
        "start_ms": p.get("start_ms"),
        "head": str(p.get("verbatim_text") or "")[:70],
        **{k: _json_safe(v) for k, v in extra.items()},
    }


def _result(
    cid: str,
    dimension: str,
    severity: str,
    description: str,
    value: float,
    total: int,
    thresholds: dict[str, float],
    *,
    count: int | None = None,
    examples: Iterable[dict[str, Any]] = (),
    mode: str = "max",
    note: str = "",
) -> dict[str, Any]:
    target = thresholds[cid]
    ok = value >= target if mode == "min" else value <= target
    unit = (
        "days"
        if cid.endswith("_days")
        else "rate"
        if cid.endswith(("_rate", "_share"))
        else "count"
    )
    measured: float | int | None
    if isinstance(value, float):
        measured = round(value, 6) if math.isfinite(value) else None
    else:
        measured = value
    return {
        "id": cid,
        "unit": unit,
        "dimension": dimension,
        "severity": severity,
        "description": description,
        "measured": measured,
        "count": count,
        "of": total,
        "target": target,
        "target_kind": "at_least" if mode == "min" else "at_most",
        "status": "PASS" if ok else "FAIL",
        "note": note,
        "examples": list(examples)[:EXAMPLE_CAP],
    }


def _rate(n: int, total: int) -> float:
    return n / total if total else 0.0


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _words(text: str) -> list[str]:
    return text.split()


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def run_checks(
    pts: list[dict[str, Any]],
    thresholds: dict[str, float],
    *,
    exported_at: dt.datetime | None,
    now: dt.datetime,
) -> list[dict[str, Any]]:
    n = len(pts)
    out: list[dict[str, Any]] = []

    def add(cid: str, *a: Any, **k: Any) -> None:
        out.append(_result(cid, *a, thresholds=thresholds, **k))

    # -- completeness -------------------------------------------------------
    missing = [(p, [f for f in REQUIRED_FIELDS if p.get(f) in (None, "")]) for p in pts]
    missing = [(p, f) for p, f in missing if f]
    add(
        "missing_required_fields",
        "completeness",
        "BLOCKER",
        "spans missing a required fp-context-v1 field",
        float(len(missing)),
        n,
        count=len(missing),
        examples=[_example(p, missing=f) for p, f in missing],
    )

    # -- validity -----------------------------------------------------------
    invalid: list[tuple[dict[str, Any], str]] = []
    for p in pts:
        why = ""
        if not (_is_int(p.get("start_ms")) and _is_int(p.get("end_ms"))):
            why = "start_ms/end_ms not int"
        elif not (_is_int(p.get("word_start")) and _is_int(p.get("word_end"))):
            why = "word_start/word_end not int"
        elif not all(
            HEX64.match(str(p.get(k) or "")) for k in ("source_span_id", "source_text_hash")
        ):
            why = "id/hash not 64-hex"
        elif p.get("speaker_role") not in SPEAKER_ROLES:
            why = "speaker_role not in enum"
        elif p.get("boundary_status") not in BOUNDARY_STATUSES:
            why = "boundary_status not in enum"
        elif p.get("completeness_status") not in COMPLETENESS_STATUSES:
            why = "completeness_status not in enum"
        elif (
            _is_int(p.get("word_start"))
            and _is_int(p.get("word_end"))
            and p["word_end"] < p["word_start"]
        ):
            why = "word_end < word_start"
        if why:
            invalid.append((p, why))
    add(
        "invalid_values",
        "validity",
        "BLOCKER",
        "spans with a type/enum/hex violation",
        float(len(invalid)),
        n,
        count=len(invalid),
        examples=[_example(p, why=w) for p, w in invalid],
    )

    # -- integrity ----------------------------------------------------------
    bad_hash = [
        p
        for p in pts
        if hashlib.sha256(str(p.get("verbatim_text", "")).encode("utf-8")).hexdigest()
        != str(p.get("source_text_hash", "")).lower()
    ]
    add(
        "text_hash_mismatch",
        "integrity",
        "BLOCKER",
        "sha256(verbatim_text) != source_text_hash (served text would quarantine)",
        float(len(bad_hash)),
        n,
        count=len(bad_hash),
        examples=[_example(p) for p in bad_hash],
    )
    not_idem = [
        p
        for p in pts
        if clean_verbatim_text(str(p.get("verbatim_text", ""))) != p.get("verbatim_text")
    ]
    # NOTE the key is historical: this counts text that was stored UNCLEANED
    # (the cleaner would still change it), i.e. invariant 13 was not applied
    # before hashing. It is NOT a cleaner-idempotence defect; measured
    # 2026-10-25 the cleaner is idempotent on all 2,737 live and 1,529
    # candidate spans (see ``asr_cleaner_two_pass_unstable`` below). The key is
    # kept so committed reports and ``--baseline`` drift stay comparable.
    add(
        "asr_clean_not_idempotent",
        "integrity",
        "MEDIUM",
        "text stored uncleaned: asr_cleaner would still change it (FP invariant 13: clean before hashing)",
        float(len(not_idem)),
        n,
        count=len(not_idem),
        examples=[_example(p) for p in not_idem],
    )

    from ingest.verbatim.gates import script_and_loop_problem

    garbage_spans = [
        p for p in pts
        if script_and_loop_problem(str(p.get("verbatim_text", ""))) is not None
    ]
    add(
        "script_mixed_or_loop",
        "integrity",
        "BLOCKER",
        "mixed foreign scripts (>2%) or character/word ASR decoder loops",
        float(len(garbage_spans)),
        n,
        count=len(garbage_spans),
        examples=[
            _example(p, problem=script_and_loop_problem(str(p.get("verbatim_text", ""))))
            for p in garbage_spans
        ],
    )

    # A true idempotence check: clean(clean(t)) must equal clean(t), otherwise a
    # rebuild that cleans once can still emit text a second run would change,
    # which silently moves transcript_hash between builds.
    unstable = []
    for p in pts:
        once = clean_verbatim_text(str(p.get("verbatim_text", "")))
        if clean_verbatim_text(once) != once:
            unstable.append(p)
    add(
        "asr_cleaner_two_pass_unstable",
        "integrity",
        "HIGH",
        "asr_cleaner is not idempotent on this text (second pass changes the first pass output)",
        float(len(unstable)),
        n,
        count=len(unstable),
        examples=[_example(p) for p in unstable],
    )

    # -- uniqueness ---------------------------------------------------------
    keys = collections.Counter()
    for p in pts:
        keys[("pid", p.get("point_id"))] += 1 if p.get("point_id") else 0
        keys[("span", p.get("source_span_id"))] += 1
        keys[("win", p.get("video_id"), p.get("start_ms"), p.get("end_ms"))] += 1
    dup_keys = {k: v for k, v in keys.items() if v > 1}
    add(
        "duplicate_identity",
        "uniqueness",
        "BLOCKER",
        "duplicate point id, source_span_id or (video, start, end)",
        float(len(dup_keys)),
        n,
        count=len(dup_keys),
        examples=[{"key": [str(x)[:16] for x in k], "copies": v} for k, v in dup_keys.items()],
    )
    text_count = collections.Counter(str(p.get("verbatim_text", "")).strip() for p in pts)
    dup_rows = [p for p in pts if text_count[str(p.get("verbatim_text", "")).strip()] > 1]
    add(
        "duplicate_text_rate",
        "uniqueness",
        "MEDIUM",
        "spans whose text is identical to another span's",
        _rate(len(dup_rows), n),
        n,
        count=len(dup_rows),
        examples=[_example(p) for p in dup_rows],
        note="same words served from two spans inflate coverage and waste top-k slots",
    )
    by_video: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for p in pts:
        if _is_int(p.get("start_ms")) and _is_int(p.get("end_ms")):
            by_video[str(p.get("video_id"))].append(p)
    contained: dict[str, dict[str, Any]] = {}
    for spans in by_video.values():
        spans.sort(key=lambda s: (s["start_ms"], -s["end_ms"]))
        for i, a in enumerate(spans):
            for b in spans[i + 1 :]:
                if b["start_ms"] >= a["end_ms"]:
                    break
                if b["end_ms"] <= a["end_ms"] and (a["start_ms"], a["end_ms"]) != (
                    b["start_ms"],
                    b["end_ms"],
                ):
                    contained[_sid(b)] = b
    add(
        "contained_in_other_span_rate",
        "uniqueness",
        "MEDIUM",
        "spans fully inside another span of the same video (redundant windows)",
        _rate(len(contained), n),
        n,
        count=len(contained),
        examples=[_example(p) for p in contained.values()],
    )

    # -- consistency: prev/next chain ----------------------------------------
    by_id = {str(p.get("source_span_id")): p for p in pts}
    broken: list[tuple[dict[str, Any], str]] = []
    for p in pts:
        for ref, back, label in (
            ("next_span_id", "previous_span_id", "next"),
            ("previous_span_id", "next_span_id", "previous"),
        ):
            tgt = p.get(ref)
            if not tgt:
                continue
            other = by_id.get(str(tgt))
            if other is None:
                broken.append((p, f"{label} dangling"))
            elif str(other.get(back)) != str(p.get("source_span_id")):
                broken.append((p, f"{label} not symmetric"))
    add(
        "broken_chain",
        "consistency",
        "HIGH",
        "prev/next links that dangle or are not symmetric",
        float(len(broken)),
        n,
        count=len(broken),
        examples=[_example(p, why=w) for p, w in broken],
    )

    # -- timing / accuracy ---------------------------------------------------
    bad_window = [
        p
        for p in pts
        if _is_int(p.get("start_ms"))
        and _is_int(p.get("end_ms"))
        and (p["start_ms"] < 0 or p["end_ms"] <= p["start_ms"])
    ]
    add(
        "invalid_time_window",
        "validity",
        "BLOCKER",
        "negative start or end <= start",
        float(len(bad_window)),
        n,
        count=len(bad_window),
        examples=[_example(p) for p in bad_window],
    )
    timed = [
        p
        for p in pts
        if p not in bad_window and _is_int(p.get("start_ms")) and _is_int(p.get("end_ms"))
    ]
    durations = [(p["end_ms"] - p["start_ms"]) / 1000.0 for p in timed]
    off_band = [
        (p, d)
        for p, d in zip(timed, durations, strict=True)
        if not DURATION_BAND_S[0] <= d <= DURATION_BAND_S[1]
    ]
    add(
        "duration_out_of_band_rate",
        "accuracy",
        "HIGH",
        f"spans shorter than {DURATION_BAND_S[0]:.0f}s or longer than {DURATION_BAND_S[1]:.0f}s",
        _rate(len(off_band), n),
        n,
        count=len(off_band),
        examples=[
            _example(p, duration_s=round(d, 1)) for p, d in sorted(off_band, key=lambda x: -x[1])
        ],
        note="a multi-minute 'clip' is not a quotable passage and breaks playback",
    )
    odd_rate: list[tuple[dict[str, Any], float]] = []
    for p, d in zip(timed, durations, strict=True):
        wps = len(_words(str(p.get("verbatim_text", "")))) / d
        if not SPEECH_RATE_BAND[0] <= wps <= SPEECH_RATE_BAND[1]:
            odd_rate.append((p, wps))
    add(
        "speech_rate_out_of_band_rate",
        "accuracy",
        "HIGH",
        f"words/second outside {SPEECH_RATE_BAND}: text and audio window disagree",
        _rate(len(odd_rate), n),
        n,
        count=len(odd_rate),
        examples=[
            _example(p, words_per_s=round(w, 2)) for p, w in sorted(odd_rate, key=lambda x: x[1])
        ],
        note="cheap proxy for blocker B2 (citation text does not fit the cited audio window)",
    )
    short = [p for p in pts if len(_words(str(p.get("verbatim_text", "")))) < MIN_WORDS]
    add(
        "short_text_rate",
        "accuracy",
        "MEDIUM",
        f"spans under {MIN_WORDS} words (Tier 2 floor)",
        _rate(len(short), n),
        n,
        count=len(short),
        examples=[_example(p) for p in short],
    )

    # -- boundary quality & label reliability --------------------------------
    defects = {_sid(p): boundary_defects(_words(str(p.get("verbatim_text", "")))) for p in pts}
    defective = [p for p in pts if defects[_sid(p)]]
    kinds = collections.Counter(d for p in defective for d in defects[_sid(p)])
    add(
        "boundary_defect_rate",
        "accuracy",
        "HIGH",
        "spans where the generic boundary detector finds a head/tail defect",
        _rate(len(defective), n),
        n,
        count=len(defective),
        examples=[_example(p, defects=defects[_sid(p)]) for p in defective],
        note="defect kinds: " + ", ".join(f"{k}={v}" for k, v in kinds.most_common()),
    )
    disagree = [
        p
        for p in defective
        if p.get("boundary_status") == "verified" and p.get("completeness_status") == "complete"
    ]
    add(
        "boundary_label_disagreement_rate",
        "consistency",
        "HIGH",
        "labelled boundary=verified AND completeness=complete, yet the detector finds a defect",
        _rate(len(disagree), n),
        n,
        count=len(disagree),
        examples=[_example(p, defects=defects[_sid(p)]) for p in disagree],
        note="the labels cannot be trusted as a quality filter while this is non-zero",
    )
    unverified = [
        p
        for p in pts
        if p.get("boundary_status") != "verified" or p.get("completeness_status") != "complete"
    ]
    add(
        "unverified_boundary_label_rate",
        "accuracy",
        "MEDIUM",
        "spans labelled boundary!=verified or completeness!=complete",
        _rate(len(unverified), n),
        n,
        count=len(unverified),
        examples=[_example(p) for p in unverified],
    )

    # -- accuracy: edits against the raw ASR text ----------------------------
    edited = 0
    heavy: list[tuple[dict[str, Any], float]] = []
    for p in pts:
        src = _words(re.sub(r"[^\w\s']", "", str(p.get("source_transcript_text", "")).lower()))
        ver = _words(re.sub(r"[^\w\s']", "", str(p.get("verbatim_text", "")).lower()))
        if src == ver:
            continue
        edited += 1
        changed = 1.0 - difflib.SequenceMatcher(None, src, ver, autojunk=False).ratio()
        if changed > HEAVY_EDIT_RATIO:
            heavy.append((p, changed))
    add(
        "text_edited_vs_source_rate",
        "accuracy",
        "HIGH",
        "spans whose words differ from the raw ASR text (ignoring case/punctuation)",
        _rate(edited, n),
        n,
        count=edited,
        note="no per-span record says which stage changed the words or why; the audio is the only ground truth",
    )
    add(
        "heavily_edited_vs_source_rate",
        "accuracy",
        "HIGH",
        f"spans with more than {HEAVY_EDIT_RATIO:.0%} of tokens changed vs raw ASR",
        _rate(len(heavy), n),
        n,
        count=len(heavy),
        examples=[_example(p, changed=round(c, 3)) for p, c in sorted(heavy, key=lambda x: -x[1])],
    )

    # -- evidence ------------------------------------------------------------
    no_method = [
        p
        for p in pts
        if p.get("speaker_verified") is True and not p.get("voice_verification_method")
    ]
    add(
        "speaker_verified_without_method",
        "evidence",
        "BLOCKER",
        "speaker_verified=true with no recorded voice_verification_method",
        float(len(no_method)),
        n,
        count=len(no_method),
        examples=[_example(p) for p in no_method],
        note="a payload flag is a claim, not evidence; absence of a method must read as unverified",
    )

    # -- timeliness / lineage -------------------------------------------------
    variants = {f: sorted({str(p.get(f)) for p in pts}) for f in LINEAGE_FIELDS}
    worst = max(len(v) for v in variants.values())
    add(
        "lineage_variants",
        "timeliness",
        "MEDIUM",
        "max distinct values of any lineage field (schema/corpus/ASR/retrieval versions)",
        float(worst),
        n,
        note=json.dumps({k: v for k, v in variants.items() if len(v) > 1}) or "uniform",
    )
    age = (now - exported_at).total_seconds() / 86400 if exported_at else None
    add(
        "export_age_days",
        "timeliness",
        "MEDIUM",
        "days between the export and now (stale exports describe a collection that may have moved)",
        round(age, 2) if age is not None else float("inf"),
        n,
        note="" if age is not None else "export carries no exported_at_utc; treated as stale",
    )

    # -- coverage -------------------------------------------------------------
    vids = collections.Counter(str(p.get("video_id")) for p in pts)
    top_vid, top_n = vids.most_common(1)[0]
    add(
        "max_video_share",
        "coverage",
        "MEDIUM",
        "largest share of spans held by one video",
        _rate(top_n, n),
        n,
        count=top_n,
        examples=[{"video_id": v, "spans": c} for v, c in vids.most_common(EXAMPLE_CAP)],
        note=f"{len(vids)} videos; top video {top_vid}",
    )
    gurus = collections.Counter(str(p.get("guru_id")) for p in pts)
    add(
        "min_guru_share",
        "coverage",
        "MEDIUM",
        "smallest teacher share of spans",
        _rate(min(gurus.values()), n),
        n,
        mode="min",
        note=", ".join(f"{g}={c}" for g, c in gurus.most_common()),
    )
    opening = [p for p in timed if p["start_ms"] < OPENING_MS]
    add(
        "opening_clip_rate",
        "coverage",
        "MEDIUM",
        f"spans starting in the first {OPENING_MS // 1000}s of a video (greetings, hub intros)",
        _rate(len(opening), n),
        n,
        count=len(opening),
        examples=[_example(p) for p in opening],
    )

    # -- headline: spans that pass every span-level check -----------------------
    # Opening-of-video and unverified-label spans are reported above but do not
    # disqualify a span here: they are risks, not defects.
    bad: set[int] = set()
    for group in (
        [p for p, _ in missing],
        [p for p, _ in invalid],
        bad_hash,
        not_idem,
        dup_rows,
        list(contained.values()),
        [p for p, _ in broken],
        bad_window,
        [p for p, _ in off_band],
        [p for p, _ in odd_rate],
        short,
        defective,
        [p for p, _ in heavy],
        no_method,
        garbage_spans,
    ):
        bad.update(id(p) for p in group)
    strict = n - len(bad)
    add(
        "strict_clean_rate",
        "accuracy",
        "HIGH",
        "spans passing every span-level check (hash, cleaning, duration, speech rate, "
        "boundaries, length, redundancy, speaker evidence, edits)",
        _rate(strict, n),
        n,
        count=strict,
        mode="min",
        note="data-side counterpart of the '~1 in 7 clips is clean' judge estimate",
    )

    return out


def summarize(checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [c for c in checks if c["status"] == "FAIL"]
    gating = [c for c in failed if c["severity"] in ("BLOCKER", "HIGH")]
    by_dim: dict[str, dict[str, int]] = {}
    for c in checks:
        d = by_dim.setdefault(c["dimension"], {"pass": 0, "fail": 0})
        d["pass" if c["status"] == "PASS" else "fail"] += 1
    return {
        "checks": len(checks),
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "gating_failures": [c["id"] for c in gating],
        "verdict": "FAIL" if gating else "PASS",
        "by_dimension": by_dim,
    }


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------
def drift(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> dict[str, Any]:
    o = {str(p.get("source_span_id")): p for p in old}
    nw = {str(p.get("source_span_id")): p for p in new}
    added, removed = nw.keys() - o.keys(), o.keys() - nw.keys()
    common = o.keys() & nw.keys()
    text_changed = [
        i for i in common if o[i].get("source_text_hash") != nw[i].get("source_text_hash")
    ]
    flag_changed = [
        i
        for i in common
        if (o[i].get("speaker_verified"), o[i].get("rights_cleared"), o[i].get("boundary_status"))
        != (
            nw[i].get("speaker_verified"),
            nw[i].get("rights_cleared"),
            nw[i].get("boundary_status"),
        )
    ]
    return {
        "old_spans": len(o),
        "new_spans": len(nw),
        "added": len(added),
        "removed": len(removed),
        "id_churn_rate": _rate(len(added) + len(removed), max(len(o), 1)),
        "text_changed_same_id": len(text_changed),
        "flags_changed_same_id": len(flag_changed),
        "examples": {
            "added": sorted(added)[:EXAMPLE_CAP],
            "removed": sorted(removed)[:EXAMPLE_CAP],
            "text_changed": sorted(text_changed)[:EXAMPLE_CAP],
        },
    }


# ---------------------------------------------------------------------------
# Rendering / CLI
# ---------------------------------------------------------------------------
def _fmt(v: float | None, unit: str) -> str:
    if v is None:
        return "n/a"
    if unit == "rate":
        return f"{v:.2%}"
    if unit == "days":
        return f"{v:.1f} d"
    return str(int(v)) if float(v).is_integer() else str(v)


def render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"# First-person data-quality scorecard ({report['source']})",
        "",
        f"Verdict: **{s['verdict']}** — {s['passed']}/{s['checks']} checks pass; "
        f"gating failures: {', '.join(s['gating_failures']) or 'none'}.",
        f"Spans: {report['spans']}. Generated {report['generated_at']}.",
        "",
        "| Check | Severity | Measured | Target | Status |",
        "|---|---|---|---|---|",
    ]
    for c in report["checks"]:
        meas, tgt = _fmt(c["measured"], c["unit"]), _fmt(c["target"], c["unit"])
        op = "≥" if c["target_kind"] == "at_least" else "≤"
        cnt = f" ({c['count']}/{c['of']})" if c["count"] is not None else ""
        lines.append(f"| {c['id']} | {c['severity']} | {meas}{cnt} | {op} {tgt} | {c['status']} |")
    if "drift" in report:
        d = report["drift"]
        lines += [
            "",
            f"Drift: +{d['added']} / -{d['removed']} spans, {d['text_changed_same_id']} text changes on the same id.",
        ]
    return "\n".join(lines) + "\n"


def build_report(
    pts: list[dict[str, Any]],
    meta: dict[str, Any],
    *,
    source: str,
    thresholds: dict[str, float] | None = None,
    now: dt.datetime | None = None,
    baseline: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    thr = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    now = now or dt.datetime.now(dt.UTC)
    exported_at = None
    if meta.get("exported_at_utc"):
        try:
            exported_at = dt.datetime.fromisoformat(str(meta["exported_at_utc"]))
            if exported_at.tzinfo is None:
                exported_at = exported_at.replace(tzinfo=dt.UTC)
        except ValueError:
            exported_at = None
    checks = run_checks(pts, thr, exported_at=exported_at, now=now)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": now.isoformat(),
        "source": source,
        "spans": len(pts),
        "export_meta": {
            k: meta[k]
            for k in ("schema", "collection", "exported_at_utc", "rows_non_child")
            if k in meta
        },
        "read_only": True,
        "summary": summarize(checks),
        "checks": checks,
    }
    if baseline is not None:
        report["drift"] = drift(baseline, pts)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--points", type=Path, required=True, help="points export (JSON envelope, list, or JSONL)"
    )
    ap.add_argument("--baseline", type=Path, default=None, help="older export, for drift")
    ap.add_argument(
        "--thresholds", type=Path, default=None, help="JSON overriding DEFAULT_THRESHOLDS"
    )
    ap.add_argument(
        "--redact-text",
        action="store_true",
        help="drop teacher text from examples (use before committing a report: the repo is public)",
    )
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--md-out", type=Path, default=None)
    args = ap.parse_args(argv)
    try:
        pts, meta = load_points(args.points)
        base = load_points(args.baseline)[0] if args.baseline else None
        overrides = json.loads(args.thresholds.read_text()) if args.thresholds else None
    except (InputError, OSError, json.JSONDecodeError) as exc:
        print(f"fp_data_quality_scorecard: {exc}", file=sys.stderr)
        return 2
    report = build_report(pts, meta, source=args.points.name, thresholds=overrides, baseline=base)
    if args.redact_text:
        for c in report["checks"]:
            for ex in c["examples"]:
                ex.pop("head", None)
    # Sanitise anywhere a non-finite float can hide (measured, examples, drift,
    # percentiles) BEFORE the strict dump: allow_nan=False must never fail a run
    # that has an otherwise honest report.
    report = _json_safe(report)
    text = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(report), encoding="utf-8")
    s = report["summary"]
    print(
        f"{s['verdict']}: {s['passed']}/{s['checks']} checks pass over {report['spans']} spans; "
        f"gating failures: {', '.join(s['gating_failures']) or 'none'}"
    )
    return 0 if s["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
