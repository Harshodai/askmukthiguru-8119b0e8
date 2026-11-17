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


# ---------------------------------------------------------------------------
# Windowed ECAPA v1 (review F1/F2/F6)
# ---------------------------------------------------------------------------

WINDOWED_ROW = {
    "source_span_id": "s1",
    "video_id": "vid",
    "verdict_group": "verified",
    "span_cosine_mean": 0.71,
    "span_cosine_min": 0.53,
    "span_margin_min": 0.19,
    "windowed_calibration_revision": "a40b315b",
    "model_revision": "0f99f2d0",
    "window_check": "pass",
}
CAL = {"cosine_floor": 0.492987, "margin_threshold": 1e-6}


def test_windowed_promotes_with_full_provenance_and_min_cosine():
    outcome, upd = w.decide_windowed(PENDING, WINDOWED_ROW, NOW, CAL)
    assert outcome == "promoted"
    assert upd["speaker_verified"] is True
    assert upd["voice_verification_method"] == "ecapa_voxceleb_windowed_v1"
    assert upd["voice_calibration_id"] == "a40b315b"
    assert upd["voice_model_revision"] == "0f99f2d0"
    # Never the mean: the gate is per-window.
    assert upd["voice_score"] == 0.53
    assert upd["voice_threshold_applied"]["cosine_floor"] == 0.492987
    assert set(upd) <= set(w.ALLOWED_KEYS)


def test_windowed_refusal_demotes_a_legacy_verified_row():
    legacy = {**PENDING, "speaker_verified": True, "speaker_verification_status": "verified"}
    row = {**WINDOWED_ROW, "verdict_group": "refused", "window_check": "fail"}
    outcome, upd = w.decide_windowed(legacy, row, NOW, CAL)
    assert outcome == "demoted"
    assert upd["speaker_verified"] is False
    assert upd["speaker_verification_status"] == "ecapa_failed"
    assert upd["voice_verified_at"] is None


@pytest.mark.parametrize("group", ["not_run", None])
def test_windowed_indeterminate_is_no_evidence(group):
    """An unscored span is not a refusal: nothing is written."""
    row = {**WINDOWED_ROW, "verdict_group": group}
    assert w.decide_windowed(PENDING, row, NOW, CAL) == ("windowed_no_evidence", {})


def test_windowed_without_score_is_no_evidence():
    row = {**WINDOWED_ROW, "span_cosine_min": None, "cosine": None}
    assert w.decide_windowed(PENDING, row, NOW, CAL) == ("windowed_no_evidence", {})


def test_windowed_missing_calibration_id_stays_untouched():
    row = {**WINDOWED_ROW, "windowed_calibration_revision": None}
    assert w.decide_windowed(PENDING, row, NOW, CAL) == ("windowed_no_evidence", {})


def test_windowed_skips_already_windowed_rows_unless_recheck():
    done = {
        **PENDING,
        "speaker_verified": True,
        "speaker_verification_status": "verified",
        "voice_verification_method": "ecapa_voxceleb_windowed_v1",
    }
    assert w.decide_windowed(done, WINDOWED_ROW, NOW, CAL) == ("not_pending", {})

    # --recheck-windowed re-evaluates and rewrites the score under the current rule.
    outcome, upd = w.decide_windowed(done, WINDOWED_ROW, NOW, CAL, recheck=True)
    assert outcome == "promoted"
    assert upd["voice_score"] == 0.53
