"""P3: the corpus builders write provenance with every verified speaker claim.

Torch-free: the helpers live in ``domain.speaker_provenance`` and the strict assert in the
store, so no model, audio or Qdrant is needed.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from domain.speaker_provenance import (
    METHOD_ECAPA_CENTROID_V1,
    METHOD_ECAPA_SPAN_SLICE_V2,
    STATUS_ECAPA_FAILED,
    STATUS_PENDING_VOICE_CHECK,
    STATUS_VERIFIED,
    automated_voice_fields,
    calibration_id_from,
    pending_voice_fields,
    span_slice_voice_fields,
    speaker_write_violations,
)
from services.first_person_context_store import (
    FirstPersonContextStoreError,
    assert_speaker_provenance,
    speaker_provenance_violations,
)

EVIDENCE = {"cosine": 0.71, "margin": 0.4, "cosine_floor": 0.2828, "margin_threshold": 0.05}


def _auto(**over):
    kwargs = dict(
        verified=True,
        evidence=EVIDENCE,
        model_revision="rev-1",
        calibration_id="cal-1",
        verified_at="2026-10-31T00:00:00+00:00",
        window_check="pass",
    )
    kwargs.update(over)
    return automated_voice_fields(**kwargs)


def test_verified_span_records_full_provenance_and_passes_the_write_rule():
    fields = _auto()
    assert fields["speaker_verified"] is True
    assert fields["voice_verification_method"] == METHOD_ECAPA_SPAN_SLICE_V2
    assert fields["speaker_verification_status"] == STATUS_VERIFIED
    assert fields["voice_model_revision"] == "rev-1"
    assert fields["voice_calibration_id"] == "cal-1"
    assert fields["voice_score"] == pytest.approx(0.71)
    assert fields["voice_margin"] == pytest.approx(0.4)
    assert fields["voice_threshold_applied"] == {"cosine_floor": 0.2828, "margin_threshold": 0.05}
    assert speaker_write_violations(fields) == []


@pytest.mark.parametrize("evidence", [None, {}, {"cosine": None}, {"cosine": float("nan")}])
def test_no_score_is_pending_voice_check_never_verified(evidence):
    fields = _auto(evidence=evidence)
    assert fields == pending_voice_fields()
    assert fields["speaker_verified"] is False
    assert fields["voice_verification_method"] is None
    assert fields["speaker_verification_status"] == STATUS_PENDING_VOICE_CHECK


@pytest.mark.parametrize(
    "over",
    [
        {"calibration_id": None},
        {"calibration_id": "  "},
        {"model_revision": None},
        {"evidence": {**EVIDENCE, "cosine_floor": None}},
        {"evidence": {**EVIDENCE, "cosine": 0.10}},  # below its own floor
        {"evidence": {**EVIDENCE, "margin": 0.01}},  # below its own margin threshold
    ],
)
def test_verified_claim_without_backing_evidence_is_demoted_not_dropped(over):
    fields = _auto(**over)
    assert fields["speaker_verified"] is False
    assert fields["voice_verification_method"] is None
    assert fields["speaker_verification_status"] == STATUS_PENDING_VOICE_CHECK
    assert speaker_write_violations(fields) == []


def test_failed_check_records_the_evidence_and_no_method():
    fields = _auto(verified=False)
    assert fields["speaker_verified"] is False
    assert fields["voice_verification_method"] is None
    assert fields["speaker_verification_status"] == STATUS_ECAPA_FAILED
    assert fields["voice_score"] == pytest.approx(0.71)
    assert fields["voice_calibration_id"] == "cal-1"


def _slice(**over):
    kwargs = dict(
        verified=True,
        scored=True,
        cosine=0.71,
        margin=0.4,
        foreign_window_count=0,
        cosine_floor=0.2828,
        margin_threshold=0.05,
        model_revision="rev-1",
        calibration_id="cal-1",
        verified_at="2026-10-31T00:00:00+00:00",
    )
    kwargs.update(over)
    return span_slice_voice_fields(**kwargs)


def test_span_slice_verified_marks_window_pass():
    fields = _slice()
    assert fields["voice_window_check"] == "pass"
    assert speaker_write_violations(fields) == []


def test_span_slice_with_no_embedding_is_pending_not_a_zero_score():
    # verify_span_speaker returns cosine=0.0 when there is no audio. That is a placeholder.
    fields = _slice(verified=False, scored=False, cosine=0.0, margin=0.0)
    assert fields == pending_voice_fields()
    assert "voice_score" not in fields


def test_span_slice_foreign_window_is_recorded_as_a_failed_window():
    fields = _slice(verified=False, foreign_window_count=2)
    assert fields["voice_window_check"] == "fail"
    assert fields["speaker_verified"] is False
    assert fields["speaker_verification_status"] == STATUS_ECAPA_FAILED


def test_span_slice_below_floor_without_foreign_window_has_no_window_claim():
    fields = _slice(verified=False, cosine=0.1)
    assert fields["voice_window_check"] is None


def test_a_new_write_claiming_the_legacy_centroid_method_is_refused():
    claim = {
        "speaker_verified": True,
        "voice_verification_method": METHOD_ECAPA_CENTROID_V1,
        "voice_score": 0.9,
    }
    assert speaker_write_violations(claim) == [f"legacy_method_refused:{METHOD_ECAPA_CENTROID_V1}"]
    # Reading stored data may tolerate it, so the promotion gate can count it.
    assert speaker_write_violations(claim, allow_legacy_centroid=True) == []


def test_calibration_id_prefers_the_pinned_revision():
    assert calibration_id_from({"calibration_revision": "rev-x"}, b"{}") == "rev-x"


def test_calibration_id_falls_back_to_the_file_hash():
    raw = json.dumps({"cosine_floor": 0.3}).encode()
    assert calibration_id_from({"cosine_floor": 0.3}, raw) == (
        "file-sha256:" + hashlib.sha256(raw).hexdigest()
    )
    assert calibration_id_from({"calibration_revision": " "}, raw).startswith("file-sha256:")


# ------------------------------------------------------------ strict collection assert


def _payload(**fields):
    base = {"record_type": "retrieval_child", "source_span_id": "s1"}
    base.update(fields)
    return base


def test_assert_speaker_provenance_accepts_complete_and_unverified():
    assert_speaker_provenance(
        [
            _payload(source_span_id="a", **_auto()),
            _payload(source_span_id="b", **pending_voice_fields()),
        ],
        where="test",
    )


def test_assert_speaker_provenance_refuses_a_method_with_no_score_or_calibration():
    bad = _payload(
        source_span_id="bad",
        speaker_verified=True,
        voice_verification_method=METHOD_ECAPA_SPAN_SLICE_V2,
    )
    with pytest.raises(FirstPersonContextStoreError, match="1 span"):
        assert_speaker_provenance([_payload(source_span_id="ok", **_auto()), bad], where="test")
    assert set(speaker_provenance_violations([bad])) == {"bad"}


def test_assert_speaker_provenance_refuses_a_legacy_centroid_claim_on_a_new_write():
    legacy = _payload(
        source_span_id="old",
        speaker_verified=True,
        voice_verification_method=METHOD_ECAPA_CENTROID_V1,
    )
    with pytest.raises(FirstPersonContextStoreError, match="legacy_method_refused"):
        assert_speaker_provenance([legacy], where="test")


def test_a_verified_v2_claim_without_margin_or_margin_threshold_is_refused():
    # D7: a missing margin used to pass because the margin check only ran when present.
    no_margin = _auto()
    no_margin.pop("voice_margin")
    assert "ecapa_missing:voice_margin" in speaker_write_violations(no_margin)
    no_threshold = _auto()
    no_threshold["voice_threshold_applied"] = {"cosine_floor": 0.2828}
    assert "ecapa_missing:margin_threshold" in speaker_write_violations(no_threshold)
    # The builder helper demotes it instead of claiming it.
    demoted = _auto(evidence={**EVIDENCE, "margin": None})
    assert demoted == pending_voice_fields()


def test_promotion_gate_and_store_collection_check_agree_on_who_violates():
    # D5: one rule. The gate's violator set equals the store's speaker_provenance_violations.
    from domain.speaker_audit import promotion_speaker_gate

    payloads = [
        _payload(source_span_id="ok", **_auto()),
        _payload(
            source_span_id="no_calibration",
            **_auto(calibration_id=None)
            | {
                "speaker_verified": True,
                "voice_verification_method": METHOD_ECAPA_SPAN_SLICE_V2,
                "voice_calibration_id": None,
                "voice_score": 0.7,
                "voice_margin": 0.4,
                "voice_model_revision": "rev-1",
                "voice_threshold_applied": {"cosine_floor": 0.28, "margin_threshold": 0.05},
            },
        ),
        _payload(source_span_id="bare", speaker_verified=True),
        _payload(source_span_id="unverified", **pending_voice_fields()),
    ]
    gate = promotion_speaker_gate(payloads)
    store_view = speaker_provenance_violations(payloads)
    assert set(store_view) == {"no_calibration", "bare"}
    assert gate["violators"]["count"] == len(store_view)
    assert gate["violators"]["span_ids_first_20"] == sorted(store_view)
