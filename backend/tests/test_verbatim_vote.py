"""Unit tests for ingest.verbatim.vote (ROVER word vote). No models, no I/O."""

from ingest.verbatim.vote import (
    glossary_hits,
    hallucination_flags,
    is_numeral_pair,
    norm_word,
    repeated_ngram_flags,
    rover_vote,
    vote_stage,
    wer,
)


def _w(word, start, end):
    return {"w": word, "start": start, "end": end}


def test_norm_word_strips_punctuation_and_lowercases():
    assert norm_word("Krishnaji,") == "krishnaji"
    assert norm_word("don't") == "don't"


def test_rover_vote_equal_words_not_disputed():
    a = [_w("hello", 0.0, 0.3), _w("world", 0.3, 0.6)]
    b = [_w("hello", 0.0, 0.3), _w("world", 0.3, 0.6)]
    voted = rover_vote(a, b)
    assert len(voted) == 2
    assert all(not w["disputed"] for w in voted)


def test_rover_vote_replace_is_disputed_with_alt():
    a = [_w("fact", 0.0, 0.3)]
    b = [_w("fat", 0.0, 0.3)]
    voted = rover_vote(a, b)
    assert voted[0]["disputed"] is True
    assert voted[0]["alt"] == "fat"


def test_rover_vote_delete_keeps_a_word_flagged_absent_in_b():
    a = [_w("hello", 0.0, 0.3), _w("extra", 0.3, 0.5)]
    b = [_w("hello", 0.0, 0.3)]
    voted = rover_vote(a, b)
    assert len(voted) == 2
    assert voted[1]["disputed"] is True
    assert voted[1]["alt"] == "(absent in B)"


def test_rover_vote_insert_in_b_produces_no_extra_a_word():
    a = [_w("hello", 0.0, 0.3)]
    b = [_w("hello", 0.0, 0.3), _w("there", 0.3, 0.5)]
    voted = rover_vote(a, b)
    assert len(voted) == 1  # B-only tokens have no A word to attach to


def test_is_numeral_pair():
    assert is_numeral_pair("two", "2")
    assert is_numeral_pair("2", "two")
    assert not is_numeral_pair("two", "three")


def test_repeated_ngram_flags_detects_a_repeated_run():
    words = ["thank", "you"] * 4 + ["for", "watching"]
    flags = repeated_ngram_flags(words, nmin=2, nmax=2, min_repeats=3)
    assert flags
    assert flags[0]["ngram"] == "thank you"
    assert flags[0]["repeats"] == 4


def test_wer_identical_is_zero_and_one_substitution_is_partial():
    assert wer(["a", "b", "c"], ["a", "b", "c"]) == 0.0
    assert wer(["a", "b", "c"], ["a", "x", "c"]) == 1 / 3


def test_glossary_hits_counts_doctrine_terms_case_insensitively():
    hits = glossary_hits(["ekam", "is", "not", "a", "place"])
    assert hits["ekam"] == 1


def test_hallucination_flags_long_disputed_run_with_no_b_support():
    voted = [{**_w(f"w{i}", i, i + 0.1), "disputed": True, "alt": None} for i in range(6)]
    flags = hallucination_flags(voted, b_words=[])
    assert len(flags) == 1
    assert flags[0]["reason"] == "no_B_support_in_span"


def test_hallucination_flags_short_disputed_run_is_not_flagged():
    voted = [{**_w(f"w{i}", i, i + 0.1), "disputed": True, "alt": None} for i in range(3)]
    assert hallucination_flags(voted, b_words=[]) == []


def test_vote_stage_end_to_end_shape():
    a = [_w("Suffering", 0.0, 0.3), _w("is", 0.3, 0.5), _w("not", 0.5, 0.7),
         _w("a", 0.7, 0.8), _w("fact", 0.8, 1.1)]
    b = [_w("Suffering", 0.0, 0.3), _w("is", 0.3, 0.5), _w("not", 0.5, 0.7),
         _w("a", 0.7, 0.8), _w("fat", 0.8, 1.1)]
    r = vote_stage(a, b)
    assert r["ok"] is True
    assert r["n_voted"] == 5
    assert r["agreement_rate"] == 4 / 5
    assert len(r["voted_words"]) == 5
