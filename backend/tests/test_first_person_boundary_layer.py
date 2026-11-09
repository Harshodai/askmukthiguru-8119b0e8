"""Boundary guard judges ``verbatim_text`` only, never the display layer.

2026-10-05: an earlier change let a same-words ``display_text`` pass the guard.
It was reverted: the punctuation restorer ends every clip with a period, so it
"repairs" real mid-sentence cuts (~1 in 3 sampled display-only passes were
cuts). These tests pin the verbatim-only behaviour.

L-FP-INTEGRITY-OVERBLOCK-1 (2026-10-11): ``tail_no_terminal`` was removed from
_SERVE_BLOCKING_BOUNDARY_DEFECTS, so a clip whose sole defect is a missing
terminal is served now; head defects and tail_dangling_word still block.
"""

import hashlib

import pytest

from ingest.verbatim.boundaries import TERMINAL_ASCII, boundary_defects, terminal_tokens
from ingest.verbatim.boundary_evidence import derive_boundary_evidence
from services.first_person_pipeline import _passes_integrity_gate


@pytest.fixture(autouse=True)
def _synthetic_sources_are_registered(monkeypatch):
    """Synthetic unit fixtures model licensed clips without live register files."""
    monkeypatch.setattr(
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
    )


def _clip(verbatim: str, display: str | None = None) -> dict:
    return {
        "verbatim_text": verbatim,
        "display_text": display,
        "transcript_hash": hashlib.sha256(verbatim.encode("utf-8")).hexdigest(),
        "speaker": "Sri Preethaji",
        "point_id": "p",
        "video_id": "vid1",
        "source_url": "https://www.youtube.com/watch?v=vid1",
        "is_verbatim": True,
        "first_person_eligible": True,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
    }


def _ok(clip: dict) -> bool:
    return _passes_integrity_gate(clip, boundary_guard_enabled=True)


def test_nonterminal_tail_alone_no_longer_blocks():
    # Live v7 clip OWMBvMlGWTA@42.75s: an unfinished "If ..." clause.
    # L-FP-INTEGRITY-OVERBLOCK-1: tail_no_terminal no longer blocks (v7 has
    # 25% non-terminal ASR cuts; hard-blocking caused 100% abstention).
    # Verbatim-only judging is unchanged — display_text still cannot rescue.
    v = "If you are in a suffering state, states of anger, anxiety or sadness, oneness,"
    d = "If you are in a suffering state, states of anger, anxiety or sadness oneness."
    assert _ok(_clip(v, d))


def test_nonterminal_verbatim_with_punctuated_display_is_served():
    # L-FP-INTEGRITY-OVERBLOCK-1: sole defect is tail_no_terminal, now served.
    v = "Like a pendulum you keep moving between joy and sorrow you keep moving"
    d = "Like a pendulum, you keep moving between joy and sorrow; you keep moving."
    assert _ok(_clip(v, d))


def test_nonterminal_verbatim_without_display_is_served():
    # L-FP-INTEGRITY-OVERBLOCK-1: sole defect is tail_no_terminal, now served.
    assert _ok(_clip("Like a pendulum you keep moving between joy and sorrow"))


def test_display_with_different_words_is_ignored():
    v = "Like a pendulum you keep moving between joy and sorrow you did not feel being part of"
    d = "Like a pendulum, you keep moving between joy and sorrow. You are whole."
    assert not _ok(_clip(v, d))


def test_restored_period_after_a_dangling_word_is_still_a_cut():
    v = "When you look at nature you did not feel being part of"
    d = "When you look at nature, you did not feel being part of."
    assert not _ok(_clip(v, d))


def test_truncated_display_layer_is_served():
    # L-FP-INTEGRITY-OVERBLOCK-1: head_lowercase is not a blocking defect and
    # tail_no_terminal no longer blocks, so this clip is served.
    v = "two things must happen in your consciousness the first one is you need to experience"
    d = "Two things must happen in your consciousness: the first one is you need to experience"
    assert _ok(_clip(v, d))


def test_hash_is_still_checked_on_verbatim_not_display():
    v = "Like a pendulum you keep moving"
    clip = _clip(v, "Like a pendulum, you keep moving.")
    clip["transcript_hash"] = hashlib.sha256(clip["display_text"].encode()).hexdigest()
    assert not _ok(clip)


# --- Terminal vocabulary and the derived boundary record -------------------
# The danda pair ("।" U+0964, "॥" U+0965) terminates Indic sentences. It never
# occurs in English text, so the default vocabulary stays ASCII-only while the
# module-level TERMINAL still accepts both.


def test_danda_terminated_sentence_is_clean():
    assert boundary_defects("सत्यं वद\u0964".split()) == []
    assert boundary_defects(["रामः", "गच्छति", "\u0965"]) == []


def test_default_vocabulary_is_ascii_only_but_terminal_accepts_both():
    assert terminal_tokens() == TERMINAL_ASCII
    assert terminal_tokens("en") == TERMINAL_ASCII
    assert "\u0964" in terminal_tokens("hi")


def test_sentence_without_terminal_is_a_defect():
    assert "tail_no_terminal" in boundary_defects("You are awareness".split())
    assert "tail_no_terminal" in boundary_defects("सत्यं वद".split())


def _timings(n: int) -> list[tuple[float, float]]:
    return [(float(i), float(i) + 0.5) for i in range(n)]


def test_no_eof_promotion_through_derived_evidence():
    # The last word carries no terminal: the derived record must NOT call the
    # span complete just because it sits at the end of the word list.
    words = "You are awareness and you are".split()
    ev = derive_boundary_evidence(words, _timings(len(words)), 0, len(words))
    assert ev.terminal_evidence is None
    assert ev.status == "uncertain"
    assert "tail_no_terminal" in ev.defect_codes


def test_danda_terminated_derived_span_is_complete():
    words = "रामः गच्छति सत्यं वद\u0964".split()
    ev = derive_boundary_evidence(words, _timings(len(words)), 0, len(words))
    assert ev.status == "complete"
    assert ev.terminal_evidence == "वद\u0964"
