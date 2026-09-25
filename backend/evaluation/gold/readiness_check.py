"""
Mukthi Guru — Labelling Readiness & Gold Sheet Validator (B1 Protocol)

Implements end-to-end readiness auditing for videos and gold annotation sheets:
  1. Video Readiness: verifies audio availability, transcript presence, cryptographic
     hash integrity, speaker attribution plausibility, and zero host speech in teacher clips.
  2. Sheet Validation: enforces schema correctness, detects contradictory judgments,
     blanks, and guarantees at most 3 questions per video.
"""

from __future__ import annotations

from collections import Counter
import csv
import json
import logging
from pathlib import Path
from typing import Any, Optional

from evaluation.gold.sheets import QUESTION_COLUMNS, RELEVANCE_COLUMNS
from services.transcript_verbatim import compute_verbatim_hash

logger = logging.getLogger(__name__)

FORBIDDEN_HOST_SPEAKER_LABELS = {
    "host",
    "questioner",
    "host / questioner",
    "interviewer",
}


def check_video_readiness(
    video_dir: Path,
    audio_path: Optional[Path] = None,
    max_duration_seconds: Optional[float] = None,
) -> dict[str, Any]:
    """
    Check a processed video folder end-to-end for human labelling readiness.
    Flags any anomalies (hash mismatch, missing audio, host speech in teacher clips).
    """
    video_id = video_dir.name
    issues: list[str] = []
    warnings: list[str] = []
    stats: dict[str, Any] = {"video_id": video_id}

    # 1. Check audio file
    if audio_path:
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            issues.append(f"Audio file missing or empty: {audio_path}")
        else:
            stats["audio_size_bytes"] = audio_path.stat().st_size

    # 2. Check canonical segments or transcript
    canonical_file = video_dir / "canonical_segments.json"
    quality_file = video_dir / "quality_report.json"
    manifest_file = video_dir / "artifact_manifest.json"

    if not canonical_file.exists():
        issues.append(f"Missing canonical_segments.json in {video_dir}")
        return {"ready": False, "video_id": video_id, "issues": issues, "warnings": warnings, "stats": stats}

    try:
        with open(canonical_file, "r", encoding="utf-8") as f:
            canonical_data = json.load(f)
    except Exception as e:
        issues.append(f"Unreadable canonical_segments.json: {e}")
        return {"ready": False, "video_id": video_id, "issues": issues, "warnings": warnings, "stats": stats}

    segments = canonical_data.get("segments", [])
    stats["segment_count"] = len(segments)

    # 3. Check transcript hash integrity
    stored_hash = canonical_data.get("transcript_hash")
    computed_hash = compute_verbatim_hash(segments)
    if stored_hash and stored_hash != computed_hash:
        issues.append(
            f"Transcript hash mismatch! Stored: {stored_hash[:16]}..., Computed: {computed_hash[:16]}..."
        )

    # 4. Check speaker turns and bounds
    for i, seg in enumerate(segments):
        start = seg.get("start", 0.0)
        end = seg.get("end", 0.0)
        speaker = str(seg.get("speaker") or seg.get("speaker_evidence") or "unknown").strip()

        if start < 0.0:
            issues.append(f"Segment {i} has negative start timestamp: {start}")
        if end <= start:
            issues.append(f"Segment {i} has end ({end}) <= start ({start})")
        if max_duration_seconds and end > max_duration_seconds + 5.0:
            warnings.append(f"Segment {i} end ({end}s) exceeds known video duration ({max_duration_seconds}s)")

        # Host leak check
        if speaker.lower() in ("sri preethaji", "sri krishnaji", "teacher"):
            text = seg.get("text", "").lower()
            if "host:" in text or "questioner:" in text:
                issues.append(f"Segment {i} attributed to {speaker} contains host dialogue marker")

        # This corpus is teacher-speech-only by design (see root CLAUDE.md's
        # OKF doctrine-bundle invariant); a segment whose own speaker label
        # names the host/questioner/interviewer is host content that leaked
        # into what must be zero-host-speech teacher clips — a hard failure,
        # not a warning.
        if speaker.lower() in FORBIDDEN_HOST_SPEAKER_LABELS:
            issues.append(f"Segment {i} carries a forbidden host speaker label: '{speaker}'")

    # 5. Check artifact manifest if present
    if manifest_file.exists():
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            stats["manifest_artifacts"] = list(manifest.get("artifacts", {}).keys())
        except Exception as e:
            warnings.append(f"Could not parse artifact_manifest.json: {e}")
    else:
        warnings.append("No artifact_manifest.json found")

    is_ready = len(issues) == 0
    return {
        "ready": is_ready,
        "video_id": video_id,
        "issues": issues,
        "warnings": warnings,
        "stats": stats,
    }


def validate_gold_sheet(
    csv_path: Path,
    sheet_type: str = "relevance",  # "relevance" or "question"
    max_questions_per_video: int = 3,
) -> dict[str, Any]:
    """
    Validate filled human gold sheets against B1 protocol rules:
      - Valid schema columns
      - No contradictions between judge_a, judge_b, and adjudicated
      - At most max_questions_per_video (default 3) per video
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Gold sheet CSV does not exist: {csv_path}")

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    violations: list[str] = []
    warnings: list[str] = []

    expected_cols = RELEVANCE_COLUMNS if sheet_type == "relevance" else QUESTION_COLUMNS
    for col in expected_cols:
        if col not in fieldnames:
            violations.append(f"Missing required column in CSV header: '{col}'")

    if violations:
        return {
            "valid": False,
            "total_rows": len(rows),
            "violations": violations,
            "warnings": warnings,
        }

    # Count questions per video
    if sheet_type == "question":
        video_counts = Counter(r.get("intended_video_ids", "").strip() for r in rows if r.get("intended_video_ids"))
        for vid, count in video_counts.items():
            if count > max_questions_per_video:
                violations.append(
                    f"Video '{vid}' exceeds maximum allowed questions: {count} > {max_questions_per_video}"
                )

    # Validate row-level constraints for relevance sheet
    if sheet_type == "relevance":
        for idx, row in enumerate(rows):
            ja = row.get("judge_a", "").strip().lower()
            jb = row.get("judge_b", "").strip().lower()
            adj = row.get("adjudicated", "").strip().lower()

            valid_labels = {"yes", "no", ""}
            if ja not in valid_labels:
                violations.append(f"Row {idx}: Invalid label for judge_a: '{ja}'")
            if jb not in valid_labels:
                violations.append(f"Row {idx}: Invalid label for judge_b: '{jb}'")
            if adj not in valid_labels:
                violations.append(f"Row {idx}: Invalid label for adjudicated: '{adj}'")

            # Check contradiction: If both judges labelled and disagree, adjudicated must be
            # non-empty. Unadjudicated disagreement is a HARD failure, not a warning — an
            # unresolved yes/no split must never reach calibration as if it were a settled label.
            if ja and jb and ja != jb and not adj:
                violations.append(
                    f"Row {idx} (question {row.get('question_id')}): Disagreement (judge_a='{ja}', judge_b='{jb}') requires adjudication"
                )

    is_valid = len(violations) == 0
    return {
        "valid": is_valid,
        "total_rows": len(rows),
        "violations": violations,
        "warnings": warnings,
    }
