"""Unit tests for ingest.verbatim.gates (ASR-agreement gate)."""

from ingest.verbatim.gates import MIN_ASR_AGREEMENT, check_asr_agreement


def test_passes_above_threshold():
    assert check_asr_agreement({"ok": True, "agreement_rate": 0.95}) is None


def test_passes_exactly_at_threshold():
    assert check_asr_agreement({"ok": True, "agreement_rate": MIN_ASR_AGREEMENT}) is None


def test_fails_below_threshold_with_rate_in_reason():
    reason = check_asr_agreement({"ok": True, "agreement_rate": 0.5})
    assert reason == "asr_agreement_low:0.500"


def test_unknown_when_vote_failed():
    assert check_asr_agreement({"ok": False}) == "asr_agreement_unknown"


def test_unknown_when_rate_missing():
    assert check_asr_agreement({"ok": True}) == "asr_agreement_unknown"


def test_custom_threshold_overrides_default():
    assert check_asr_agreement({"ok": True, "agreement_rate": 0.7}, min_agreement=0.6) is None
