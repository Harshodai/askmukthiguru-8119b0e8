"""Tests for the read-only v10 unchecked-speaker scorer."""

from __future__ import annotations

import json

from scripts.ops.score_v10_unchecked_speakers import classify_child, score

_WINDOWS = {"ok": True, "t_centres": [10.0, 11.0, 12.0], "win_lab": ["P", "P", "P"]}


def _child(**over):
    base = {
        "record_type": "retrieval_child",
        "video_id": "vid1",
        "speaker_id": "Sri Preethaji",
        "start_ms": 9000,
        "end_ms": 13000,
        "verbatim_text": "Hold the intention to live free.",
        "source_span_id": "s1",
    }
    base.update(over)
    return base


def test_matching_windows_pass():
    assert classify_child(_child(), _WINDOWS) == "window_pass"


def test_other_teacher_or_host_window_fails():
    assert classify_child(_child(speaker_id="Sri Krishnaji"), _WINDOWS) == "window_fail"
    host = {**_WINDOWS, "win_lab": ["P", "O", "P"]}
    assert classify_child(_child(), host) == "window_fail"


def test_missing_or_not_ok_diarization_is_no_evidence():
    assert classify_child(_child(), None) == "no_diarization"
    assert classify_child(_child(), {**_WINDOWS, "ok": False}) == "no_diarization"


def test_unknown_speaker_label_fails_closed():
    assert classify_child(_child(speaker_id="Host"), _WINDOWS) == "window_fail"


def test_score_skips_voice_checked_and_parents_and_counts(tmp_path):
    (tmp_path / "vid1_speaker.json").write_text(json.dumps(_WINDOWS))
    payloads = [
        _child(),
        _child(source_span_id="s2", voice_verification_method="ecapa_voxceleb_centroid_v1"),
        _child(source_span_id="s3", record_type="parent_unit"),
        _child(source_span_id="s4", video_id="vid2", verbatim_text="Why am I angry?"),
    ]
    rows, summary = score(payloads, tmp_path)
    assert [r["source_span_id"] for r in rows] == ["s1", "s4"]
    assert summary["verdicts"] == {"window_pass": 1, "no_diarization": 1}
    assert summary["no_diarization_ending_in_question"] == 1
