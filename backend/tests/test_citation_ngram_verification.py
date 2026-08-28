"""
Test citation n-gram verification protocol.
Verifies 8-word verbatim continuous n-gram matching against source transcripts.
"""

import pytest
from services.citation_service import (
    extract_verbatim_quotes,
    check_continuous_ngram_match,
    verify_quote_ngram_fidelity,
    verify_citation_ngrams,
)

SAMPLE_TRANSCRIPT = (
    "Every moment of your life you are living either in a beautiful state "
    "or in a suffering state. There is no third state. In a beautiful state, "
    "you experience connection, joy, calm, and profound stillness. The warring self "
    "dissolves into universal intelligence, allowing divine grace to flow freely."
)


def test_extract_verbatim_quotes_straight_quotes():
    """Verify extraction of phrases inside straight double quotes."""
    text = 'Sri Krishnaji said, "Every moment of your life you are living" and smiled.'
    quotes = extract_verbatim_quotes(text)
    assert len(quotes) == 1
    assert quotes[0] == "Every moment of your life you are living"


def test_extract_verbatim_quotes_curly_quotes():
    """Verify extraction of phrases inside curly quotes."""
    text = 'The teaching emphasizes: “The warring self dissolves into universal intelligence” as key.'
    quotes = extract_verbatim_quotes(text)
    assert len(quotes) == 1
    assert quotes[0] == "The warring self dissolves into universal intelligence"


def test_exact_8_word_continuous_match_positive():
    """Verify exact 8-word verbatim continuous sequence matches."""
    # 8 words: "Every moment of your life you are living"
    quote_8_words = "Every moment of your life you are living"
    assert check_continuous_ngram_match(quote_8_words, SAMPLE_TRANSCRIPT, n=8) is True


def test_long_quote_containing_8_word_ngram_positive():
    """Verify long quote with multiple 8-word continuous n-grams matches."""
    quote_15_words = (
        "Every moment of your life you are living either in a beautiful state "
        "or in a suffering state."
    )
    assert check_continuous_ngram_match(quote_15_words, SAMPLE_TRANSCRIPT, n=8) is True


def test_hallucinated_quote_rejection_negative():
    """Verify fabricated quote with no matching continuous 8-word n-gram is rejected."""
    hallucinated_quote = (
        "Every human being must meditate three hours daily to reach enlightened salvation."
    )
    assert check_continuous_ngram_match(hallucinated_quote, SAMPLE_TRANSCRIPT, n=8) is False


def test_rearranged_words_rejection_negative():
    """Verify that scrambled words from source do NOT match continuous 8-word n-gram."""
    # Words exist in transcript, but NOT in this continuous 8-word order
    scrambled_quote = (
        "living state beautiful suffering moment life every universal intelligence dissolving"
    )
    assert check_continuous_ngram_match(scrambled_quote, SAMPLE_TRANSCRIPT, n=8) is False


def test_short_quote_under_8_words():
    """Verify quotes with fewer than 8 words match if they appear continuously."""
    short_positive = "The warring self dissolves"  # 4 words
    assert check_continuous_ngram_match(short_positive, SAMPLE_TRANSCRIPT, n=8) is True

    short_negative = "The peaceful self awakens"
    assert check_continuous_ngram_match(short_negative, SAMPLE_TRANSCRIPT, n=8) is False


def test_case_and_punctuation_tolerance():
    """Verify matching is case-insensitive and ignores surrounding punctuation/newlines."""
    quote_varied = (
        "EVERY MOMENT OF YOUR LIFE, YOU ARE LIVING\n"
        "EITHER IN A BEAUTIFUL STATE..."
    )
    assert check_continuous_ngram_match(quote_varied, SAMPLE_TRANSCRIPT, n=8) is True


def test_verify_quote_ngram_fidelity_metrics():
    """Verify detailed metric computation for quote fidelity."""
    quote = "Every moment of your life you are living either in a beautiful state"
    fidelity = verify_quote_ngram_fidelity(quote, SAMPLE_TRANSCRIPT, n=8)
    assert fidelity["matched"] is True
    assert fidelity["quote_word_count"] == 13
    assert fidelity["matched_ngrams_count"] == 6  # 13 - 8 + 1 = 6
    assert fidelity["total_ngrams_count"] == 6
    assert fidelity["match_ratio"] == 1.0

    fake_quote = "This is a completely fabricated teaching that does not exist anywhere."
    fake_fidelity = verify_quote_ngram_fidelity(fake_quote, SAMPLE_TRANSCRIPT, n=8)
    assert fake_fidelity["matched"] is False
    assert fake_fidelity["match_ratio"] == 0.0


def test_verify_citation_ngrams_answer_level():
    """Verify answer-level citation n-gram check against context documents."""
    context_docs = [
        {"title": "Beautiful State Discourse", "text": SAMPLE_TRANSCRIPT},
        {"title": "Soul Sync Teaching", "text": "Soul Sync is an 8-step meditation for inner peace."},
    ]

    answer_valid = (
        'As Sri Krishnaji teaches, "Every moment of your life you are living either in a beautiful state '
        'or in a suffering state." [[CITE:1]]'
    )
    res_valid = verify_citation_ngrams(answer_valid, context_docs, n=8)
    assert res_valid["verified"] is True
    assert res_valid["quotes_checked"] == 1
    assert res_valid["quotes_passed"] == 1

    answer_invalid = (
        'As Sri Krishnaji stated, "You should abandon all worldly pursuits and live alone in the mountains." [[CITE:1]]'
    )
    res_invalid = verify_citation_ngrams(answer_invalid, context_docs, n=8)
    assert res_invalid["verified"] is False
    assert res_invalid["quotes_checked"] == 1
    assert res_invalid["quotes_passed"] == 0


def test_empty_quote_handling():
    """Verify empty or non-quoted answer passes trivially."""
    assert verify_citation_ngrams("Plain answer with no quotes.", [{"text": SAMPLE_TRANSCRIPT}])["verified"] is True
    assert check_continuous_ngram_match("", SAMPLE_TRANSCRIPT) is False
    assert check_continuous_ngram_match("some quote", "") is False
