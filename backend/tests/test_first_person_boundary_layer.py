"""Boundary guard judges ``verbatim_text`` only, never the display layer.

2026-10-05: an earlier change let a same-words ``display_text`` pass the guard.
It was reverted: the punctuation restorer ends every clip with a period, so it
"repairs" real mid-sentence cuts (~1 in 3 sampled display-only passes were
cuts). These tests pin the verbatim-only behaviour.
"""

import hashlib

from services.first_person_pipeline import _passes_integrity_gate


def _clip(verbatim: str, display: str | None = None) -> dict:
    return {
        "verbatim_text": verbatim,
        "display_text": display,
        "transcript_hash": hashlib.sha256(verbatim.encode("utf-8")).hexdigest(),
        "speaker": "Sri Preethaji",
        "point_id": "p",
    }


def _ok(clip: dict) -> bool:
    return _passes_integrity_gate(clip, boundary_guard_enabled=True)


def test_punctuated_display_does_not_rescue_an_unpunctuated_verbatim_cut():
    v = "Like a pendulum you keep moving between joy and sorrow you keep moving"
    d = "Like a pendulum, you keep moving between joy and sorrow; you keep moving."
    assert not _ok(_clip(v, d))


def test_unpunctuated_verbatim_without_display_is_still_blocked():
    assert not _ok(_clip("Like a pendulum you keep moving between joy and sorrow"))


def test_display_with_different_words_is_ignored():
    v = "Like a pendulum you keep moving between joy and sorrow you did not feel being part of"
    d = "Like a pendulum, you keep moving between joy and sorrow. You are whole."
    assert not _ok(_clip(v, d))


def test_restored_period_after_a_dangling_word_is_still_a_cut():
    v = "When you look at nature you did not feel being part of"
    d = "When you look at nature, you did not feel being part of."
    assert not _ok(_clip(v, d))


def test_truncated_display_layer_is_blocked():
    v = "two things must happen in your consciousness the first one is you need to experience"
    d = "Two things must happen in your consciousness: the first one is you need to experience"
    assert not _ok(_clip(v, d))


def test_hash_is_still_checked_on_verbatim_not_display():
    v = "Like a pendulum you keep moving"
    clip = _clip(v, "Like a pendulum, you keep moving.")
    clip["transcript_hash"] = hashlib.sha256(clip["display_text"].encode()).hexdigest()
    assert not _ok(clip)


def test_restored_period_does_not_admit_a_cut_clause():
    # Live first_person_v7 clip OWMBvMlGWTA@42.75s (Mac 2026-10-06): an unfinished
    # "If ..." clause whose restored display layer ends with a period.
    v = "If you are in a suffering state, states of anger, anxiety or sadness, oneness,"
    d = "If you are in a suffering state, states of anger, anxiety or sadness oneness."
    assert not _ok(_clip(v, d))
