"""Unit tests for ingest.verbatim.gates (ASR-agreement gate)."""

from ingest.verbatim.gates import (
    MIN_ASR_AGREEMENT,
    check_asr_agreement,
    script_and_loop_problem,
)


def test_script_and_loop_problem_detects_mixed_scripts():
    """D1: Mixed script ASR output (Urdu + Cyrillic + English) is flagged."""
    text = "کہ Ift my addiction isn't even physicalyфصل"
    prob = script_and_loop_problem(text, expected_script="Latin")
    assert prob is not None
    assert "asr_script_garbage" in prob


def test_script_and_loop_problem_detects_char_loop():
    """D1: Decoder character loops are flagged."""
    text = "तुई अवेखन … अवाँँँँँँ"
    prob = script_and_loop_problem(text, expected_script="Latin")
    assert prob is not None
    assert "asr_char_loop" in prob or "asr_script_garbage" in prob


def test_script_and_loop_problem_detects_word_loop():
    """D1: 5+ word repetition loops are flagged."""
    text = "peace peace peace peace peace"
    prob = script_and_loop_problem(text, expected_script="Latin")
    assert prob is not None
    assert "asr_word_loop:peace" in prob


def test_script_and_loop_problem_clean_english_passes():
    """Valid English with punctuation passes."""
    text = "What is peace? Peace is an inner state of stillness."
    assert script_and_loop_problem(text, expected_script="Latin") is None


def test_script_and_loop_problem_sanskrit_iast_passes():
    """Sanskrit IAST transliterated accents pass."""
    text = "Śrī Bhagavan teaches that mukthi or samādhi is an inner state of peace."
    assert script_and_loop_problem(text, expected_script="Latin") is None


def test_script_and_loop_problem_devanagari_expected_passes():
    """Devanagari text passes when expected_script is Devanagari."""
    text = "ध्यान आंतरिक शांति की यात्रा है।"
    assert script_and_loop_problem(text, expected_script="Devanagari") is None


def test_auto_script_accepts_a_wholly_devanagari_span():
    """Serve time is multilingual: a single non-Latin script is not garbage."""
    text = "दुःख एक आंतरिक विभाजन है।"
    assert script_and_loop_problem(text, expected_script=None) is None


def test_auto_script_accepts_english():
    assert script_and_loop_problem("What is peace?", expected_script=None) is None


def test_auto_script_still_flags_a_mixed_span():
    """D1: the live defect mixes scripts, so auto-detection must still refuse it."""
    text = "کہ Ift my addiction isn't even physicalyфصل"
    prob = script_and_loop_problem(text, expected_script=None)
    assert prob is not None and "asr_script_garbage" in prob


def test_auto_script_still_flags_a_decoder_loop():
    prob = script_and_loop_problem("तुई अवेखन … अवाँँँँँँ", expected_script=None)
    assert prob is not None


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
