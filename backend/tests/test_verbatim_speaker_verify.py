"""Unit tests for ingest.verbatim.speaker_verify.

The embedder is always injected (a plain lambda), so this file never loads
SpeechBrain/ECAPA -- these are pure-logic tests on synthetic embeddings.
"""

import numpy as np

from ingest.verbatim.speaker_verify import (
    cluster_and_name_windows,
    label_words_by_speaker,
    relabel_turn_start_prefixes,
    verify_speakers,
)

_VP = {"preethaji": np.array([1.0, 0.0]), "krishnaji": np.array([0.0, 1.0])}
_THR = {"P": 0.5, "K": 0.5}


def test_cluster_and_name_windows_empty_embeddings():
    r = cluster_and_name_windows(np.array([]), np.array([]).reshape(0, 2), _VP, _THR)
    assert r["n_windows"] == 0
    assert r["time_share"]["teacher_P"] == 0.0


def test_cluster_and_name_windows_five_identical_preethaji_windows():
    # >= MIN_CLUSTER_WINDOWS (5) in speaker_attribution.py, else the cluster
    # abstains as "?" regardless of how well it matches a voiceprint.
    t = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    e = np.array([[1.0, 0.0]] * 5)
    r = cluster_and_name_windows(t, e, _VP, _THR)
    assert r["n_windows"] == 5
    assert set(r["win_lab"]) == {"P"}
    assert r["time_share"]["teacher_P"] == 1.0


def test_verify_speakers_wraps_injected_embedder_and_reports_timing():
    fake = lambda wav, hop=1.0: (np.array([0.0] * 5), np.array([[1.0, 0.0]] * 5))  # noqa: E731
    r = verify_speakers("fake.wav", _VP, _THR, embedder=fake)
    assert r["ok"] is True
    assert "embed_time_s" in r


def test_verify_speakers_fails_closed_on_embedder_error():
    def boom(wav, hop=1.0):
        raise RuntimeError("no such wav")

    r = verify_speakers("missing.wav", _VP, _THR, embedder=boom)
    assert r == {"ok": False, "error": "no such wav"}


def test_label_words_by_speaker_snaps_to_nearest_window():
    words = [{"w": "hi", "start": 0.5, "end": 1.0}, {"w": "there", "start": 20.0, "end": 20.5}]
    labelled = label_words_by_speaker(words, [1.0, 21.0], ["P", "K"])
    assert labelled[0]["spk"] == "P"
    assert labelled[1]["spk"] == "K"


def test_label_words_by_speaker_beyond_snap_radius_is_unknown():
    words = [{"w": "far", "start": 100.0, "end": 100.5}]
    labelled = label_words_by_speaker(words, [1.0], ["P"], snap_radius_s=1.5)
    assert labelled[0]["spk"] == "?"


def test_label_words_by_speaker_no_windows_is_all_unknown():
    words = [{"w": "hi", "start": 0.5, "end": 1.0}]
    assert label_words_by_speaker(words, [], [])[0]["spk"] == "?"


# --- Task S1: Turn-Start Speaker Prefix Recovery Tests ---


def test_relabel_turn_start_prefixes_positive_case():
    """Positive case: 'It[O] is[O] beyond[P] attitudes[P] and[P] beliefs[P].' -> 'It[P] is[P] beyond[P] attitudes[P] and[P] beliefs[P].'"""
    words = [
        {"w": "It", "start": 0.0, "end": 0.2, "spk": "O"},
        {"w": "is", "start": 0.2, "end": 0.4, "spk": "O"},
        {"w": "beyond", "start": 0.4, "end": 0.7, "spk": "P"},
        {"w": "attitudes", "start": 0.7, "end": 1.1, "spk": "P"},
        {"w": "and", "start": 1.1, "end": 1.3, "spk": "P"},
        {"w": "beliefs.", "start": 1.3, "end": 1.8, "spk": "P"},
    ]
    relabelled = relabel_turn_start_prefixes(words)
    assert [w["spk"] for w in relabelled] == ["P", "P", "P", "P", "P", "P"]


def test_relabel_turn_start_prefixes_negative_host_sentence():
    """Negative case: genuine host sentence 'What[O] is[O] meditation[O]?' followed by teacher sentence -> remains 'O'."""
    words = [
        {"w": "What", "start": 0.0, "end": 0.3, "spk": "O"},
        {"w": "is", "start": 0.3, "end": 0.5, "spk": "O"},
        {"w": "meditation?", "start": 0.5, "end": 1.0, "spk": "O"},
        {"w": "Meditation", "start": 1.2, "end": 1.6, "spk": "K"},
        {"w": "is", "start": 1.6, "end": 1.8, "spk": "K"},
        {"w": "an", "start": 1.8, "end": 2.0, "spk": "K"},
        {"w": "awakened", "start": 2.0, "end": 2.4, "spk": "K"},
        {"w": "state.", "start": 2.4, "end": 2.8, "spk": "K"},
    ]
    relabelled = relabel_turn_start_prefixes(words)
    assert [w["spk"] for w in relabelled[:3]] == ["O", "O", "O"]
    assert [w["spk"] for w in relabelled[3:]] == ["K", "K", "K", "K", "K"]


def test_relabel_turn_start_prefixes_mixed_ambiguous_untouched():
    """Mixed/ambiguous sentence -> remains untouched."""
    # Subcase A: host word in remainder
    words_a = [
        {"w": "It", "start": 0.0, "end": 0.2, "spk": "O"},
        {"w": "is", "start": 0.2, "end": 0.4, "spk": "O"},
        {"w": "beyond", "start": 0.4, "end": 0.7, "spk": "P"},
        {"w": "attitudes", "start": 0.7, "end": 1.1, "spk": "O"},
        {"w": "and", "start": 1.1, "end": 1.3, "spk": "P"},
        {"w": "beliefs.", "start": 1.3, "end": 1.8, "spk": "P"},
    ]
    assert [w["spk"] for w in relabel_turn_start_prefixes(words_a)] == [
        "O",
        "O",
        "P",
        "O",
        "P",
        "P",
    ]

    # Subcase B: mixed teachers (P and K) in remainder
    words_b = [
        {"w": "It", "start": 0.0, "end": 0.2, "spk": "O"},
        {"w": "is", "start": 0.2, "end": 0.4, "spk": "O"},
        {"w": "beyond", "start": 0.4, "end": 0.7, "spk": "P"},
        {"w": "attitudes", "start": 0.7, "end": 1.1, "spk": "K"},
        {"w": "and", "start": 1.1, "end": 1.3, "spk": "P"},
        {"w": "beliefs.", "start": 1.3, "end": 1.8, "spk": "P"},
    ]
    assert [w["spk"] for w in relabel_turn_start_prefixes(words_b)] == [
        "O",
        "O",
        "P",
        "K",
        "P",
        "P",
    ]

    # Subcase C: unknown word (?) in remainder
    words_c = [
        {"w": "It", "start": 0.0, "end": 0.2, "spk": "O"},
        {"w": "is", "start": 0.2, "end": 0.4, "spk": "O"},
        {"w": "beyond", "start": 0.4, "end": 0.7, "spk": "P"},
        {"w": "attitudes", "start": 0.7, "end": 1.1, "spk": "?"},
        {"w": "and", "start": 1.1, "end": 1.3, "spk": "P"},
        {"w": "beliefs.", "start": 1.3, "end": 1.8, "spk": "P"},
    ]
    assert [w["spk"] for w in relabel_turn_start_prefixes(words_c)] == [
        "O",
        "O",
        "P",
        "?",
        "P",
        "P",
    ]


def test_relabel_turn_start_prefixes_bounded_prefix_length():
    """Bounded prefix length (> 6 words does not relabel; <= 6 words relabels)."""
    # 7 words of 'O' followed by 3 teacher words -> must NOT relabel (> 6 boundary)
    words_7 = [
        {"w": "one", "start": 0.0, "end": 0.2, "spk": "O"},
        {"w": "two", "start": 0.2, "end": 0.4, "spk": "O"},
        {"w": "three", "start": 0.4, "end": 0.6, "spk": "O"},
        {"w": "four", "start": 0.6, "end": 0.8, "spk": "O"},
        {"w": "five", "start": 0.8, "end": 1.0, "spk": "O"},
        {"w": "six", "start": 1.0, "end": 1.2, "spk": "O"},
        {"w": "seven", "start": 1.2, "end": 1.4, "spk": "O"},
        {"w": "eight", "start": 1.4, "end": 1.6, "spk": "P"},
        {"w": "nine", "start": 1.6, "end": 1.8, "spk": "P"},
        {"w": "ten.", "start": 1.8, "end": 2.0, "spk": "P"},
    ]
    relabelled_7 = relabel_turn_start_prefixes(words_7)
    assert [w["spk"] for w in relabelled_7[:7]] == ["O"] * 7
    assert [w["spk"] for w in relabelled_7[7:]] == ["P", "P", "P"]

    # Exactly 6 words of 'O' followed by 3 teacher words -> DOES relabel (<= 6)
    words_6 = words_7[1:]
    relabelled_6 = relabel_turn_start_prefixes(words_6)
    assert [w["spk"] for w in relabelled_6] == ["P"] * 9


def test_relabel_turn_start_prefixes_unknown_prefix_recovered():
    """Unknown (?) prefix is recovered when followed by uniform teacher remainder."""
    words = [
        {"w": "The", "start": 0.0, "end": 0.2, "spk": "?"},
        {"w": "sacred", "start": 0.2, "end": 0.5, "spk": "K"},
        {"w": "heart", "start": 0.5, "end": 0.8, "spk": "K"},
        {"w": "glows.", "start": 0.8, "end": 1.2, "spk": "K"},
    ]
    relabelled = relabel_turn_start_prefixes(words)
    assert [w["spk"] for w in relabelled] == ["K", "K", "K", "K"]


def test_relabel_turn_start_prefixes_explicit_sentence_boundaries():
    """Explicit sentence boundaries guide prefix recovery even without terminal punctuation."""
    words = [
        {"w": "It", "start": 1.0, "end": 1.2, "spk": "O"},
        {"w": "is", "start": 1.2, "end": 1.4, "spk": "O"},
        {"w": "beyond", "start": 1.4, "end": 1.7, "spk": "K"},
        {"w": "attitudes", "start": 1.7, "end": 2.0, "spk": "K"},
        {"w": "here", "start": 2.0, "end": 2.3, "spk": "K"},
    ]
    boundaries = [(0.5, 3.0)]
    relabelled = relabel_turn_start_prefixes(words, sentence_boundaries=boundaries)
    assert [w["spk"] for w in relabelled] == ["K", "K", "K", "K", "K"]


def test_relabel_turn_start_prefixes_not_absorbed_after_teacher_terminal():
    """Ask-5 host-exclusion gate: a single host interjection right after a
    terminal-punctuated teacher sentence must NEVER be absorbed (the
    test_clips_v2::test_b host-never-in-a-clip invariant). The previous turn
    was complete, so the O-label there is genuine host speech, not a
    mislabelled teacher head."""
    words = [
        {"w": "beliefs.", "start": 0.0, "end": 0.4, "spk": "K"},
        {"w": "question", "start": 0.5, "end": 0.8, "spk": "O"},
        {"w": "exactly", "start": 0.9, "end": 1.2, "spk": "K"},
        {"w": "here", "start": 1.2, "end": 1.5, "spk": "K"},
        {"w": "now.", "start": 1.5, "end": 1.9, "spk": "K"},
    ]
    relabelled = relabel_turn_start_prefixes(words)
    assert relabelled[1]["spk"] == "O", "host interjection after teacher terminal was absorbed"
    # ...but recovery after HOST terminal speech stays open (prime mislabel case).
    host_then_teacher = [
        {"w": "meditation?", "start": 0.0, "end": 0.5, "spk": "O"},
        {"w": "It", "start": 0.7, "end": 0.9, "spk": "O"},
        {"w": "is", "start": 0.9, "end": 1.1, "spk": "O"},
        {"w": "beyond", "start": 1.1, "end": 1.4, "spk": "K"},
        {"w": "all", "start": 1.4, "end": 1.6, "spk": "K"},
        {"w": "belief.", "start": 1.6, "end": 2.0, "spk": "K"},
    ]
    recovered = relabel_turn_start_prefixes(host_then_teacher)
    assert [w["spk"] for w in recovered[1:3]] == ["K", "K"], "recovery after host terminal blocked"


def test_label_words_by_speaker_end_to_end_prefix_recovery():
    """Verify label_words_by_speaker automatically applies turn-start recovery."""
    words = [
        {"w": "It", "start": 0.0, "end": 0.3},
        {"w": "is", "start": 0.3, "end": 0.6},
        {"w": "beyond", "start": 0.9, "end": 1.2},
        {"w": "attitudes", "start": 1.2, "end": 1.5},
        {"w": "and", "start": 1.5, "end": 1.8},
        {"w": "beliefs.", "start": 1.8, "end": 2.1},
    ]
    t_centres = [0.2, 1.5]
    win_lab = ["O", "P"]
    labelled = label_words_by_speaker(words, t_centres, win_lab)
    assert [w["spk"] for w in labelled] == ["P", "P", "P", "P", "P", "P"]


def test_apply_transition_dilation_guardband():
    from ingest.verbatim.speaker_verify import apply_transition_dilation_guardband

    words = [
        {"w": "Hello", "start": 0.0, "end": 0.4, "spk": "O"},
        {"w": "World", "start": 0.45, "end": 0.8, "spk": "O"},
        # Transition at ~0.85
        {"w": "Peace", "start": 0.9, "end": 1.3, "spk": "P"},
        {"w": "comes", "start": 1.35, "end": 1.8, "spk": "P"},
    ]
    guarded = apply_transition_dilation_guardband(words, dilation_s=0.30)
    assert guarded[1]["near_speaker_transition"] is True
    assert guarded[2]["near_speaker_transition"] is True
    assert guarded[3].get("near_speaker_transition") is not True


def test_guardband_never_downgrades_a_host_word_to_unknown():
    """A host "O" word at a turn edge must stay host, or clips absorb it."""
    from ingest.verbatim.speaker_verify import apply_transition_dilation_guardband

    words = [
        {"w": "fact.", "start": 0.8, "end": 1.1, "spk": "K"},
        {"w": "question", "start": 1.2, "end": 1.6, "spk": "O"},
        {"w": "It", "start": 1.7, "end": 1.8, "spk": "K"},
    ]
    guarded = apply_transition_dilation_guardband(words, dilation_s=0.30)
    assert guarded[1]["spk"] == "O"
    assert guarded[1]["guardband_dilated"] is True


def test_check_clip_transition_guardband():
    from ingest.verbatim.speaker_verify import check_clip_transition_guardband

    transitions = [10.0, 25.5]
    # Clip starting too close to 10.0 (e.g. 10.1 within 0.30s)
    assert check_clip_transition_guardband(10.1, 15.0, transitions, dilation_s=0.30) is True
    # Clip ending too close to 25.5 (e.g. 25.4 within 0.30s)
    assert check_clip_transition_guardband(20.0, 25.4, transitions, dilation_s=0.30) is True
    # Clip safely inside boundaries
    assert check_clip_transition_guardband(12.0, 20.0, transitions, dilation_s=0.30) is False


if __name__ == "__main__":
    # ponytail: one runnable self-check — run pytest on this module.
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
