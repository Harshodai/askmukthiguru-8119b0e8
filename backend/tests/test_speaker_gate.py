"""In-ingest windowed ECAPA speaker gate (`services/speaker_gate.py`).

The gate is the only thing standing between a live upload and a payload that claims a
verified speaker, so these tests pin its three rules:

1. a label that does not name exactly one registry teacher is *not applicable* (`{}`);
2. a gate that cannot produce a verdict stamps ``pending_voice_check``, never verified;
3. a claim that the write rule would refuse is demoted before it can be written.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services import speaker_gate  # noqa: E402


class _StubVerifier:
    def __init__(self, fields):
        self.fields = fields
        self.calls = []

    def verify_audio_file(self, wav_path, start_ms, end_ms, guru_id):
        self.calls.append((str(wav_path), start_ms, end_ms, guru_id))
        if isinstance(self.fields, Exception):
            raise self.fields
        return dict(self.fields)


def _verified_fields():
    return {
        "speaker_verified": True,
        "speaker_verification_status": "verified",
        "voice_verification_method": "ecapa_voxceleb_windowed_v1",
        "voice_model_revision": "0f99f2d0",
        "voice_calibration_id": "a40b315b",
        "voice_score": 0.61,
        "voice_margin": 0.22,
        "voice_threshold_applied": {"cosine_floor": 0.49, "margin_threshold": 1e-6},
        "voice_window_check": "pass",
        "voice_verified_at": "2026-11-17T00:00:00+00:00",
    }


@pytest.fixture()
def armed(monkeypatch):
    monkeypatch.setattr(speaker_gate, "enabled", lambda: True)
    speaker_gate.reset_for_tests()
    yield
    speaker_gate.reset_for_tests()


# ---------------------------------------------------------------------------
# Label -> guru
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label,expected",
    [
        ("Sri Krishnaji", "krishnaji"),
        ("krishnaji", "krishnaji"),
        ("SRI_PREETHAJI", "preethaji"),
        ("Sri Preethaji & Sri Krishnaji", None),  # compound: no single expected voice
        ("Unknown", None),
        ("", None),
        (None, None),
    ],
)
def test_guru_for_speaker(label, expected):
    assert speaker_gate.guru_for_speaker(label) == expected


# ---------------------------------------------------------------------------
# Applicability
# ---------------------------------------------------------------------------

def test_disabled_gate_stamps_nothing(monkeypatch):
    monkeypatch.setattr(speaker_gate, "enabled", lambda: False)
    assert speaker_gate.verify(
        audio_path="/tmp/a.wav", start_ms=0, end_ms=1000, speaker="Sri Krishnaji"
    ) == {}


def test_compound_label_stamps_nothing(armed):
    assert speaker_gate.verify(
        audio_path="/tmp/a.wav",
        start_ms=0,
        end_ms=1000,
        speaker="Sri Preethaji & Sri Krishnaji",
    ) == {}


def test_missing_bounds_are_pending_not_verified(armed):
    result = speaker_gate.verify(
        audio_path="/tmp/a.wav", start_ms=None, end_ms=1000, speaker="Sri Krishnaji"
    )
    assert result["speaker_verified"] is False
    assert result["speaker_verification_status"] == "pending_voice_check"


def test_unavailable_verifier_is_pending_not_verified(armed, monkeypatch):
    monkeypatch.setattr(speaker_gate, "get_verifier", lambda: None)
    result = speaker_gate.verify(
        audio_path="/tmp/a.wav", start_ms=0, end_ms=1000, speaker="Sri Krishnaji"
    )
    assert result["speaker_verified"] is False
    assert result["speaker_verification_status"] == "pending_voice_check"


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

def test_valid_verified_record_is_returned_unchanged(armed):
    stub = _StubVerifier(_verified_fields())
    speaker_gate.set_verifier_for_tests(stub)
    result = speaker_gate.verify(
        audio_path="/tmp/a.wav", start_ms=1000, end_ms=4000, speaker="Sri Krishnaji", video_id="vid"
    )
    assert result["speaker_verified"] is True
    assert result["voice_verification_method"] == "ecapa_voxceleb_windowed_v1"
    assert stub.calls == [("/tmp/a.wav", 1000, 4000, "krishnaji")]


def test_invalid_verified_record_is_demoted_before_it_can_be_written(armed):
    broken = _verified_fields()
    broken["voice_score"] = 0.10  # below its own recorded floor
    speaker_gate.set_verifier_for_tests(_StubVerifier(broken))

    result = speaker_gate.verify(
        audio_path="/tmp/a.wav", start_ms=0, end_ms=1000, speaker="Sri Krishnaji"
    )
    assert result["speaker_verified"] is False
    assert result["speaker_verification_status"] == "pending_voice_check"


def test_verifier_exception_is_pending_not_a_crash(armed):
    speaker_gate.set_verifier_for_tests(_StubVerifier(RuntimeError("boom")))
    result = speaker_gate.verify(
        audio_path="/tmp/a.wav", start_ms=0, end_ms=1000, speaker="Sri Krishnaji"
    )
    assert result["speaker_verified"] is False
    assert result["speaker_verification_status"] == "pending_voice_check"


# ---------------------------------------------------------------------------
# annotate_chunks
# ---------------------------------------------------------------------------

def test_annotate_chunks_is_parallel_and_only_gates_teacher_labels(armed, monkeypatch):
    monkeypatch.setattr(speaker_gate, "max_spans_per_source", lambda: 10)
    speaker_gate.set_verifier_for_tests(_StubVerifier(_verified_fields()))

    out = speaker_gate.annotate_chunks(
        chunks=["a", "b", "c"],
        starts=[0.0, 10.0, 20.0],
        ends=[5.0, 15.0, 25.0],
        speakers=["Sri Krishnaji", "Unknown", None],
        audio_path="/tmp/a.wav",
    )

    assert len(out) == 3
    assert out[0]["speaker_verified"] is True
    assert out[1] == {}
    assert out[2] == {}


def test_annotate_chunks_caps_cost_and_stamps_pending(armed, monkeypatch):
    monkeypatch.setattr(speaker_gate, "max_spans_per_source", lambda: 1)
    speaker_gate.set_verifier_for_tests(_StubVerifier(_verified_fields()))

    out = speaker_gate.annotate_chunks(
        chunks=["a", "b"],
        starts=[0.0, 10.0],
        ends=[5.0, 15.0],
        speakers=["Sri Krishnaji", "Sri Krishnaji"],
        audio_path="/tmp/a.wav",
    )

    assert out[0]["speaker_verified"] is True
    assert out[1]["speaker_verified"] is False
    assert out[1]["speaker_verification_status"] == "pending_voice_check"


def test_annotate_chunks_without_timing_is_pending(armed):
    speaker_gate.set_verifier_for_tests(_StubVerifier(_verified_fields()))
    out = speaker_gate.annotate_chunks(
        chunks=["a"],
        starts=None,
        ends=None,
        speakers=["Sri Krishnaji"],
        audio_path="/tmp/a.wav",
    )
    assert out[0]["speaker_verified"] is False
    assert out[0]["speaker_verification_status"] == "pending_voice_check"


# ---------------------------------------------------------------------------
# Boot / status reporting (X41)
# ---------------------------------------------------------------------------

def test_status_reports_off_when_disabled(monkeypatch):
    monkeypatch.setattr(speaker_gate, "enabled", lambda: False)
    state = speaker_gate.status()
    assert state["state"] == "off"
    assert state["enabled"] is False


def test_status_reports_missing_references_in_its_own_units(armed, monkeypatch):
    monkeypatch.setattr(speaker_gate, "_references_path", lambda: None)
    state = speaker_gate.status()
    assert state["state"] == "missing_references"
    assert "references" in state["reason"].lower()


def test_status_ready_when_both_artifacts_exist(armed, monkeypatch, tmp_path):
    refs = tmp_path / "references.npz"
    refs.write_bytes(b"x")
    cal = tmp_path / "cal.json"
    cal.write_text("{}")
    monkeypatch.setattr(speaker_gate, "_references_path", lambda: refs)
    monkeypatch.setattr(speaker_gate, "_calibration_path", lambda: cal)
    state = speaker_gate.status()
    assert state["state"] == "ready"
    assert state["references_path"] == str(refs)
