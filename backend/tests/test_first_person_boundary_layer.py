"""The boundary guard judges verbatim_text, never the restored display layer.

2026-10-05: 568 first_person_v7 clips fail ``tail_no_terminal``. Their punctuated
``display_text`` would pass ~200 of them, but the restorer ends every clip with
a period, so it also "repairs" real mid-sentence cuts (about 1 in 3 sampled). The
next clip in the same video confirms the cuts (e.g. "...being part of" then
"World it is a state ..." 880 ms later). Fix belongs at ingest (sentence-snapped
segmentation), not in a looser serve gate.
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


def test_restored_period_does_not_admit_a_cut_clause():
    # Live v7 clip OWMBvMlGWTA@42.75s: an unfinished "If ..." clause.
    v = "If you are in a suffering state, states of anger, anxiety or sadness, oneness,"
    d = "If you are in a suffering state, states of anger, anxiety or sadness oneness."
    assert not _ok(_clip(v, d))


def test_unpunctuated_verbatim_is_blocked_even_with_clean_display():
    v = "Like a pendulum you keep moving between joy and sorrow you keep moving"
    d = "Like a pendulum, you keep moving between joy and sorrow; you keep moving."
    assert not _ok(_clip(v, d))


def test_whole_sentence_verbatim_passes():
    assert _ok(_clip("Like a pendulum, you keep moving between joy and sorrow."))


def test_hash_is_checked_on_verbatim_not_display():
    v = "Like a pendulum, you keep moving."
    clip = _clip(v, "Like a pendulum you keep moving")
    clip["transcript_hash"] = hashlib.sha256(clip["display_text"].encode()).hexdigest()
    assert not _ok(clip)
