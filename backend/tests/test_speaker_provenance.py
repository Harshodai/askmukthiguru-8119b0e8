"""P1 provenance fields and the P2 write rule (domain level, no Qdrant, no network).

The rule is the single source of truth shared by the store's ``upsert`` and the backfill
writer, so each refusal reason has its own test here. Store- and backfill-level tests
(that nothing is written) live next to those writers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from domain import speaker_provenance as sp  # noqa: E402

SHA = "a" * 64


def _v2(**over):
    base = {
        "source_span_id": "span-1",
        "speaker_verified": True,
        "voice_verification_method": sp.METHOD_ECAPA_SPAN_SLICE_V2,
        "voice_score": 0.71,
        "voice_margin": 0.40,
        "voice_threshold_applied": {"cosine_floor": 0.2828, "margin_threshold": 0.05},
        "voice_calibration_id": "cal-1",
        "voice_model_revision": "rev-1",
        "voice_window_check": "pass",
        "speaker_verification_status": "verified",
    }
    base.update(over)
    return base


def _human(**over):
    base = {
        "source_span_id": "span-1",
        "speaker_verified": True,
        "voice_verification_method": sp.METHOD_HUMAN_LISTEN_V1,
        "reviewer_id": "reviewer-1",
        "reviewed_at": "2026-10-31T10:00:00+00:00",
        "reviewed_audio_sha256": SHA,
    }
    base.update(over)
    return base


# ---- allowed --------------------------------------------------------------------------------
def test_a_complete_ecapa_record_is_allowed():
    assert sp.speaker_write_violations(_v2()) == []


def test_a_complete_human_record_is_allowed():
    assert sp.speaker_write_violations(_human()) == []


def test_legacy_centroid_method_is_still_writable_without_the_new_fields():
    payload = {"speaker_verified": True, "voice_verification_method": sp.METHOD_ECAPA_CENTROID_V1}
    assert sp.speaker_write_violations(payload) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"speaker_verified": False},
        {"speaker_verified": False, "voice_verification_method": None},
        {"speaker_verified": False, "voice_score": 0.0, "voice_verification_method": "x"},
        {},
    ],
)
def test_an_unverified_span_is_always_writable(payload):
    assert sp.speaker_write_violations(payload) == []


# ---- one refusal test per rule --------------------------------------------------------------
@pytest.mark.parametrize("method", [None, "", "   "])
def test_refuses_verified_with_no_method(method):
    out = sp.speaker_write_violations(_v2(voice_verification_method=method))
    assert out == [sp.CODE_NO_METHOD]


def test_refuses_an_unknown_method():
    out = sp.speaker_write_violations(_v2(voice_verification_method="trust_me"))
    assert out == ["voice_method_unknown:trust_me"]


@pytest.mark.parametrize(
    "key",
    ["voice_score", "voice_calibration_id", "voice_model_revision", "voice_threshold_applied"],
)
def test_refuses_ecapa_span_slice_missing_any_required_field(key):
    payload = _v2()
    payload.pop(key)
    assert sp.speaker_write_violations(payload) == [f"ecapa_missing:{key}"]


@pytest.mark.parametrize("bad", [None, "", float("nan"), float("inf"), True, "0.7"])
def test_refuses_a_non_numeric_or_non_finite_score(bad):
    assert "ecapa_missing:voice_score" in sp.speaker_write_violations(_v2(voice_score=bad))


def test_refuses_a_score_below_the_floor_recorded_with_it():
    out = sp.speaker_write_violations(_v2(voice_score=0.2))
    assert out == ["ecapa_score_below_floor"]


def test_a_score_exactly_at_the_floor_is_allowed():
    assert sp.speaker_write_violations(_v2(voice_score=0.2828)) == []


def test_refuses_a_margin_below_its_threshold():
    out = sp.speaker_write_violations(_v2(voice_margin=0.01))
    assert out == ["ecapa_margin_below_threshold"]


def test_refuses_when_the_independent_window_check_failed():
    out = sp.speaker_write_violations(_v2(voice_window_check="fail"))
    assert out == ["window_check_failed"]


def test_refuses_a_status_that_contradicts_the_flag():
    out = sp.speaker_write_violations(_v2(speaker_verification_status="ecapa_failed"))
    assert out == ["status_contradicts_flag:ecapa_failed"]


@pytest.mark.parametrize("key", ["reviewer_id", "reviewed_at", "reviewed_audio_sha256"])
def test_refuses_human_listen_missing_any_review_field(key):
    payload = _human()
    payload.pop(key)
    assert sp.speaker_write_violations(payload) == [f"human_missing:{key}"]


@pytest.mark.parametrize("bad", ["abc", "G" * 64, "A" * 64, "a" * 63])
def test_refuses_a_human_listen_with_a_malformed_audio_hash(bad):
    out = sp.speaker_write_violations(_human(reviewed_audio_sha256=bad))
    assert out == ["human_missing:reviewed_audio_sha256"]


def test_human_listen_is_not_held_to_the_ecapa_fields():
    # A human listen records who and what was heard, not a cosine.
    assert "voice_score" not in _human()
    assert sp.speaker_write_violations(_human()) == []


# ---- raising wrapper ------------------------------------------------------------------------
def test_assert_names_the_span_and_every_reason():
    with pytest.raises(sp.SpeakerWriteRefused) as caught:
        sp.assert_speaker_write_allowed(_v2(voice_score=None, voice_calibration_id=None))
    assert caught.value.span_id == "span-1"
    assert "ecapa_missing:voice_score" in caught.value.violations
    assert "ecapa_missing:voice_calibration_id" in caught.value.violations
    assert "span-1" in str(caught.value)


def test_assert_is_silent_when_the_record_is_complete():
    sp.assert_speaker_write_allowed(_v2())


# ---- P1: model fields -----------------------------------------------------------------------
def _span_kwargs(**over):
    from domain.first_person_context import (
        BoundaryStatus,
        CompletenessStatus,
        SpeakerRole,
        clip_text_hash,
        make_source_span_id,
    )

    text = "hold the intention to live free from fear and walk with steady grace today"
    transcript_hash = "b" * 64
    base = {
        "corpus_version": "fp-context-v1",
        "guru_id": "krishnaji",
        "video_id": "vidA",
        "source_asset_id": "vidA",
        "source_span_id": make_source_span_id(
            guru_id="krishnaji",
            video_id="vidA",
            corpus_version="fp-context-v1",
            word_start=0,
            word_end=13,
            transcript_hash=transcript_hash,
        ),
        "parent_unit_id": "parentA",
        "turn_id": "t0",
        "turn_index": 0,
        "source_span_index": 0,
        "start_ms": 0,
        "end_ms": 9000,
        "word_start": 0,
        "word_end": 13,
        "speaker_id": "krishnaji",
        "speaker_role": SpeakerRole.GURU,
        "speaker_verified": True,
        "source_transcript_text": text,
        "verbatim_text": text,
        "transcript_hash": transcript_hash,
        "source_text_hash": clip_text_hash(text),
        "boundary_status": BoundaryStatus.VERIFIED,
        "completeness_status": CompletenessStatus.COMPLETE,
        "rights_cleared": True,
        "caption_status": "auto",
        "source_url": "https://www.youtube.com/watch?v=vidA",
    }
    base.update(over)
    return base


def test_provenance_fields_round_trip_through_to_payload():
    from domain.first_person_context import SourceSpan

    span = SourceSpan(
        **_span_kwargs(
            voice_verification_method=sp.METHOD_ECAPA_SPAN_SLICE_V2,
            voice_model_revision="rev-1",
            voice_score=0.71,
            voice_margin=0.4,
            voice_threshold_applied={"cosine_floor": 0.2828, "margin_threshold": 0.05},
            voice_calibration_id="cal-1",
            voice_window_check="pass",
            voice_verified_at="2026-10-31T10:00:00+00:00",
            speaker_verification_status="verified",
        )
    )
    payload = span.to_payload()
    for key in sp.AUTOMATED_PROVENANCE_KEYS:
        assert key in payload, key
    assert payload["voice_threshold_applied"] == {"cosine_floor": 0.2828, "margin_threshold": 0.05}
    restored = SourceSpan.model_validate({k: v for k, v in payload.items() if k != "record_type"})
    assert restored == span
    assert sp.speaker_write_violations(payload) == []


def test_human_review_fields_round_trip():
    from domain.first_person_context import SourceSpan

    span = SourceSpan(
        **_span_kwargs(
            voice_verification_method=sp.METHOD_HUMAN_LISTEN_V1,
            reviewer_id="r1",
            reviewed_at="2026-10-31T10:00:00+00:00",
            review_guidelines_version="v1",
            reviewed_audio_sha256=SHA,
            review_choice="sri_krishnaji",
        )
    )
    payload = span.to_payload()
    for key in sp.HUMAN_REVIEW_KEYS:
        assert payload[key] is not None, key
    assert sp.speaker_write_violations(payload) == []


def test_an_old_payload_without_the_new_fields_still_loads():
    """Reads stay tolerant: the 732 live spans carry none of these keys."""
    from domain.first_person_context import SourceSpan

    legacy = SourceSpan(**_span_kwargs(voice_verification_method=None))
    payload = legacy.to_payload()
    for key in sp.AUTOMATED_PROVENANCE_KEYS[1:] + sp.HUMAN_REVIEW_KEYS:
        payload.pop(key)
    payload.pop("record_type")
    restored = SourceSpan.model_validate(payload)
    assert restored.speaker_verified is True
    assert restored.voice_score is None
    # ...and the WRITE rule still names the defect on it.
    assert sp.speaker_write_violations(restored.to_payload()) == [sp.CODE_NO_METHOD]


@pytest.mark.parametrize(
    "field,value",
    [
        ("voice_window_check", "maybe"),
        ("speaker_verification_status", "trusted"),
        ("review_choice", "krishnaji"),
        ("reviewed_audio_sha256", "xyz"),
    ],
)
def test_the_model_rejects_values_outside_the_vocabulary(field, value):
    from pydantic import ValidationError

    from domain.first_person_context import SourceSpan

    with pytest.raises(ValidationError):
        SourceSpan(**_span_kwargs(**{field: value}))


def test_the_vocabularies_in_the_model_match_the_module():
    from domain.first_person_context import SourceSpan

    def literal_values(name):
        annotation = SourceSpan.model_fields[name].annotation
        out = set()
        stack = [annotation]
        while stack:
            current = stack.pop()
            args = getattr(current, "__args__", None)
            if args:
                stack.extend(args)
            elif isinstance(current, str):
                out.add(current)
        return out

    assert literal_values("speaker_verification_status") == set(sp.SPEAKER_VERIFICATION_STATUSES)
    assert literal_values("voice_window_check") == set(sp.WINDOW_CHECKS)
    assert literal_values("review_choice") == set(sp.REVIEW_CHOICES)
