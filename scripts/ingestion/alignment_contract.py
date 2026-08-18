"""Deterministic contract for canonical transcript alignment evidence."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

ALLOWED_ALIGNMENT_METHODS = {
    "forced_phoneme_alignment",
    "word_level_alignment",
    "human_audio_review",
    "source_caption_alignment",
}


def segment_rows(payload: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get("segments", [])
    else:
        rows = payload
    return rows if isinstance(rows, list) else []


def validate_alignment_evidence(quality: Dict[str, Any], segments_payload: Any, trusted: bool) -> List[str]:
    errors: List[str] = []
    previous_end = None
    rows = list(segment_rows(segments_payload))
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append("segment_not_object:%d" % index)
            continue
        start, end = row.get("start"), row.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            errors.append("segment_time_missing:%d" % index)
            continue
        if start < 0 or end <= start:
            errors.append("segment_time_invalid:%d" % index)
        if previous_end is not None and start < previous_end:
            errors.append("segment_overlap:%d" % index)
        previous_end = end
    coverage = quality.get("speech_interval_coverage_ratio")
    if coverage is not None and (not isinstance(coverage, (int, float)) or not 0 <= coverage <= 1):
        errors.append("coverage_ratio_out_of_range")
    if trusted:
        method = quality.get("alignment_method")
        if method not in ALLOWED_ALIGNMENT_METHODS:
            errors.append("trusted_alignment_method_missing_or_unknown")
        if not isinstance(quality.get("alignment_evidence_sha256"), str) or len(quality.get("alignment_evidence_sha256", "")) != 64:
            errors.append("trusted_alignment_evidence_digest_missing_or_invalid")
    return errors
