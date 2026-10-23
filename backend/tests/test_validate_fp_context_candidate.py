"""Tests for validate_fp_context_candidate.py — Phase 4 dry-run validator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops.validate_fp_context_candidate import (
    ValidationError,
    _validate_span,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_span():
    return {
        "source_span_id": "span_001",
        "source_asset_id": "asset_video_123",
        "video_id": "video_123",
        "corpus_version": "v1.0",
        "span_text": "Meditation brings clarity to the restless mind.",
        "completeness_status": "complete",
    }


@pytest.fixture
def asr_manifest():
    return {
        "span_001": {
            "audio_start_ms": 1000,
            "audio_end_ms": 5000,
            "asr_engine": "whisper_large_v3",
            "asr_model_version": "v3-turbo",
            "caption_status": "verified",
            "boundary_status": "verified",
        }
    }


@pytest.fixture
def rights_manifest():
    return {
        "asset_video_123": {
            "rights_cleared": True,
            "license": "authorized_educational",
            "reviewer": "legal_steward",
        }
    }


@pytest.fixture
def speaker_manifest():
    return {
        "span_001": {
            "speaker_verified": True,
            "speaker_id": "krishnaji",
            "speaker_role": "guru",
            "guru_id": "krishnaji",
            "teacher_id": "krishnaji",
        }
    }


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_valid_span_passes(valid_span, asr_manifest, rights_manifest, speaker_manifest):
    seen = set()
    rec = _validate_span(valid_span, asr_manifest, rights_manifest, speaker_manifest, seen)
    assert rec["source_span_id"] == "span_001"
    assert rec["speaker_verified"] is True
    assert rec["speaker_role"] == "guru"
    assert rec["guru_id"] == "krishnaji"
    assert rec["audio_start_ms"] == 1000
    assert rec["audio_end_ms"] == 5000
    assert rec["asr_engine"] == "whisper_large_v3"
    assert len(rec["source_text_hash"]) == 64
    assert "_point_id" in rec
    assert "span_001" in seen


def test_missing_asr_quarantines(valid_span, rights_manifest, speaker_manifest):
    seen = set()
    with pytest.raises(ValidationError) as exc:
        _validate_span(valid_span, {}, rights_manifest, speaker_manifest, seen)
    assert exc.value.code == "MISSING_ASR"


def test_boundary_inversion_quarantines(valid_span, rights_manifest, speaker_manifest):
    asr = {
        "span_001": {
            "audio_start_ms": 5000,
            "audio_end_ms": 1000,  # end < start
            "asr_engine": "whisper",
            "asr_model_version": "v3",
        }
    }
    seen = set()
    with pytest.raises(ValidationError) as exc:
        _validate_span(valid_span, asr, rights_manifest, speaker_manifest, seen)
    assert exc.value.code == "BOUNDARY_INVERSION"


def test_rights_not_cleared_quarantines(valid_span, asr_manifest, speaker_manifest):
    rights = {"asset_video_123": {"rights_cleared": False}}
    seen = set()
    with pytest.raises(ValidationError) as exc:
        _validate_span(valid_span, asr_manifest, rights, speaker_manifest, seen)
    assert exc.value.code == "RIGHTS_NOT_CLEARED"


def test_missing_rights_entry_quarantines(valid_span, asr_manifest, speaker_manifest):
    seen = set()
    with pytest.raises(ValidationError) as exc:
        _validate_span(valid_span, asr_manifest, {}, speaker_manifest, seen)
    assert exc.value.code == "NO_RIGHTS_ENTRY"


def test_speaker_not_verified_quarantines(valid_span, asr_manifest, rights_manifest):
    speaker = {
        "span_001": {
            "speaker_verified": False,
            "speaker_id": "krishnaji",
            "speaker_role": "guru",
            "guru_id": "krishnaji",
        }
    }
    seen = set()
    with pytest.raises(ValidationError) as exc:
        _validate_span(valid_span, asr_manifest, rights_manifest, speaker, seen)
    assert exc.value.code == "SPEAKER_NOT_VERIFIED"


def test_missing_speaker_entry_quarantines(valid_span, asr_manifest, rights_manifest):
    seen = set()
    with pytest.raises(ValidationError) as exc:
        _validate_span(valid_span, asr_manifest, rights_manifest, {}, seen)
    assert exc.value.code == "MISSING_SPEAKER_REVIEW"


def test_speaker_not_guru_role_quarantines(valid_span, asr_manifest, rights_manifest):
    speaker = {
        "span_001": {
            "speaker_verified": True,
            "speaker_id": "interviewer",
            "speaker_role": "host",  # host dialogue must not enter guru candidate
            "guru_id": "krishnaji",
        }
    }
    seen = set()
    with pytest.raises(ValidationError) as exc:
        _validate_span(valid_span, asr_manifest, rights_manifest, speaker, seen)
    assert exc.value.code == "SPEAKER_NOT_GURU"


def test_graceful_degradation_detected_and_quarantined(
    valid_span, asr_manifest, rights_manifest, speaker_manifest
):
    valid_span["span_text"] = (
        "I'm currently experiencing a temporary connection issue. Please try again later."
    )
    seen = set()
    with pytest.raises(ValidationError) as exc:
        _validate_span(valid_span, asr_manifest, rights_manifest, speaker_manifest, seen)
    assert exc.value.code == "GRACEFUL_DEGRADATION_TEXT"


def test_text_hash_mismatch_quarantines(
    valid_span, asr_manifest, rights_manifest, speaker_manifest
):
    valid_span["source_text_hash"] = "0" * 64  # deliberate bogus hash
    seen = set()
    with pytest.raises(ValidationError) as exc:
        _validate_span(valid_span, asr_manifest, rights_manifest, speaker_manifest, seen)
    assert exc.value.code == "HASH_MISMATCH"


def test_duplicate_span_id_quarantines(valid_span, asr_manifest, rights_manifest, speaker_manifest):
    seen = {"span_001"}
    with pytest.raises(ValidationError) as exc:
        _validate_span(valid_span, asr_manifest, rights_manifest, speaker_manifest, seen)
    assert exc.value.code == "DUPLICATE_SPAN_ID"


# ---------------------------------------------------------------------------
# CLI integration test
# ---------------------------------------------------------------------------


def test_cli_execution_with_mixed_input(tmp_path):
    asr_path = tmp_path / "asr.json"
    rights_path = tmp_path / "rights.json"
    speaker_path = tmp_path / "speaker.json"
    spans_path = tmp_path / "spans.jsonl"
    cand_path = tmp_path / "candidates.jsonl"
    quar_path = tmp_path / "quarantine.jsonl"

    asr_path.write_text(
        json.dumps(
            {
                "s1": {
                    "audio_start_ms": 0,
                    "audio_end_ms": 2000,
                    "asr_engine": "whisper",
                    "asr_model_version": "v3",
                },
                "s2": {
                    "audio_start_ms": 3000,
                    "audio_end_ms": 1000,
                    "asr_engine": "whisper",
                    "asr_model_version": "v3",
                },  # inverted
            }
        )
    )
    rights_path.write_text(
        json.dumps(
            {
                "a1": {"rights_cleared": True},
                "a2": {"rights_cleared": True},
            }
        )
    )
    speaker_path.write_text(
        json.dumps(
            {
                "s1": {
                    "speaker_verified": True,
                    "speaker_id": "preethaji",
                    "speaker_role": "guru",
                    "guru_id": "preethaji",
                },
                "s2": {
                    "speaker_verified": True,
                    "speaker_id": "preethaji",
                    "speaker_role": "guru",
                    "guru_id": "preethaji",
                },
            }
        )
    )
    spans = [
        {
            "source_span_id": "s1",
            "source_asset_id": "a1",
            "video_id": "v1",
            "corpus_version": "v1",
            "span_text": "Truth one.",
        },
        {
            "source_span_id": "s2",
            "source_asset_id": "a2",
            "video_id": "v2",
            "corpus_version": "v1",
            "span_text": "Truth two.",
        },
    ]
    spans_path.write_text("\n".join(json.dumps(s) for s in spans) + "\n")

    cmd = [
        sys.executable,
        str(
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "ops"
            / "validate_fp_context_candidate.py"
        ),
        "--asr-manifest",
        str(asr_path),
        "--rights-manifest",
        str(rights_path),
        "--speaker-manifest",
        str(speaker_path),
        "--source-spans",
        str(spans_path),
        "--candidate-out",
        str(cand_path),
        "--quarantine-out",
        str(quar_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

    cands = [json.loads(line) for line in cand_path.read_text().strip().split("\n")]
    quars = [json.loads(line) for line in quar_path.read_text().strip().split("\n")]

    assert len(cands) == 1
    assert cands[0]["source_span_id"] == "s1"
    assert len(quars) == 1
    assert quars[0]["source_span_id"] == "s2"
    assert quars[0]["reason_code"] == "BOUNDARY_INVERSION"
