"""Tests for windowed_ecapa_v1_scorer — pure functions only.

No torch, no speechbrain, no Qdrant, no audio I/O.  Every test exercises a
deterministic function that depends only on numpy arrays, lists of dicts, and
scalars.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops.windowed_ecapa_v1_scorer import (  # noqa: E402
    GROUP_NOT_RUN,
    GROUP_REFUSED,
    GROUP_VERIFIED,
    SILENCE_RMS_FLOOR,
    VERDICT_INDETERMINATE,
    VERDICT_REFUSED_FLOOR,
    VERDICT_REFUSED_HOST,
    VERDICT_REFUSED_MARGIN,
    VERDICT_VERIFIED,
    _roc_auc,
    _slide_windows,
    calibrate_windowed_floor,
    is_silent,
    windowed_verdict,
)

# ---------------------------------------------------------------------------
# is_silent
# ---------------------------------------------------------------------------

def test_silence_skip_all_silent():
    """All-zeros audio is silent."""
    audio = np.zeros(16000 * 3, dtype=np.float32)
    assert is_silent(audio, SILENCE_RMS_FLOOR) is True


def test_silence_skip_non_silent():
    """A 440 Hz sine at reasonable amplitude is not silent."""
    t = np.linspace(0, 3.0, 16000 * 3, endpoint=False)
    audio = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    assert is_silent(audio, SILENCE_RMS_FLOOR) is False


def test_silence_empty_array():
    assert is_silent(np.array([], dtype=np.float32)) is True


def test_silence_just_below_floor():
    # RMS exactly at the floor boundary.
    # floor = 0.01, so RMS < 0.01 → silent.
    audio = np.full(16000, 0.009, dtype=np.float32)
    assert is_silent(audio, SILENCE_RMS_FLOOR) is True


def test_silence_just_above_floor():
    audio = np.full(16000, 0.011, dtype=np.float32)
    assert is_silent(audio, SILENCE_RMS_FLOOR) is False


# ---------------------------------------------------------------------------
# windowed_verdict — core cases
# ---------------------------------------------------------------------------

def _make_window_score(cosine: float, margin: float, predicted: str) -> dict:
    return {"cosine": cosine, "margin": margin, "predicted": predicted, "scores": {}}


def test_all_windows_pass_verified():
    """4 windows all above floor for the right teacher → verified."""
    guru = "krishnaji"
    scores = [_make_window_score(0.75, 0.30, guru) for _ in range(4)]
    verdict, reason, stats = windowed_verdict(
        scores, guru, cosine_floor=0.28, margin_threshold=1e-6, max_failing_windows=0
    )
    assert verdict == VERDICT_VERIFIED
    assert reason == VERDICT_VERIFIED
    assert stats["group"] == GROUP_VERIFIED
    assert stats["windows_failing"] == 0


def test_one_host_window_refuses_strict():
    """3 passing + 1 wrong-guru window, max_failing=0 → refused."""
    guru = "krishnaji"
    passing = [_make_window_score(0.75, 0.30, guru) for _ in range(3)]
    host = [_make_window_score(0.72, 0.28, "preethaji")]  # wrong teacher
    verdict, reason, stats = windowed_verdict(
        passing + host, guru, cosine_floor=0.28, margin_threshold=1e-6, max_failing_windows=0
    )
    assert stats["group"] == GROUP_REFUSED
    assert stats["windows_failing"] == 1
    # Should report as a host/mismatch refusal.
    assert verdict in (VERDICT_REFUSED_HOST, VERDICT_REFUSED_FLOOR, VERDICT_REFUSED_MARGIN)


def test_zero_windows_indeterminate():
    """Empty window list → indeterminate."""
    verdict, reason, stats = windowed_verdict(
        [], "krishnaji", cosine_floor=0.28, margin_threshold=1e-6, max_failing_windows=0
    )
    assert verdict == VERDICT_INDETERMINATE
    assert stats["group"] == GROUP_NOT_RUN
    assert stats["windows_scored"] == 0


def test_one_failing_window_allowed_when_max_is_one():
    """With max_failing_windows=1, one bad window should still verify."""
    guru = "preethaji"
    passing = [_make_window_score(0.80, 0.35, guru) for _ in range(3)]
    bad = [_make_window_score(0.20, -0.10, "krishnaji")]  # below floor
    verdict, reason, stats = windowed_verdict(
        passing + bad, guru, cosine_floor=0.28, margin_threshold=1e-6, max_failing_windows=1
    )
    assert verdict == VERDICT_VERIFIED
    assert stats["group"] == GROUP_VERIFIED
    assert stats["windows_failing"] == 1


def test_two_failing_windows_refused_when_max_is_one():
    """Two bad windows exceed max_failing_windows=1 → refused."""
    guru = "preethaji"
    passing = [_make_window_score(0.80, 0.35, guru) for _ in range(2)]
    bad = [_make_window_score(0.15, -0.20, "krishnaji") for _ in range(2)]
    verdict, reason, stats = windowed_verdict(
        passing + bad, guru, cosine_floor=0.28, margin_threshold=1e-6, max_failing_windows=1
    )
    assert stats["group"] == GROUP_REFUSED
    assert stats["windows_failing"] == 2


def test_below_cosine_floor_window_refuses():
    """A window with cosine below floor → refused_below_cosine_floor."""
    guru = "krishnaji"
    scores = [_make_window_score(0.20, 0.30, guru)]  # cosine < floor
    verdict, reason, stats = windowed_verdict(
        scores, guru, cosine_floor=0.28, margin_threshold=1e-6, max_failing_windows=0
    )
    assert stats["group"] == GROUP_REFUSED
    assert VERDICT_REFUSED_FLOOR in verdict or stats["windows_failing"] == 1


def test_below_margin_threshold_window_refuses():
    """A window with margin below threshold → refused."""
    guru = "krishnaji"
    # cosine above floor but margin below threshold
    scores = [_make_window_score(0.70, 0.00001, guru)]
    verdict, reason, stats = windowed_verdict(
        scores, guru, cosine_floor=0.28, margin_threshold=0.05, max_failing_windows=0
    )
    assert stats["group"] == GROUP_REFUSED


# ---------------------------------------------------------------------------
# calibrate_windowed_floor
# ---------------------------------------------------------------------------

def test_calibration_threshold_selection():
    """Calibration from known distributions → FAR ≤ 1% and positive_pass_rate > 0.9."""
    rng = np.random.default_rng(7)
    # Positives: cosine ∈ [0.6, 0.9], margin ∈ [0.05, 0.4]
    pos = [
        {"cosine": float(c), "margin": float(m)}
        for c, m in zip(
            rng.uniform(0.6, 0.9, 200),
            rng.uniform(0.05, 0.4, 200),
        )
    ]
    # Negatives: cosine ∈ [0.1, 0.35], margin ∈ [-0.4, -0.05]
    neg = [
        {"cosine": float(c), "margin": float(m)}
        for c, m in zip(
            rng.uniform(0.1, 0.35, 100),
            rng.uniform(-0.4, -0.05, 100),
        )
    ]
    result = calibrate_windowed_floor(pos, neg, target_far=0.01)
    assert result["calibration_available"] is True
    assert result["far_on_negatives"]["rate"] <= 0.01
    assert result["positive_window_pass_rate"] >= 0.90
    assert 0.0 <= result["roc_auc"] <= 1.0
    assert "cosine_floor" in result
    assert "margin_threshold" in result


def test_calibration_too_few_negatives_fails_closed():
    """Fewer than MIN_NEGATIVE_WINDOWS negatives → calibration_available=False."""
    rng = np.random.default_rng(1)
    pos = [{"cosine": float(c), "margin": 0.2} for c in rng.uniform(0.6, 0.9, 50)]
    neg = [{"cosine": float(c), "margin": -0.1} for c in rng.uniform(0.1, 0.3, 10)]
    result = calibrate_windowed_floor(pos, neg, target_far=0.01)
    assert result["calibration_available"] is False


def test_calibration_no_positives_fails_closed():
    rng = np.random.default_rng(2)
    neg = [{"cosine": float(c), "margin": -0.1} for c in rng.uniform(0.1, 0.3, 200)]
    result = calibrate_windowed_floor([], neg, target_far=0.01)
    assert result["calibration_available"] is False


# ---------------------------------------------------------------------------
# _slide_windows
# ---------------------------------------------------------------------------

def test_slide_windows_short_audio_padded():
    """Audio shorter than window_frames gets padded to one full window."""
    sr = 16000
    audio = np.ones(int(0.5 * sr), dtype=np.float32)  # 0.5 s < 3 s window
    windows = _slide_windows(audio, window_s=3.0, hop_s=1.5, sr=sr)
    assert len(windows) == 1
    assert windows[0].shape[0] == int(3.0 * sr)


def test_slide_windows_exact_multiple():
    sr = 16000
    # 6 s audio with 3s window / 1.5s hop → starts at 0, 1.5, 3, 4.5 (but last is 3+window)
    audio = np.ones(int(6.0 * sr), dtype=np.float32)
    windows = _slide_windows(audio, window_s=3.0, hop_s=1.5, sr=sr)
    # starts: 0, 24000, 48000, 72000; last (72000+48000=120000 == audio.size) so 4 windows
    assert len(windows) >= 3


def test_slide_windows_empty_audio():
    windows = _slide_windows(np.array([], dtype=np.float32), window_s=3.0, hop_s=1.5)
    assert windows == []


# ---------------------------------------------------------------------------
# _roc_auc
# ---------------------------------------------------------------------------

def test_roc_auc_perfect_separation():
    pos = [0.9, 0.85, 0.80]
    neg = [0.2, 0.15, 0.10]
    auc = _roc_auc(pos, neg)
    assert auc > 0.99


def test_roc_auc_no_separation():
    rng = np.random.default_rng(3)
    scores = rng.uniform(0.0, 1.0, 200).tolist()
    pos = scores[:100]
    neg = scores[100:]
    auc = _roc_auc(pos, neg)
    # Random → AUC ≈ 0.5
    assert 0.3 < auc < 0.7
