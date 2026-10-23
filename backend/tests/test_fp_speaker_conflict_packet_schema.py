"""Packet-schema tests for the speaker-conflict review package (schema v2).

The v1 packet wrote the **slice** width into a field named ``audio_duration_ms``
— the same name the Phase-2 verdict uses for the duration of the **complete
WAV file**. The two quantities are different and differ by orders of
magnitude, so a human reviewer reading the v1 packet would reasonably believe
the window sat near the end of the recording.

These tests pin the corrected schema: the file duration and the slice duration
must never be confused, the misleading field must be gone, and the bounds of
every window must be checked against the complete file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import build_fp_speaker_conflict_review as conflicts  # noqa: E402


def _candidate(span_id: str, *, start: int = 172540, end: int = 183020) -> dict:
    return {
        "source_span_id": span_id,
        "video_id": "vid-a",
        "source_asset_id": "vid-a",
        "guru_id": "krishnaji",
        "reconstructed_text": "and it was the most incredible experience",
        "source_text_hash": "h" * 64,
        "transcript_hash": "t" * 64,
        "audio_start_ms": start,
        "audio_end_ms": end,
        "word_start": 311,
        "word_end": 338,
        "corpus_version": "fp-context-transcript-v2",
        "normalization_version": "fp-norm-unicode-v1",
    }


def _verdict(span_id: str, *, file_duration: int | None, slice_duration: int | None) -> dict:
    row = {
        "source_span_id": span_id,
        "reason_code": "refused_guru_mismatch",
        "expected_guru": "preethaji",
        "predicted_guru": "krishnaji",
        "cosine": -0.02,
        "runner_up_cosine": -0.17,
        "margin": 0.15,
        "cosine_floor": 0.28,
        "margin_threshold": 1e-06,
        "audio_start_ms": 172540,
        "audio_end_ms": 183020,
        "audio_path": "/audio/vid-a.wav",
        "audio_sha256": "a" * 64,
        "audio_sample_rate": 16000,
        "speaker_model": "speechbrain/spkrec-ecapa-voxceleb",
        "speaker_model_revision": "m" * 40,
        "calibration_revision": "c" * 64,
        "run_id": "r" * 64,
        "split": "train",
        "transcript_hash": "t" * 64,
        "source_text_hash": "h" * 64,
    }
    if file_duration is not None:
        row["audio_duration_ms"] = file_duration
    if slice_duration is not None:
        row["audio_slice_duration_ms"] = slice_duration
    return row


def test_the_file_duration_and_the_slice_duration_are_not_confused():
    """The exact numbers from the owner brief must stay distinct."""
    candidates = [_candidate("span-1")]
    verdicts = {"span-1": _verdict("span-1", file_duration=214692, slice_duration=10480)}
    rows = conflicts.build_conflicts(verdicts, candidates)
    assert len(rows) == 1
    row = rows[0]
    assert row["audio_slice_duration_ms"] == 10480
    assert row["audio_file_duration_ms"] == 214692
    assert row["audio_slice_duration_ms"] != row["audio_file_duration_ms"]
    assert row["audio_start_ms"] == 172540
    assert row["audio_end_ms"] == 183020


def test_the_misleading_field_is_gone_from_the_v2_schema():
    candidates = [_candidate("span-1")]
    verdicts = {"span-1": _verdict("span-1", file_duration=214692, slice_duration=10480)}
    row = conflicts.build_conflicts(verdicts, candidates)[0]
    assert "audio_duration_ms" not in row
    assert row["schema"] == "first-person-speaker-conflict-v2"
    assert conflicts.SUPERSEDED_SCHEMA == "first-person-speaker-conflict-v1"
    assert conflicts.MISLEADING_FIELD == "audio_duration_ms"


def test_a_missing_file_duration_is_reported_as_missing_not_as_a_slice():
    candidates = [_candidate("span-1")]
    verdicts = {"span-1": _verdict("span-1", file_duration=None, slice_duration=None)}
    row = conflicts.build_conflicts(verdicts, candidates)[0]
    assert row["audio_file_duration_ms"] is None
    assert row["audio_file_duration_available"] is False
    assert row["audio_file_duration_source"] == "unavailable_in_phase2_verdict"
    # The slice duration is still exact and still the slice.
    assert row["audio_slice_duration_ms"] == 183020 - 172540


def test_a_verdict_whose_slice_duration_disagrees_with_the_window_fails_closed():
    candidates = [_candidate("span-1")]
    verdicts = {"span-1": _verdict("span-1", file_duration=214692, slice_duration=999)}
    with pytest.raises(conflicts.SpeakerConflictError):
        conflicts.build_conflicts(verdicts, candidates)


def test_the_bounds_check_proves_every_window_sits_inside_the_complete_file():
    candidates = [_candidate("span-1"), _candidate("span-2", start=0, end=9000)]
    verdicts = {
        "span-1": _verdict("span-1", file_duration=214692, slice_duration=10480),
        "span-2": _verdict("span-2", file_duration=120000, slice_duration=9000),
    }
    rows = conflicts.build_conflicts(verdicts, candidates)
    report = conflicts.bounds_report(rows)
    assert report["bounds_checked_rows"] == 2
    assert report["out_of_bounds_count"] == 0
    assert report["all_checked_windows_within_file"] is True


def test_a_window_past_the_end_of_the_file_is_reported_as_out_of_bounds():
    candidates = [_candidate("span-1", start=0, end=300000)]
    verdicts = {"span-1": _verdict("span-1", file_duration=214692, slice_duration=300000)}
    rows = conflicts.build_conflicts(verdicts, candidates)
    report = conflicts.bounds_report(rows)
    assert report["out_of_bounds_count"] == 1
    assert report["all_checked_windows_within_file"] is False


def test_a_row_without_a_file_duration_is_never_counted_as_in_bounds():
    candidates = [_candidate("span-1")]
    verdicts = {"span-1": _verdict("span-1", file_duration=None, slice_duration=10480)}
    rows = conflicts.build_conflicts(verdicts, candidates)
    report = conflicts.bounds_report(rows)
    assert report["bounds_checked_rows"] == 0
    assert report["bounds_unchecked_rows"] == 1
    assert report["out_of_bounds_count"] == 0


def test_the_review_packet_states_the_correction_and_shows_both_durations(tmp_path):
    """The human reviewer must see the correction, not just the new fields."""
    candidates = [_candidate("span-1")]
    verdicts = {"span-1": _verdict("span-1", file_duration=214692, slice_duration=10480)}
    rows = conflicts.build_conflicts(verdicts, candidates)
    bounds = conflicts.bounds_report(rows)
    meta = {
        "speaker_model": "speechbrain/spkrec-ecapa-voxceleb",
        "speaker_model_revision": "m" * 40,
        "calibration_revision": "c" * 64,
        "run_id": "r" * 64,
    }
    text = conflicts.render_review(rows, meta, bounds)
    assert "misleading" in text.lower()
    assert "first-person-speaker-conflict-v1" in text
    assert "first-person-speaker-conflict-v2" in text
    assert "audio_file_duration_ms" in text
    assert "audio_slice_duration_ms" in text
    assert "10480" in text
    assert "214692" in text
