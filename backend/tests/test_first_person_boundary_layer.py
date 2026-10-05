"""Boundary guard judges the punctuated display layer only when it is the same words.

2026-10-05: 193 of 568 ``tail_no_terminal`` rejections in first_person_v7 were
whole sentences whose ``verbatim_text`` is unpunctuated ASR. The rest are real
cuts (the next clip continues the sentence) and must stay blocked.
"""

import hashlib

from services.first_person_pipeline import _boundary_layer, _passes_integrity_gate


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


def test_unpunctuated_verbatim_with_punctuated_same_words_display_passes():
    v = "Like a pendulum you keep moving between joy and sorrow you keep moving"
    d = "Like a pendulum, you keep moving between joy and sorrow; you keep moving."
    assert _boundary_layer(_clip(v, d)) == d
    assert _ok(_clip(v, d))


def test_unpunctuated_verbatim_without_display_is_still_blocked():
    assert not _ok(_clip("Like a pendulum you keep moving between joy and sorrow"))


def test_display_with_different_words_is_ignored():
    v = "Like a pendulum you keep moving between joy and sorrow you did not feel being part of"
    d = "Like a pendulum, you keep moving between joy and sorrow. You are whole."
    assert _boundary_layer(_clip(v, d)) == v
    assert not _ok(_clip(v, d))


def test_restored_period_after_a_dangling_word_is_still_a_cut():
    v = "When you look at nature you did not feel being part of"
    d = "When you look at nature, you did not feel being part of."
    assert _boundary_layer(_clip(v, d)) == d
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
