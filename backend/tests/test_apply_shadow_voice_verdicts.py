"""Shadow voice-verdict writer: promotion needs ECAPA verified AND a window pass."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import apply_shadow_voice_verdicts as w  # noqa: E402

NOW = "2026-11-17T00:00:00+00:00"
PENDING = {
    "source_span_id": "s1",
    "speaker_id": "Sri Krishnaji",
    "speaker_verified": False,
    "speaker_verification_status": "pending_voice_check",
}


def _v(group="verified", **kw):
    row = {
        "source_span_id": "s1", "verdict_group": group, "cosine": 0.7, "margin": 0.3,
        "cosine_floor": 0.28, "margin_threshold": 0.05,
        "speaker_model_revision": "rev", "calibration_revision": "cal",
    }
    row.update(kw)
    return row


def _w(verdict="window_pass"):
    return {"source_span_id": "s1", "verdict": verdict}


def test_verified_plus_window_pass_promotes_with_full_provenance():
    outcome, upd = w.decide(PENDING, _v(), _w(), NOW)
    assert outcome == "promoted" and upd["speaker_verified"] is True
    assert upd["voice_verification_method"] == "ecapa_voxceleb_span_slice_v2"
    assert set(upd) <= set(w.ALLOWED_KEYS)


@pytest.mark.parametrize("window", [None, _w("no_diarization"), _w("window_fail")])
def test_missing_window_check_is_no_evidence(window):
    assert w.decide(PENDING, _v(), window, NOW) == ("no_evidence", {})


def test_refused_unverifies_without_a_method():
    for verdict, window in ((_v("refused"), None), (_v("refused"), _w("window_fail"))):
        outcome, upd = w.decide(PENDING, verdict, window, NOW)
        assert outcome == "ecapa_failed" and upd["speaker_verified"] is False
        assert upd["voice_verification_method"] is None


def test_incomplete_record_stays_pending_and_non_pending_is_skipped():
    assert w.decide(PENDING, _v(speaker_model_revision=None), _w(), NOW) == ("guard_refused", {})
    done = {**PENDING, "speaker_verification_status": "verified"}
    assert w.decide(done, _v(), _w(), NOW) == ("not_pending", {})


def test_other_collections_are_refused_and_apply_needs_a_snapshot(tmp_path):
    base = ["--verdicts-jsonl", "v", "--windows-jsonl", "w", "--report", str(tmp_path / "r")]
    assert w.main([*base, "--collection", "first_person_v10"]) == 2
    assert w.main([*base, "--apply"]) == 2


def test_allowed_keys_are_declared_span_fields():
    from domain.first_person_context import SourceSpan

    assert set(w.ALLOWED_KEYS) <= set(SourceSpan.model_fields)
