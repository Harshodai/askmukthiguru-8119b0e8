"""Unit tests for ingest.verbatim.clips. No models -- t_centres/win_lab are
plain fixtures standing in for a speaker-verify stage result."""

from ingest.verbatim.clips import clips_stage


def _w(word, start, end):
    return {"w": word, "start": start, "end": end}


def test_clips_stage_excludes_host_question_and_labels_speaker():
    words = [
        _w("Suffering", 0.0, 0.3),
        _w("is", 0.3, 0.5),
        _w("not", 0.5, 0.7),
        _w("a", 0.7, 0.8),
        _w("fact.", 0.8, 1.1),
        _w("question", 1.2, 1.6),
        _w("It", 1.7, 1.8),
        _w("is", 1.8, 1.9),
        _w("a", 1.9, 2.0),
        _w("perception.", 2.0, 2.5),
    ]
    t_centres = [0.55, 1.4, 2.25]
    win_lab = ["K", "O", "K"]
    r = clips_stage(words, t_centres, win_lab, "vid1", min_words=3)
    assert len(r["clips"]) == 2
    assert all("question" not in c["verbatim_text"] for c in r["clips"])
    assert r["clips"][0]["speaker"] == "krishnaji"
    assert r["host_leak_count"] == 0
    assert len(r["labelled_words"]) == len(words)


def test_clips_stage_reports_clip_build_stats():
    words = [_w(w, i, i + 0.2) for i, w in enumerate(["Love", "is", "not", "a", "feeling."])]
    t_centres = [i + 0.1 for i in range(len(words))]  # one window per word, all "P"
    win_lab = ["P"] * len(words)
    r = clips_stage(words, t_centres, win_lab, "vid2", min_words=3)
    assert r["stats"]["runs"] == 1
    assert r["stats"]["clips"] == 1
