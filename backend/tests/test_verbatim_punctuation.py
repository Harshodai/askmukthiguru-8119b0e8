"""Unit tests for ingest.verbatim.punctuation, ported from the pilot's
test_run_punct.py (~/mukthiguru_attribution_data/pilot50_2026-09-25/). No
model load -- every test injects a fake Punctuator."""

from ingest.verbatim.punctuation import chunk, diff_norm_word_sequences, punctuate_stage
from ingest.verbatim.vote import norm_word


def test_real_word_change_is_rejected():
    verbatim = [norm_word(w) for w in ["I", "was", "gonna", "go"]]
    display = [norm_word(w) for w in ["I", "was", "going", "to", "go"]]
    diffs = diff_norm_word_sequences(verbatim, display)
    assert diffs, "a genuine word change ('gonna' -> 'going to') must be flagged"


def test_hyphen_apostrophe_number_tokens_pass():
    verbatim_raw = ["well-being", "don't", "3", "O'Brien's"]
    display_raw = ["Well-Being,", "Don't", "3.", "O'Brien's"]
    verbatim = [norm_word(w) for w in verbatim_raw]
    display = [norm_word(w) for w in display_raw]
    assert diff_norm_word_sequences(verbatim, display) == []


def test_pure_punctuation_token_excluded_both_sides():
    voted_words = ["love", "%", "and", "connection"]
    norm_all = [norm_word(w) for w in voted_words]
    model_input = [w for w in norm_all if w]
    assert model_input == ["love", "and", "connection"]


def test_windows_merge_without_duplication():
    words = [f"word{i}" for i in range(450)]  # spans 3 chunks of size 200
    display_words = []
    for ch in chunk(words, 200):
        sentence = " ".join(ch) + "."
        display_words.extend(sentence.split())
    verbatim_norm = [norm_word(w) for w in words]
    display_norm = [norm_word(w) for w in display_words]
    assert diff_norm_word_sequences(verbatim_norm, display_norm) == []


def test_the_actual_bug_pre_punctuated_input_would_have_failed():
    """Reproduces the root cause directly: feeding already-punctuated verbatim
    text into a model that treats an embedded '.' as a sentence boundary."""
    verbatim_words = ["to", "heal.", "it", "is", "not"]

    def fake_buggy_infer(text):
        parts = text.split(". ")
        return [parts[0] + "."] + [". " + p for p in parts[1:]]

    display_words = " ".join(fake_buggy_infer(" ".join(verbatim_words))).split()
    verbatim_norm = [norm_word(w) for w in verbatim_words]
    display_norm = [norm_word(w) for w in display_words]
    diffs = diff_norm_word_sequences(verbatim_norm, display_norm)
    assert diffs, "pre-punctuated input must reproduce a spurious insert diff (guards the regression)"


class _FakePunctuator:
    def infer(self, texts):
        return [[" ".join(w.capitalize() for w in texts[0].split()) + "."]]


class _BuggyPunctuator:
    """Stands in for the real model's historical pre-fix bug: given already-
    punctuated input it mis-segments on the embedded '.'."""

    def infer(self, texts):
        parts = texts[0].split(". ")
        return [[parts[0] + "."] + [". " + p for p in parts[1:]]]


def test_punctuate_stage_end_to_end_with_fake_model():
    voted = [{"w": "love"}, {"w": "and"}, {"w": "connection"}]
    r = punctuate_stage(voted, model=_FakePunctuator())
    assert r["ok"] is True
    assert r["zero_change_assert_passed"] is True
    assert r["diff_count"] == 0


def test_punctuate_stage_feeds_normalised_input_so_buggy_model_cannot_reproduce_the_bug():
    # voted words already carry punctuation ("heal.") -- the fix strips it
    # before the model ever sees it, so even a model that reproduces the
    # historical bug given raw punctuated input stays clean here.
    voted = [{"w": "to"}, {"w": "heal."}, {"w": "it"}, {"w": "is"}, {"w": "not"}]
    r = punctuate_stage(voted, model=_BuggyPunctuator())
    assert r["zero_change_assert_passed"] is True, r


def test_punctuate_stage_empty_input():
    assert punctuate_stage([], model=_FakePunctuator()) == {"ok": False, "reason": "no_voted_words"}
