"""Clip boundary integrity (CLAUDE.md first-person invariants 10/11)."""

import pytest

from ingest.verbatim.boundaries import boundary_defects, snap_to_sentences


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Suffering is not a fact.", []),
        ("This is who you are.", []),
        ("and then you let go of", ["head_lowercase", "head_conjunction", "tail_no_terminal", "tail_dangling_word"]),
        ("is agitated before the event,", ["head_lowercase", "tail_no_terminal"]),
        ("...and it ends.", ["head_orphan_punctuation", "head_conjunction"]),
        ("So approach your yoga gently.", ["head_conjunction"]),
    ],
)
def test_boundary_defects(text, expected):
    assert boundary_defects(text.split()) == expected


def test_empty_clip_is_a_defect():
    assert boundary_defects([]) == ["empty"]


def test_snap_trims_both_severed_edges():
    toks = "was agitated. You see the truth. Then it goes and".split()
    s, e = snap_to_sentences(toks, 0, len(toks), min_words=3)
    assert toks[s:e] == "You see the truth.".split()
    assert boundary_defects(toks[s:e]) == []


def test_snap_keeps_an_already_clean_clip_whole():
    toks = "You see the truth. It is here.".split()
    assert snap_to_sentences(toks, 0, len(toks), min_words=3) == (0, len(toks))


def test_snap_quarantines_when_too_little_survives():
    toks = "was agitated. You see. Then it goes and".split()
    assert snap_to_sentences(toks, 0, len(toks), min_words=5) is None


def test_snap_quarantines_a_span_with_no_sentence_boundary():
    toks = "and then not able to handle it you move into".split()
    assert snap_to_sentences(toks, 0, len(toks), min_words=1) is None


def test_snap_uses_a_parallel_display_layer_for_unpunctuated_asr():
    verbatim = "it hurts you see the truth it is here and".split()
    display = "it hurts. You see the truth. It is here and".split()
    assert len(verbatim) == len(display)
    s, e = snap_to_sentences(display, 0, len(display), min_words=3)
    assert verbatim[s:e] == "you see the truth".split()


def test_snap_rejects_bad_span():
    with pytest.raises(ValueError):
        snap_to_sentences(["A."], 1, 1)
