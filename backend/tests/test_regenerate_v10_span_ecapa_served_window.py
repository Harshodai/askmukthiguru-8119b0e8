"""Served-window mode of ``scripts.ops.regenerate_v10_span_ecapa_verdicts`` (B2).

A live span is served at ``[start_ms - 250, end_ms + 250]`` (the citation
player's ``CITATION_PLAYBACK_PAD_S``), which is **not** the reconstruction window
the candidate mode scores. These tests pin:

* the served window bounds (and the clamp at zero);
* that the sliced audio really is the served window, measured in samples on a
  synthetic WAV;
* that every row echoes the pinned calibration revision and is never
  recalibrated;
* that a broken or unmeasurable calibration fails closed (exit 2, no rows).

No torch / speechbrain / scikit-learn: the slice embedder is injected, so this
module runs in the locked release image too.
"""

from __future__ import annotations

import json
import math
import struct
import sys
import wave
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve()
if _HERE.parents[1].name == "app" or _HERE.parents[1] == Path("/app"):
    _BACKEND = Path("/app")
else:
    _BACKEND = _HERE.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import regenerate_v10_span_ecapa_verdicts as phase2  # noqa: E402

SAMPLE_RATE = 16000


def _write_wav(path: Path, duration_ms: int, amplitude: float = 0.2) -> None:
    frames = int(SAMPLE_RATE * duration_ms / 1000)
    samples = b"".join(
        struct.pack("<h", int(amplitude * 32767 * math.sin(2 * math.pi * 220 * i / SAMPLE_RATE)))
        for i in range(frames)
    )
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(samples)


def _span(**over):
    base = {
        "point_id": "11111111-1111-1111-1111-111111111111",
        "source_span_id": "span-1",
        "video_id": "vid1",
        "start_ms": 9000,
        "end_ms": 13000,
        "speaker_id": "Sri Preethaji",
    }
    base.update(over)
    return base


def _calibration(**over):
    base = {
        "calibration_available": True,
        "calibration_revision": "pinned-revision-2026-10-30",
        "cosine_floor": 0.28282581431961057,
        "margin_threshold": 1e-06,
    }
    base.update(over)
    return base


class _RecordingEmbedder:
    """Fake slice embedder: records the sample count it was handed."""

    def __init__(self, vector: np.ndarray):
        self.vector = vector
        self.sample_counts: list[int] = []

    def __call__(self, audio: np.ndarray) -> np.ndarray:
        self.sample_counts.append(int(audio.size))
        return self.vector


_REFERENCE = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)


def _references() -> dict[str, np.ndarray]:
    return {
        "preethaji": _REFERENCE,
        "krishnaji": np.asarray([0.0, 1.0, 0.0], dtype=np.float32),
    }


# ---------------------------------------------------------------------------
# Pure window bounds
# ---------------------------------------------------------------------------
def test_served_window_adds_the_citation_pad_on_both_sides():
    assert phase2.served_window(9000, 13000) == (8750, 13250)
    assert phase2.served_window(9000, 13000, pad_ms=0) == (9000, 13000)


def test_served_window_clamps_the_start_at_zero_but_not_the_end():
    assert phase2.served_window(100, 900) == (0, 1150)
    assert phase2.served_window(0, 500) == (0, 750)
    # A negative input is clamped, not carried into a negative slice offset.
    assert phase2.served_window(-5000, 500)[0] == 0


def test_served_pad_matches_the_citation_playback_pad():
    assert phase2.SERVED_PAD_MS == 250


# ---------------------------------------------------------------------------
# The slice that is embedded is the served window
# ---------------------------------------------------------------------------
def test_rows_are_scored_on_the_served_window_and_echo_the_calibration(tmp_path):
    _write_wav(tmp_path / "vid1.wav", duration_ms=20000)
    embedder = _RecordingEmbedder(_REFERENCE)
    spans = [_span(), _span(source_span_id="span-2", start_ms=100, end_ms=900)]

    rows, counters = phase2.span_verdict_rows(
        spans,
        audio_dir=tmp_path,
        calibration=_calibration(),
        references=_references(),
        embed_slice_fn=embedder,
        run_id="run-1",
        model_revision="pinned-ecapa-revision",
        device="cpu",
    )

    assert counters["rows"] == 2
    assert counters["audio_failures"] == {}
    # 9000-250 .. 13000+250 = 4500 ms; 100-250 clamps to 0 .. 900+250 = 1150 ms.
    assert embedder.sample_counts == [int(4.5 * SAMPLE_RATE), int(1.15 * SAMPLE_RATE)]

    first, second = rows
    assert (first["window_start_ms"], first["window_end_ms"]) == (8750, 13250)
    assert (first["span_start_ms"], first["span_end_ms"]) == (9000, 13000)
    assert (second["window_start_ms"], second["window_end_ms"]) == (0, 1150)
    assert first["audio_slice_duration_ms"] == 4500
    assert second["audio_slice_duration_ms"] == 1150

    for row in rows:
        assert row["calibration_revision"] == "pinned-revision-2026-10-30"
        assert row["mode"] == "served_window"
        assert row["schema"] == phase2.SPAN_VERDICT_SCHEMA
        assert row["verdict"] == phase2.VERDICT_VERIFIED
        assert row["expected_guru"] == "preethaji"
        assert phase2.validate_row(row) == []


def test_the_slice_is_not_the_reconstruction_window(tmp_path):
    _write_wav(tmp_path / "vid1.wav", duration_ms=20000)
    embedder = _RecordingEmbedder(_REFERENCE)
    rows, _counters = phase2.span_verdict_rows(
        [_span()],
        audio_dir=tmp_path,
        calibration=_calibration(),
        references=_references(),
        embed_slice_fn=embedder,
        run_id="run-1",
        model_revision="pinned-ecapa-revision",
        device="cpu",
    )
    # The reconstruction window would be 4000 ms; the served window is 4500 ms.
    assert embedder.sample_counts == [int(4.5 * SAMPLE_RATE)]
    assert rows[0]["audio_slice_duration_ms"] != 4000


def test_a_window_past_the_file_fails_closed_with_no_score(tmp_path):
    _write_wav(tmp_path / "vid1.wav", duration_ms=5000)
    embedder = _RecordingEmbedder(_REFERENCE)
    rows, counters = phase2.span_verdict_rows(
        [_span(start_ms=4800, end_ms=4900)],
        audio_dir=tmp_path,
        calibration=_calibration(),
        references=_references(),
        embed_slice_fn=embedder,
        run_id="run-1",
        model_revision="pinned-ecapa-revision",
        device="cpu",
    )
    assert counters["audio_failures"] == {phase2.VERDICT_OUT_OF_BOUNDS: 1}
    assert embedder.sample_counts == []
    assert rows[0]["verdict"] == phase2.VERDICT_OUT_OF_BOUNDS
    assert rows[0]["cosine"] is None
    assert rows[0]["calibration_revision"] == "pinned-revision-2026-10-30"


def test_a_different_teacher_is_refused_not_verified(tmp_path):
    _write_wav(tmp_path / "vid1.wav", duration_ms=20000)
    other = np.asarray([0.0, 1.0, 0.0], dtype=np.float32)
    rows, _counters = phase2.span_verdict_rows(
        [_span(speaker_id="Sri Krishnaji")],
        audio_dir=tmp_path,
        calibration=_calibration(),
        references=_references(),
        embed_slice_fn=_RecordingEmbedder(other),
        run_id="run-1",
        model_revision="pinned-ecapa-revision",
        device="cpu",
    )
    assert rows[0]["expected_guru"] == "krishnaji"
    assert rows[0]["predicted_guru"] == "krishnaji"
    assert rows[0]["verdict"] == phase2.VERDICT_VERIFIED


# ---------------------------------------------------------------------------
# Inputs fail closed
# ---------------------------------------------------------------------------
def test_load_pinned_calibration_reads_nested_thresholds_and_the_revision(tmp_path):
    path = tmp_path / "calibration.json"
    path.write_text(
        json.dumps(
            {
                "calibration_available": True,
                "calibration_revision": "rev-nested",
                "thresholds": {"cosine_floor": 0.31, "margin_threshold": 0.02},
            }
        )
    )
    calibration = phase2.load_pinned_calibration(path)
    assert calibration["cosine_floor"] == 0.31
    assert calibration["margin_threshold"] == 0.02
    assert calibration["calibration_revision"] == "rev-nested"
    assert calibration["sha256"]


def test_an_unmeasurable_or_unrevisioned_calibration_is_rejected(tmp_path):
    cases = {
        "unavailable": {"calibration_available": False, "calibration_revision": "r"},
        "no_revision": {
            "calibration_available": True,
            "cosine_floor": 0.3,
            "margin_threshold": 0.0,
        },
        "no_floor": {"calibration_available": True, "calibration_revision": "r"},
    }
    for name, payload in cases.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload))
        try:
            phase2.load_pinned_calibration(path)
        except phase2.InputError:
            continue
        raise AssertionError(f"{name} calibration must be rejected")


def test_load_spans_rejects_duplicates_bad_bounds_and_unknown_speakers(tmp_path):
    good = _span()
    _calibration()  # keep the helper used for readability
    for name, row in {
        "duplicate": good,
        "bounds": _span(end_ms=100),
        "speaker": _span(speaker_id="Host"),
        "missing_id": _span(source_span_id=""),
        "non_integer": _span(start_ms="9000"),
    }.items():
        path = tmp_path / f"{name}.jsonl"
        rows = [good, row] if name == "duplicate" else [row]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        try:
            phase2.load_spans(path)
        except phase2.InputError:
            continue
        raise AssertionError(f"{name} spans must be rejected")


def test_served_window_mode_requires_its_inputs(tmp_path, capsys):
    code = phase2.main(
        ["--spans-jsonl", str(tmp_path / "spans.jsonl"), "--audio-dir", str(tmp_path)]
    )
    assert code == phase2.EXIT_INVALID_INPUT
    assert "requires" in capsys.readouterr().err
