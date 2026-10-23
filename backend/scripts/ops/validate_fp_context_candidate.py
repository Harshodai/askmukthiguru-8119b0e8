"""Dry-run validator/planner for fp-context-v1 candidate builds — Phase 4.

Accepts owner-provided ASR, rights, and speaker-review manifests plus a
source-span input JSONL. Validates all fp-context-v1 contract requirements,
emits a candidate JSONL (valid records only) and a quarantine JSONL (failures
with reason codes). Cannot connect to Qdrant or mutate anything.

Usage:
  python validate_fp_context_candidate.py \\
    --asr-manifest path/to/asr.json \\
    --rights-manifest path/to/rights.json \\
    --speaker-manifest path/to/speaker_review.json \\
    --source-spans path/to/source_spans.jsonl \\
    --candidate-out path/to/candidate.jsonl \\
    --quarantine-out path/to/quarantine.jsonl

Exits non-zero if any required manifest is missing/malformed or if zero
valid records are produced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Sentinel for graceful-degradation strings (L-INGEST-2)
# ---------------------------------------------------------------------------
_GRACEFUL_DEGRADATION_PHRASES = [
    "I'm currently experiencing a temporary connection issue",
    "temporarily unavailable",
    "I apologize, but I am unable",
    "I cannot access",
]


def _is_graceful_degradation(text: str) -> bool:
    """Return True if text is a provider canned failure string."""
    return any(phrase.lower() in text.lower() for phrase in _GRACEFUL_DEGRADATION_PHRASES)


# ---------------------------------------------------------------------------
# UUID v5 helper (mirrors first_person_context.py)
# ---------------------------------------------------------------------------
import uuid

_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace


def _make_uuid5(name: str) -> str:
    return str(uuid.uuid5(_NS, name))


# ---------------------------------------------------------------------------
# Validation gates
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Single record validation failure with a machine-readable reason code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"[{code}] {detail}")


def _require_str(value: Any, field: str) -> str:
    """Require a non-empty string value."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(
            "MISSING_FIELD", f"'{field}' must be a non-empty string, got {value!r}"
        )
    return value.strip()


def _require_int_ge_zero(value: Any, field: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValidationError(
            "INVALID_FIELD", f"'{field}' must be a non-negative int, got {value!r}"
        )
    return value


def _validate_asr_evidence(span: dict, asr_lookup: dict) -> dict:
    """Cross-check span against ASR manifest and return merged asr fields."""
    span_id = span.get("source_span_id", "")
    asr = asr_lookup.get(span_id)
    if asr is None:
        raise ValidationError("MISSING_ASR", f"No ASR entry for source_span_id={span_id!r}")
    # Require word-level timing fields
    for field in ("audio_start_ms", "audio_end_ms", "asr_engine", "asr_model_version"):
        if asr.get(field) is None:
            raise ValidationError(
                "MISSING_ASR_FIELD", f"ASR manifest missing '{field}' for span {span_id!r}"
            )
    start = _require_int_ge_zero(asr["audio_start_ms"], "audio_start_ms")
    end = _require_int_ge_zero(asr["audio_end_ms"], "audio_end_ms")
    if end <= start:
        raise ValidationError(
            "BOUNDARY_INVERSION",
            f"audio_end_ms({end}) <= audio_start_ms({start}) for span {span_id!r}",
        )
    return {
        "audio_start_ms": start,
        "audio_end_ms": end,
        "asr_engine": _require_str(asr["asr_engine"], "asr_engine"),
        "asr_model_version": _require_str(asr["asr_model_version"], "asr_model_version"),
        "caption_status": asr.get("caption_status", "asr_only"),
        "boundary_status": asr.get("boundary_status", "verified"),
    }


def _validate_rights(span: dict, rights_lookup: dict) -> None:
    """Assert rights are explicitly cleared for this span's asset."""
    asset_id = span.get("source_asset_id")
    if not asset_id:
        raise ValidationError("MISSING_ASSET_ID", "source_asset_id is required for rights check")
    entry = rights_lookup.get(asset_id)
    if entry is None:
        raise ValidationError(
            "NO_RIGHTS_ENTRY", f"No rights entry for source_asset_id={asset_id!r}"
        )
    if entry.get("rights_cleared") is not True:
        raise ValidationError(
            "RIGHTS_NOT_CLEARED",
            f"rights_cleared is not true for asset {asset_id!r}: {entry.get('rights_cleared')!r}",
        )


def _validate_speaker(span: dict, speaker_lookup: dict) -> dict:
    """Assert speaker is explicitly verified in the review manifest."""
    span_id = span.get("source_span_id", "")
    entry = speaker_lookup.get(span_id)
    if entry is None:
        raise ValidationError(
            "MISSING_SPEAKER_REVIEW", f"No speaker review entry for span {span_id!r}"
        )
    if entry.get("speaker_verified") is not True:
        raise ValidationError(
            "SPEAKER_NOT_VERIFIED",
            f"speaker_verified is not true for span {span_id!r}: {entry.get('speaker_verified')!r}",
        )
    # Require all typed speaker fields
    for field in ("speaker_id", "speaker_role", "guru_id"):
        if not entry.get(field):
            raise ValidationError(
                "MISSING_SPEAKER_FIELD", f"Speaker manifest missing '{field}' for span {span_id!r}"
            )
    allowed_roles = ("guru", "host", "guest", "unknown")
    if entry["speaker_role"] not in allowed_roles:
        raise ValidationError(
            "INVALID_SPEAKER_ROLE", f"speaker_role={entry['speaker_role']!r} not in {allowed_roles}"
        )
    if entry["speaker_role"] != "guru":
        raise ValidationError(
            "SPEAKER_NOT_GURU",
            f"Only guru-role spans may enter the fp-context candidate; got role={entry['speaker_role']!r}",
        )
    return {
        "speaker_verified": True,
        "speaker_id": entry["speaker_id"],
        "speaker_role": entry["speaker_role"],
        "guru_id": entry["guru_id"],
        "teacher_id": entry.get("teacher_id", entry["guru_id"]),
    }


def _validate_text_hash(span: dict) -> str:
    """Compute and verify source_text_hash from span_text."""
    text = span.get("span_text", "")
    if not text or not isinstance(text, str):
        raise ValidationError(
            "MISSING_SPAN_TEXT", "span_text is required and must be non-empty string"
        )
    if _is_graceful_degradation(text):
        raise ValidationError(
            "GRACEFUL_DEGRADATION_TEXT",
            "span_text contains a provider graceful-degradation string (L-INGEST-2)",
        )
    computed = hashlib.sha256(text.encode("utf-8")).hexdigest()
    declared = span.get("source_text_hash")
    if declared and declared != computed:
        raise ValidationError(
            "HASH_MISMATCH",
            f"source_text_hash mismatch: declared={declared!r}, computed={computed!r}",
        )
    return computed


def _validate_span(
    span: dict,
    asr_lookup: dict,
    rights_lookup: dict,
    speaker_lookup: dict,
    seen_span_ids: set[str],
) -> dict:
    """Full validation pipeline for one source span. Returns enriched record."""
    # Required identity fields
    span_id = _require_str(span.get("source_span_id", ""), "source_span_id")
    asset_id = _require_str(span.get("source_asset_id", ""), "source_asset_id")
    video_id = _require_str(span.get("video_id", ""), "video_id")
    corpus_version = _require_str(span.get("corpus_version", ""), "corpus_version")
    parent_unit_id = span.get("parent_unit_id", "")  # may be derived

    # Duplicate check
    if span_id in seen_span_ids:
        raise ValidationError("DUPLICATE_SPAN_ID", f"Duplicate source_span_id={span_id!r}")
    seen_span_ids.add(span_id)

    # Text hash
    text_hash = _validate_text_hash(span)

    # Speaker verification gate
    speaker_fields = _validate_speaker(span, speaker_lookup)

    # Rights gate
    _validate_rights(span, rights_lookup)

    # ASR evidence gate
    asr_fields = _validate_asr_evidence(span, asr_lookup)

    # Structural fields
    turn_id = span.get("turn_id") or f"turn_{video_id}_{asr_fields['audio_start_ms']}"
    turn_index = span.get("turn_index")
    if turn_index is None:
        turn_index = 0  # will be sequenced by caller

    completeness_status = span.get("completeness_status", "uncertain")
    if completeness_status not in ("complete", "fragment", "uncertain"):
        raise ValidationError(
            "INVALID_COMPLETENESS_STATUS",
            f"completeness_status={completeness_status!r} not in allowed values",
        )

    # Build valid record
    guru_id = speaker_fields["guru_id"]
    record = {
        "source_span_id": span_id,
        "source_asset_id": asset_id,
        "video_id": video_id,
        "corpus_version": corpus_version,
        "parent_unit_id": parent_unit_id or _make_uuid5(f"parent::{guru_id}::{video_id}"),
        "source_text_hash": text_hash,
        "turn_id": turn_id,
        "turn_index": turn_index,
        "completeness_status": completeness_status,
        **speaker_fields,
        **asr_fields,
        "span_text": span.get("span_text"),  # included for build only; not served
        "_point_id": _make_uuid5(span_id),
    }
    return record


# ---------------------------------------------------------------------------
# Manifest loaders
# ---------------------------------------------------------------------------


def _load_json_manifest(path: Path, name: str) -> dict:
    if not path.exists():
        print(f"ERROR: {name} not found at {path}", file=sys.stderr)
        sys.exit(2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, (dict, list)):
            raise ValueError("top-level must be dict or list")
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {name} is malformed: {exc}", file=sys.stderr)
        sys.exit(2)


def _load_jsonl(path: Path, name: str) -> list[dict]:
    if not path.exists():
        print(f"ERROR: {name} not found at {path}", file=sys.stderr)
        sys.exit(2)
    records = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"ERROR: {name} line {i} is malformed JSON: {exc}", file=sys.stderr)
                sys.exit(2)
    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--asr-manifest", required=True, type=Path, help="ASR manifest JSON keyed by source_span_id"
    )
    parser.add_argument(
        "--rights-manifest",
        required=True,
        type=Path,
        help="Rights manifest JSON keyed by source_asset_id",
    )
    parser.add_argument(
        "--speaker-manifest",
        required=True,
        type=Path,
        help="Speaker review JSON keyed by source_span_id",
    )
    parser.add_argument("--source-spans", required=True, type=Path, help="Source span JSONL input")
    parser.add_argument(
        "--candidate-out", required=True, type=Path, help="Valid candidate JSONL output path"
    )
    parser.add_argument(
        "--quarantine-out", required=True, type=Path, help="Quarantine JSONL output path"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="(Always true; this tool never writes to Qdrant)",
    )
    args = parser.parse_args()

    # Load manifests
    asr_raw = _load_json_manifest(args.asr_manifest, "asr-manifest")
    asr_lookup: dict = (
        asr_raw if isinstance(asr_raw, dict) else {r["source_span_id"]: r for r in asr_raw}
    )

    rights_raw = _load_json_manifest(args.rights_manifest, "rights-manifest")
    rights_lookup: dict = (
        rights_raw
        if isinstance(rights_raw, dict)
        else {r["source_asset_id"]: r for r in rights_raw}
    )

    speaker_raw = _load_json_manifest(args.speaker_manifest, "speaker-manifest")
    speaker_lookup: dict = (
        speaker_raw
        if isinstance(speaker_raw, dict)
        else {r["source_span_id"]: r for r in speaker_raw}
    )

    spans = _load_jsonl(args.source_spans, "source-spans")
    if not spans:
        print("ERROR: source-spans JSONL has zero records.", file=sys.stderr)
        sys.exit(2)

    # Validate each span
    candidate_records: list[dict] = []
    quarantine_records: list[dict] = []
    seen_span_ids: set[str] = set()

    for span in spans:
        try:
            record = _validate_span(span, asr_lookup, rights_lookup, speaker_lookup, seen_span_ids)
            candidate_records.append(record)
        except ValidationError as exc:
            quarantine_records.append(
                {
                    "source_span_id": span.get("source_span_id"),
                    "video_id": span.get("video_id"),
                    "teacher_id": span.get("teacher_id"),
                    "reason_code": exc.code,
                    "reason_detail": exc.detail,
                }
            )

    # Write outputs
    args.candidate_out.parent.mkdir(parents=True, exist_ok=True)
    args.quarantine_out.parent.mkdir(parents=True, exist_ok=True)

    with args.candidate_out.open("w", encoding="utf-8") as f:
        for r in candidate_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with args.quarantine_out.open("w", encoding="utf-8") as f:
        for r in quarantine_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Per-guru/video counts
    by_guru: dict[str, int] = {}
    by_video: dict[str, int] = {}
    for r in candidate_records:
        g = r.get("guru_id", "UNKNOWN")
        v = r.get("video_id", "UNKNOWN")
        by_guru[g] = by_guru.get(g, 0) + 1
        by_video[v] = by_video.get(v, 0) + 1

    # Quarantine reason summary
    reason_counts: dict[str, int] = {}
    for r in quarantine_records:
        code = r["reason_code"]
        reason_counts[code] = reason_counts.get(code, 0) + 1

    # Report
    print("=" * 60)
    print("VALIDATE FP CONTEXT CANDIDATE — DRY-RUN REPORT")
    print("=" * 60)
    print(f"Input spans:       {len(spans)}")
    print(f"Valid candidates:  {len(candidate_records)}")
    print(f"Quarantined:       {len(quarantine_records)}")
    print()
    print("Candidate counts by guru_id:")
    for g, cnt in sorted(by_guru.items()):
        print(f"  {g}: {cnt}")
    print()
    print("Quarantine reason codes:")
    for code, cnt in sorted(reason_counts.items()):
        print(f"  {code}: {cnt}")
    print()
    print(f"Candidate JSONL:   {args.candidate_out}")
    print(f"Quarantine JSONL:  {args.quarantine_out}")
    print()
    print("NOTE: This tool makes NO Qdrant connections. Output JSONL requires")
    print("      separate owner approval and a distinct write-command execution.")
    print("=" * 60)

    if not candidate_records:
        print(
            "ERROR: zero valid candidate records produced. Review quarantine output.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
