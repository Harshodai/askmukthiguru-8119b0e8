"""Unit tests for ingest.verbatim.speaker_verify.

The embedder is always injected (a plain lambda), so this file never loads
SpeechBrain/ECAPA -- these are pure-logic tests on synthetic embeddings.
"""

import numpy as np

from ingest.verbatim.speaker_verify import (
    cluster_and_name_windows,
    label_words_by_speaker,
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
