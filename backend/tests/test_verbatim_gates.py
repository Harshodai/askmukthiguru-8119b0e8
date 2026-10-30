"""Unit tests for ingest.verbatim.gates (ASR-agreement gate)."""

from ingest.verbatim.gates import (
    CORPUS_EXPECTED_SCRIPT,
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
    # not "peace": a guided practice says that on purpose (see the chant tests below)
    text = "the the the the the"
    prob = script_and_loop_problem(text, expected_script="Latin")
    assert prob is not None
    assert "asr_word_loop:the" in prob


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


# The two live v10 spans the first gate missed (2026-10-25 review). Both are ASR
# garbage taken from the committed export; written as escapes so the file stays ASCII.
_ALL_DEVANAGARI_GARBAGE = "और वागशी है, तो वोगशी है. तुटिट ठीटने भी इलिटकी"
_LATIN_WITH_TWO_ARABIC_LETTERS = (
    "Only these are destroying you slowly. Every addiction damages the brain. "
    "I want you to know,every addiction chips away at your self world. "
    "د Database because youد my poems every addiction makes hard."
)


def test_explicit_latin_refuses_a_wholly_devanagari_span():
    assert script_and_loop_problem(_ALL_DEVANAGARI_GARBAGE, expected_script="Latin")


def test_explicit_latin_refuses_two_arabic_letters_in_a_long_latin_span():
    """2 letters in ~160 is 1.2%, under the inferred-script ratio, still garbage."""
    assert script_and_loop_problem(_LATIN_WITH_TWO_ARABIC_LETTERS, expected_script="Latin")
    # the inferred-script mode keeps its 2% ratio, so it is NOT the serve-time mode
    assert script_and_loop_problem(_LATIN_WITH_TWO_ARABIC_LETTERS, expected_script=None) is None


def test_corpus_expected_script_is_latin():
    assert CORPUS_EXPECTED_SCRIPT == "Latin"


def test_explicit_latin_keeps_iast_sanskrit_and_plain_english():
    assert (
        script_and_loop_problem(
            "The ātman, or Self, is described in the Upaniṣads.",
            expected_script=CORPUS_EXPECTED_SCRIPT,
        )
        is None
    )
    assert script_and_loop_problem("What is peace?", expected_script=CORPUS_EXPECTED_SCRIPT) is None


def test_short_chant_run_is_speech_not_a_loop():
    """JRlaAip4kmk: a guided practice says 'peace' five times on purpose."""
    text = 'Inhale and see the word "peace" within. Peace, peace, peace, peace, peace.'
    assert script_and_loop_problem(text, expected_script="Latin") is None


def test_long_chant_run_is_still_a_decoder_loop():
    assert script_and_loop_problem("peace " * 20, expected_script="Latin")


def test_non_chant_word_loop_still_refused_at_five():
    assert script_and_loop_problem("the the the the the the", expected_script="Latin")


def test_expected_script_follows_the_declared_language():
    from ingest.verbatim.gates import expected_script_for

    assert expected_script_for(None) == "Latin"  # undeclared = the English corpus
    assert expected_script_for("") == "Latin"
    assert expected_script_for("en") == "Latin"
    assert expected_script_for("hi") == "Devanagari"
    assert expected_script_for("TE") == "Telugu"
    assert expected_script_for("xx") == "Latin"  # unknown language fails closed
