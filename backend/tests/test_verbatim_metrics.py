"""Unit tests for verbatim speech metrics and timestamp precision (Invariant B2)."""

import pytest
from evaluation.verbatim_metrics import (
    normalize_speech,
    evaluate_verbatim_quote,
    parse_timestamp_seconds,
    evaluate_timestamp_precision,
)


def test_normalize_speech():
    raw = "Don't divide life into 'you' and 'I'—that's suffering!"
    norm = normalize_speech(raw)
    assert "do not divide life into you and i that is suffering" == norm


def test_evaluate_verbatim_quote_exact_substring():
    ref = "Every day lived in a beautiful state is life truly lived."
    quote = "A beautiful state is life truly lived."
    res = evaluate_verbatim_quote(quote, ref)
    assert res["is_verbatim"] is True
    assert res["method"] == "exact_normalized_substring"
    assert res["score"] == 1.0


def test_evaluate_verbatim_quote_punctuation_variance():
    ref = "Meditation is not concentration; it is pure, effortless witnessing."
    quote = "Meditation is not concentration it is pure effortless witnessing"
    res = evaluate_verbatim_quote(quote, ref)
    assert res["is_verbatim"] is True


def test_evaluate_verbatim_quote_one_substituted_word_still_scores_high():
    """A 17-token quote with a single word substituted mid-quote is 16 real
    matches out of 17 -- the true matched-token ratio should still be >= 0.9.
    The longest-CONTIGUOUS-run metric this replaces would score ~0.47 instead
    (8/17), because the mid-quote substitution splits the match into two
    roughly-equal halves and only the longer half counted."""
    ref = "Suffering ends when you cease to divide yourself from life and stay separate from love completely today"
    quote = "Suffering ends when you cease to divide yourself XSUBSTITUTEDX life and stay separate from love completely today"
    res = evaluate_verbatim_quote(quote, ref)
    assert res["token_lcs_ratio"] >= 0.9


def test_evaluate_verbatim_quote_missing_word_is_not_an_exact_match():
    """Dropping a single word (the negation "not") breaks the exact-substring
    match (method 1) and the character-level ratio still reflects it (well
    below the 0.95 threshold) -- both unaffected by the token-metric fix.

    The token ratio divides by max(candidate, aligned reference span), so the
    skipped reference word counts against it. A candidate-only denominator
    scored this dropped negation a perfect 1.0 and passed it end to end
    (found and fixed 2026-09-25).
    """
    ref = "Meditation is not concentration; it is pure, effortless witnessing."
    quote_missing_not = "Meditation is concentration it is pure effortless witnessing"
    res = evaluate_verbatim_quote(quote_missing_not, ref)

    assert res["method"] != "exact_normalized_substring"
    assert res["char_lcs_ratio"] < 0.95
    # the aligned-span denominator counts the reference word the quote skipped
    assert res["token_lcs_ratio"] < 0.95
    assert res["is_verbatim"] is False


def test_evaluate_verbatim_quote_rejects_hallucination():
    ref = "The four sacred secrets reveal how inner connection transforms destiny."
    quote = "Quantum mechanics suggests that consciousness is an observer effect in physics."
    res = evaluate_verbatim_quote(quote, ref)
    assert res["is_verbatim"] is False
    assert res["score"] < 0.3


def test_parse_timestamp_seconds():
    assert parse_timestamp_seconds(120) == 120.0
    assert parse_timestamp_seconds("120") == 120.0
    assert parse_timestamp_seconds("02:30") == 150.0
    assert parse_timestamp_seconds("01:02:30") == 3750.0
    assert parse_timestamp_seconds("https://youtu.be/abc?t=45s") == 45.0
    assert parse_timestamp_seconds("https://youtu.be/abc&t=90") == 90.0


def test_evaluate_timestamp_precision_early_lead_in_valid():
    # Predicted start is 5s early (gives good conversational lead-in)
    res = evaluate_timestamp_precision(pred_start=95.0, pred_end=120.0, gt_start=100.0, gt_end=120.0)
    assert res["is_valid_onset"] is True
    assert res["onset_error_s"] == -5.0
    assert res["ux_score"] > 0.7


def test_evaluate_timestamp_precision_late_start_invalid():
    # Predicted start is 4s late (clips first words)
    res = evaluate_timestamp_precision(pred_start=104.0, pred_end=120.0, gt_start=100.0, gt_end=120.0)
    assert res["is_valid_onset"] is False  # Beyond lag_tol_s = 2.0
    assert res["onset_error_s"] == 4.0
    assert res["ux_score"] < 0.4
