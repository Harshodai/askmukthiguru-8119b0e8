"""Focused tests for ``scripts.ops.regenerate_v10_span_ecapa_verdicts``.

Phase 2 regenerates per-span ECAPA speaker evidence for the 1,600
exact-reconstruction spans of the Phase 3 candidate. These tests pin:

* that the exact Phase 3 candidate is loaded completely and exactly once per
  span, and that every quarantined span is excluded;
* that audio is read from the archived WAV only, and that a missing file, a
  header-only stub, an invalid WAV, an out-of-bounds window and a too-short
  slice each fail closed with their own reason code;
* that the verdict is a pure function of the recorded score and the recorded
  thresholds, including at the exact threshold boundary;
* that the calibration fails closed when there is no measurable held-out
  impostor set;
* that the output is deterministic, keyed by ``source_span_id``, schema
  validated, and that the script has no write path at all.

The heavy audio stack (torch / speechbrain / scikit-learn) is **not** needed:
it is imported lazily inside the functions that use it, so this module runs in
the locked release image as well.
"""

from __future__ import annotations

import ast
import json
import struct
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

_HERE = Path(__file__).resolve()
if _HERE.parents[1].name == "app" or _HERE.parents[1] == Path("/app"):
    _BACKEND = Path("/app")
else:
    _BACKEND = _HERE.parents[1]
_REPO_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import regenerate_v10_span_ecapa_verdicts as phase2  # noqa: E402

SCRIPT_PATH = _BACKEND / "scripts" / "ops" / "regenerate_v10_span_ecapa_verdicts.py"

EVIDENCE = _REPO_ROOT / "audits" / "evidence"
CANDIDATE = EVIDENCE / "public_release_phase3_candidate_2026-10-21.jsonl"
QUARANTINE = EVIDENCE / "public_release_phase3_quarantine_2026-10-21.jsonl"

#: Recorded Phase 3 facts.
EXPECTED_SPANS = 1600
EXPECTED_QUARANTINE_ROWS = 1137
EXPECTED_QUARANTINE_VARIANTS = 1127
EXPECTED_QUARANTINE_UNLOCATABLE = 10


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _write_wav(path: Path, duration_ms: int, sample_rate: int = 16000) -> Path:
    """Write a real, complete PCM WAV so the slice reader has real audio."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int((duration_ms / 1000.0) * sample_rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(struct.pack("<h", (index % 1000) - 500) for index in range(frames)))
    return path


def _write_stub_wav(path: Path, duration_ms: int) -> Path:
    """Write a header-only WAV stub: a correct declared duration, no PCM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 16000
    frames = int((duration_ms / 1000.0) * sample_rate)
    data_bytes = frames * 2
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + data_bytes)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", data_bytes)
    )
    path.write_bytes(header)
    return path


def _candidate_row(span_id: str = "a" * 64, **overrides) -> dict:
    row = {
        "source_span_id": span_id,
        "video_id": "vid0001",
        "guru_id": "krishnaji",
        "source_text_hash": "b" * 64,
        "transcript_hash": "c" * 64,
        "timed_transcript_sha256": "c" * 64,
        "audio_start_ms": 1000,
        "audio_end_ms": 4000,
    }
    row.update(overrides)
    return row


def _write_candidate(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


# ---------------------------------------------------------------------------
# Exact candidate loading
# ---------------------------------------------------------------------------
def test_load_candidate_reads_every_span_once(tmp_path):
    rows = [_candidate_row(f"{index:064x}") for index in range(3)]
    path = _write_candidate(tmp_path / "candidate.jsonl", rows)
    loaded = phase2.load_candidate(path, expected_spans=3)
    assert [row["source_span_id"] for row in loaded] == [row["source_span_id"] for row in rows]


def test_load_candidate_rejects_a_wrong_span_count(tmp_path):
    path = _write_candidate(tmp_path / "candidate.jsonl", [_candidate_row()])
    with pytest.raises(phase2.InputError):
        phase2.load_candidate(path, expected_spans=EXPECTED_SPANS)


def test_load_candidate_rejects_duplicate_source_span_ids(tmp_path):
    rows = [_candidate_row("d" * 64), _candidate_row("d" * 64)]
    path = _write_candidate(tmp_path / "candidate.jsonl", rows)
    with pytest.raises(phase2.InputError) as excinfo:
        phase2.load_candidate(path, expected_spans=2)
    assert "duplicate source_span_id" in str(excinfo.value)


def test_load_candidate_rejects_a_missing_span_id(tmp_path):
    path = _write_candidate(tmp_path / "candidate.jsonl", [_candidate_row("")])
    with pytest.raises(phase2.InputError):
        phase2.load_candidate(path, expected_spans=1)


def test_load_candidate_rejects_a_display_label_as_expected_guru(tmp_path):
    path = _write_candidate(
        tmp_path / "candidate.jsonl", [_candidate_row(guru_id="Sri Krishnaji")]
    )
    with pytest.raises(phase2.InputError):
        phase2.load_candidate(path, expected_spans=1)


def test_load_candidate_rejects_an_inverted_audio_window(tmp_path):
    path = _write_candidate(
        tmp_path / "candidate.jsonl",
        [_candidate_row(audio_start_ms=4000, audio_end_ms=1000)],
    )
    with pytest.raises(phase2.InputError):
        phase2.load_candidate(path, expected_spans=1)


def test_load_candidate_rejects_a_non_integer_coordinate(tmp_path):
    path = _write_candidate(
        tmp_path / "candidate.jsonl", [_candidate_row(audio_start_ms="1000")]
    )
    with pytest.raises(phase2.InputError):
        phase2.load_candidate(path, expected_spans=1)


def test_real_phase3_candidate_has_exactly_1600_unique_spans():
    if not CANDIDATE.is_file():
        pytest.skip("Phase 3 candidate artifact is not present")
    rows = phase2.load_candidate(CANDIDATE, expected_spans=EXPECTED_SPANS)
    assert len(rows) == EXPECTED_SPANS
    assert len({row["source_span_id"] for row in rows}) == EXPECTED_SPANS


def test_real_phase3_quarantine_is_excluded_completely():
    if not (CANDIDATE.is_file() and QUARANTINE.is_file()):
        pytest.skip("Phase 3 artifacts are not present")
    candidate = phase2.load_candidate(CANDIDATE, expected_spans=EXPECTED_SPANS)
    rows, quarantine_ids, without_id = phase2.load_quarantine(
        QUARANTINE, expected_rows=EXPECTED_QUARANTINE_ROWS
    )
    candidate_ids = {row["source_span_id"] for row in candidate}
    assert candidate_ids & quarantine_ids == set()
    # 1,137 quarantined rows: 10 never got a rebuilt span id (they were not
    # locatable in the timed artifact) and two of the remaining rows share one
    # rebuilt id (two live children with identical word coordinates).
    assert without_id == EXPECTED_QUARANTINE_UNLOCATABLE
    assert len(rows) == EXPECTED_QUARANTINE_ROWS
    assert len(quarantine_ids) == EXPECTED_QUARANTINE_VARIANTS - 1


# ---------------------------------------------------------------------------
# Audio reading
# ---------------------------------------------------------------------------
def test_missing_audio_is_reported_as_missing_audio(tmp_path):
    audio, reason = phase2.read_slice(tmp_path / "nope.wav", 0, 1000)
    assert audio is None
    assert reason == phase2.VERDICT_MISSING_AUDIO


def test_header_only_stub_audio_is_rejected(tmp_path):
    stub = _write_stub_wav(tmp_path / "stub.wav", 5000)
    header = phase2.wav_header(stub)
    assert header is not None
    assert header["audio_complete"] is False
    audio, reason = phase2.read_slice(stub, 0, 1000)
    assert audio is None
    assert reason == phase2.VERDICT_INVALID_AUDIO


def test_invalid_wav_is_rejected(tmp_path):
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not a riff file at all")
    assert phase2.wav_header(broken) is None
    audio, reason = phase2.read_slice(broken, 0, 1000)
    assert audio is None
    assert reason == phase2.VERDICT_INVALID_AUDIO


def test_out_of_bounds_window_is_rejected(tmp_path):
    real = _write_wav(tmp_path / "real.wav", 2000)
    audio, reason = phase2.read_slice(real, 0, 5000)
    assert audio is None
    assert reason == phase2.VERDICT_OUT_OF_BOUNDS


def test_negative_window_is_rejected(tmp_path):
    real = _write_wav(tmp_path / "real.wav", 2000)
    audio, reason = phase2.read_slice(real, -100, 1000)
    assert audio is None
    assert reason == phase2.VERDICT_OUT_OF_BOUNDS


def test_too_short_slice_is_rejected(tmp_path):
    real = _write_wav(tmp_path / "real.wav", 2000)
    audio, reason = phase2.read_slice(real, 0, 100)  # 100 ms
    assert audio is None
    assert reason == phase2.VERDICT_TOO_SHORT


def test_a_real_slice_is_read_at_the_candidate_coordinates(tmp_path):
    real = _write_wav(tmp_path / "real.wav", 5000)
    audio, reason = phase2.read_slice(real, 1000, 3000)
    assert reason is None
    assert audio is not None
    assert audio.size == 2000 * 16
    assert float(np.max(np.abs(audio))) > 0.0


def test_reading_uses_the_standard_library_only():
    """``soundfile`` is not a dependency of this implementation."""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "soundfile" not in imported
    assert "import soundfile" not in source
    assert "wave" in imported


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------
def _decide(**overrides):
    kwargs = {
        "expected_guru": "krishnaji",
        "predicted_guru": "krishnaji",
        "cosine": 0.8,
        "margin": 0.6,
        "cosine_floor": 0.3,
        "margin_threshold": 0.1,
        "calibration_available": True,
    }
    kwargs.update(overrides)
    return phase2.decide_verdict(**kwargs)


def test_verified_when_every_gate_clears():
    assert _decide()[0] == phase2.VERDICT_VERIFIED


def test_refused_below_cosine_floor():
    verdict, reason = _decide(cosine=0.29)
    assert verdict == phase2.VERDICT_REFUSED_BELOW_COSINE_FLOOR
    assert reason == phase2.VERDICT_REFUSED_BELOW_COSINE_FLOOR


def test_refused_below_margin():
    verdict, reason = _decide(margin=0.05)
    assert verdict == phase2.VERDICT_REFUSED_BELOW_MARGIN
    assert reason == phase2.VERDICT_REFUSED_BELOW_MARGIN


def test_refused_guru_mismatch():
    verdict, reason = _decide(predicted_guru="preethaji")
    assert verdict == phase2.VERDICT_REFUSED_GURU_MISMATCH
    assert reason == phase2.VERDICT_REFUSED_GURU_MISMATCH


def test_guru_mismatch_outranks_the_score_gates():
    verdict, _reason = _decide(predicted_guru="preethaji", cosine=0.0, margin=0.0)
    assert verdict == phase2.VERDICT_REFUSED_GURU_MISMATCH


def test_exact_threshold_boundary_is_accepted():
    verdict, _reason = _decide(cosine=0.3, margin=0.1)
    assert verdict == phase2.VERDICT_VERIFIED


def test_just_below_the_boundary_is_refused():
    verdict, _reason = _decide(cosine=0.2999999, margin=0.1)
    assert verdict == phase2.VERDICT_REFUSED_BELOW_COSINE_FLOOR
    verdict, _reason = _decide(cosine=0.3, margin=0.0999999)
    assert verdict == phase2.VERDICT_REFUSED_BELOW_MARGIN


def test_absent_calibration_fails_closed():
    verdict, reason = _decide(calibration_available=False)
    assert verdict == phase2.VERDICT_CALIBRATION_UNAVAILABLE
    assert reason == phase2.VERDICT_CALIBRATION_UNAVAILABLE


def test_absent_calibration_thresholds_fail_closed():
    verdict, _reason = _decide(cosine_floor=None, margin_threshold=None)
    assert verdict == phase2.VERDICT_CALIBRATION_UNAVAILABLE


def test_non_finite_score_is_never_verified():
    verdict, _reason = _decide(cosine=float("nan"))
    assert verdict == phase2.VERDICT_NOT_RUN
    verdict, _reason = _decide(margin=float("inf"))
    assert verdict == phase2.VERDICT_NOT_RUN


def test_every_verdict_category_is_declared():
    for category in phase2.VERDICT_CATEGORIES:
        assert category in phase2.VERDICT_CATEGORIES
    assert set(phase2.VERDICT_CATEGORIES) == {
        "verified",
        "refused_below_cosine_floor",
        "refused_below_margin",
        "refused_guru_mismatch",
        "missing_audio",
        "invalid_audio",
        "out_of_bounds",
        "too_short",
        "calibration_unavailable",
        "not_run",
    }


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
def test_calibration_fails_closed_without_a_measurable_impostor_set():
    trials = {
        "split": "calibration",
        "positive_trials": [],
        "impostor_trials": [],
        "unlabeled_slices": 0,
    }
    calibration = phase2.calibrate_from_trials(trials)
    assert calibration["calibration_available"] is False
    assert calibration["cosine_floor"] is None
    assert calibration["margin_threshold"] is None


def test_calibration_fails_closed_with_too_few_impostor_trials():
    trials = {
        "split": "calibration",
        "positive_trials": [{"cosine": 0.9, "margin": 0.7}],
        "impostor_trials": [
            {"cosine": 0.1, "margin": -0.5} for _ in range(phase2.MIN_IMPOSTOR_TRIALS - 1)
        ],
        "unlabeled_slices": 0,
    }
    calibration = phase2.calibrate_from_trials(trials)
    assert calibration["calibration_available"] is False


def test_calibration_floor_sits_strictly_above_every_impostor():
    impostors = [{"cosine": 0.20 + 0.01 * i, "margin": -0.5 + 0.01 * i} for i in range(25)]
    trials = {
        "split": "calibration",
        "positive_trials": [{"cosine": 0.8, "margin": 0.6}],
        "impostor_trials": impostors,
        "unlabeled_slices": 0,
    }
    calibration = phase2.calibrate_from_trials(trials)
    assert calibration["calibration_available"] is True
    assert calibration["cosine_floor"] > max(i["cosine"] for i in impostors)
    assert calibration["margin_threshold"] >= 0.0
    assert calibration["calibration_false_accept_rate"] == 0.0


def test_calibration_never_returns_a_negative_floor():
    impostors = [{"cosine": -0.9, "margin": -0.9} for _ in range(25)]
    trials = {
        "split": "calibration",
        "positive_trials": [{"cosine": 0.8, "margin": 0.6}],
        "impostor_trials": impostors,
        "unlabeled_slices": 0,
    }
    calibration = phase2.calibrate_from_trials(trials)
    assert calibration["cosine_floor"] > 0.0
    assert calibration["margin_threshold"] > 0.0


def test_evaluation_measures_false_accept_and_false_reject():
    trials = {
        "split": "test",
        "positive_trials": [
            {"cosine": 0.9, "margin": 0.7, "predicted": "krishnaji", "label": "krishnaji"},
            {"cosine": 0.1, "margin": 0.05, "predicted": "krishnaji", "label": "krishnaji"},
        ],
        "impostor_trials": [
            {"cosine": 0.2, "margin": -0.4, "claimed": "preethaji", "true_label": "krishnaji"},
            {"cosine": 0.5, "margin": 0.4, "claimed": "preethaji", "true_label": "krishnaji"},
        ],
        "unlabeled_slices": 0,
    }
    evaluation = phase2.evaluate_on_split(trials, cosine_floor=0.3, margin_threshold=0.1)
    assert evaluation["false_accepts"] == 1
    assert evaluation["false_accept_rate"] == 0.5
    assert evaluation["false_rejects"] == 1
    assert evaluation["false_reject_rate"] == 0.5


# ---------------------------------------------------------------------------
# Row schema
# ---------------------------------------------------------------------------
def _good_row(**overrides) -> dict:
    row = {
        "schema": phase2.VERDICT_SCHEMA,
        "run_id": "f" * 64,
        "source_span_id": "a" * 64,
        "video_id": "vid0001",
        "guru_id": "krishnaji",
        "expected_guru": "krishnaji",
        "predicted_guru": "krishnaji",
        "source_text_hash": "b" * 64,
        "transcript_hash": "c" * 64,
        "timed_transcript_sha256": "c" * 64,
        "audio_path": "/tmp/vid0001.wav",
        "audio_sha256": "e" * 64,
        "audio_sample_rate": 16000,
        "audio_duration_ms": 60000,
        "audio_start_ms": 1000,
        "audio_end_ms": 4000,
        "audio_slice_duration_ms": 3000,
        "audio_window_ordered": True,
        "speaker_model": phase2.ECAPA_MODEL_ID,
        "speaker_model_revision": "0" * 40,
        "speaker_device": "cpu",
        "calibration_revision": "9" * 64,
        "cosine": 0.8,
        "runner_up_cosine": 0.2,
        "margin": 0.6,
        "cosine_floor": 0.3,
        "margin_threshold": 0.1,
        "split": "test",
        "verdict": phase2.VERDICT_VERIFIED,
        "verdict_group": "verified",
        "reason_code": phase2.VERDICT_VERIFIED,
    }
    row.update(overrides)
    return row


def test_a_well_formed_row_passes_validation():
    assert phase2.validate_row(_good_row()) == []


def test_a_row_without_a_source_span_id_fails_validation():
    failures = phase2.validate_row(_good_row(source_span_id=""))
    assert "missing_source_span_id" in failures


def test_a_row_with_a_non_finite_score_fails_validation():
    failures = phase2.validate_row(_good_row(cosine=float("nan")))
    assert "non_finite_cosine" in failures


def test_a_row_with_a_missing_calibration_floor_fails_validation():
    failures = phase2.validate_row(_good_row(cosine_floor=None))
    assert "non_finite_cosine_floor" in failures


def test_a_verdict_that_is_not_reproducible_fails_validation():
    failures = phase2.validate_row(_good_row(cosine=0.1, verdict=phase2.VERDICT_VERIFIED))
    assert "verdict_not_reproducible" in failures


def test_a_row_with_an_unknown_verdict_fails_validation():
    failures = phase2.validate_row(_good_row(verdict="probably"))
    assert "unknown_verdict" in failures


def test_a_display_label_as_expected_guru_fails_validation():
    failures = phase2.validate_row(_good_row(expected_guru="Sri Krishnaji"))
    assert "expected_guru_not_a_registry_id" in failures


def test_an_audio_failure_row_must_not_carry_a_score():
    failures = phase2.validate_row(
        _good_row(verdict=phase2.VERDICT_MISSING_AUDIO, cosine=0.8)
    )
    assert "audio_failure_with_a_score" in failures


def test_an_audio_failure_row_needs_no_prediction():
    row = _good_row(
        verdict=phase2.VERDICT_MISSING_AUDIO,
        reason_code=phase2.VERDICT_MISSING_AUDIO,
        predicted_guru=None,
        cosine=None,
        runner_up_cosine=None,
        margin=None,
    )
    assert phase2.validate_row(row) == []


# ---------------------------------------------------------------------------
# Determinism and the no-write guarantee
# ---------------------------------------------------------------------------
def _fake_vector(seed: str) -> np.ndarray:
    digest = int(phase2._sha256_bytes(seed.encode("utf-8"))[:8], 16)
    rng = np.random.default_rng(digest)
    vector = rng.normal(size=192).astype(np.float32)
    return vector / float(np.linalg.norm(vector))


def test_the_verdict_row_is_deterministic():
    references = {"krishnaji": _fake_vector("k"), "preethaji": _fake_vector("p")}
    row = _candidate_row()
    kwargs = {
        "candidate_row": row,
        "vector": _fake_vector("span"),
        "audio_failure": None,
        "references": references,
        "split": "test",
        "calibration_available": True,
        "cosine_floor": 0.3,
        "margin_threshold": 0.1,
        "run_id": "r" * 64,
        "calibration_revision": "c" * 64,
        "model_revision": "m" * 40,
        "device": "cpu",
        "audio_dir": Path("/tmp"),
        "audio_hashes": {"vid0001": "e" * 64},
        "audio_info": {"vid0001": {"sample_rate": 16000, "duration_ms": 60000}},
        "slice_durations": {"a" * 64: 3000},
    }
    first = phase2.build_verdict_row(**kwargs)
    second = phase2.build_verdict_row(**kwargs)
    assert first == second


def test_the_split_assignment_is_deterministic_and_video_disjoint():
    assert phase2.assign_split("vid0001") == phase2.assign_split("vid0001")
    for video_id in ("a", "b", "c", "d"):
        assert phase2.assign_split(video_id) in {"train", "calibration", "test"}
    # The anchor videos seed the references and can never be a held-out trial.
    for _guru, (video_id, _moment) in phase2.ANCHORS.items():
        assert phase2.assign_split(video_id) == "train"


def test_the_script_has_no_qdrant_client_and_no_write_mode():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "qdrant_client" not in imported
    assert "redis" not in imported
    assert "requests" not in imported
    for forbidden in ("upsert(", "delete_collection", "create_collection", "set_payload"):
        assert forbidden not in source


def test_the_write_mode_is_refused_with_exit_code_two(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--candidate",
            str(CANDIDATE),
            "--quarantine",
            str(QUARANTINE),
            "--audio-dir",
            str(tmp_path),
            "--out-verdicts",
            str(tmp_path / "v.json"),
            "--out-calibration",
            str(tmp_path / "c.json"),
            "--out-summary",
            str(tmp_path / "s.json"),
            "--write-to-qdrant",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "refused" in result.stderr


# ---------------------------------------------------------------------------
# The shipped artifact (skipped when it is not present)
# ---------------------------------------------------------------------------
def test_shipped_verdict_artifact_is_keyed_by_source_span_id():
    artifact = EVIDENCE / "public_release_phase2_verdicts_2026-10-22.json"
    if not artifact.is_file():
        pytest.skip("Phase 2 verdict artifact is not present")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["key_field"] == "source_span_id"
    verdicts = payload["verdicts"]
    assert len(verdicts) == EXPECTED_SPANS
    for span_id, row in verdicts.items():
        assert row["source_span_id"] == span_id
        assert phase2.validate_row(row) == []
        assert row["verdict"] in phase2.VERDICT_CATEGORIES


def test_shipped_verdict_artifact_excludes_every_quarantined_span():
    artifact = EVIDENCE / "public_release_phase2_verdicts_2026-10-22.json"
    if not (artifact.is_file() and QUARANTINE.is_file()):
        pytest.skip("Phase 2 artifacts are not present")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    _rows, quarantine_ids, _without = phase2.load_quarantine(
        QUARANTINE, expected_rows=EXPECTED_QUARANTINE_ROWS
    )
    assert set(payload["verdicts"]) & quarantine_ids == set()


def test_shipped_calibration_artifact_is_release_grade():
    artifact = EVIDENCE / "public_release_phase2_calibration_2026-10-22.json"
    if not artifact.is_file():
        pytest.skip("Phase 2 calibration artifact is not present")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    for field in (
        "model",
        "embedding_configuration",
        "reference_construction",
        "trial_counts",
        "score_distributions",
        "thresholds",
        "false_accept",
        "false_reject",
        "calibration_method",
        "calibration_available",
        "data_hashes",
        "generated_at_utc",
        "split_definition",
    ):
        assert field in payload, field
    assert payload["calibration_available"] is True
    assert payload["model"]["revision"] == phase2._ecapa_revision()
    assert payload["thresholds"]["cosine_floor"] is not None
    assert payload["trial_counts"]["calibration_impostor_trials"] >= phase2.MIN_IMPOSTOR_TRIALS
