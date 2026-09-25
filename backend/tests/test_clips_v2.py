"""Unit tests for the v2 speaker-run clip builder (build_clips_from_labelled_words).

Replaces the offline pilot's run_clips.py logic: teacher runs absorb short
'?' flicker gaps, cut only at sentence ends (falling back to the largest
pause), and a <=200-word parent is emitted alone (no duplicate child).
"""

import hashlib

from services.speaker_diarization import build_clips_from_labelled_words


def _words(specs, start=0.0, gap=0.05, dur=0.3):
    """Build a word list from (text, spk) pairs with synthetic, strictly
    increasing timestamps -- gap seconds between words, dur seconds each."""
    out = []
    t = start
    for text, spk in specs:
        out.append({"w": text, "start": round(t, 3), "end": round(t + dur, 3), "spk": spk})
        t += dur + gap
    return out


def _teacher_words(n, spk, prefix, start=0.0, gap=0.05, dur=0.3, sentence_every=None):
    """n filler words labelled spk, optionally ending every `sentence_every`th
    word with a period so sentence-cut tests have real cut points."""
    specs = []
    for i in range(n):
        text = f"{prefix}{i}"
        if sentence_every and (i + 1) % sentence_every == 0:
            text += "."
        specs.append((text, spk))
    return _words(specs, start=start, gap=gap, dur=dur)


def _joined(words):
    return " ".join(w["w"] for w in words)


def test_a_short_unknown_gap_is_absorbed_into_one_clip():
    k1 = _teacher_words(6, "K", "a")
    gap = _words([("um", "?"), ("uh", "?")], start=k1[-1]["end"] + 0.05)
    k2 = _teacher_words(6, "K", "b", start=gap[-1]["end"] + 0.05)
    words = k1 + gap + k2

    clips, stats = build_clips_from_labelled_words(words, "vid1")

    assert stats["runs"] == 1
    assert stats["merged_unknown_gaps"] == 1
    assert len(clips) == 1
    assert clips[0]["verbatim_text"] == _joined(words)


def test_b_host_word_splits_run_and_is_never_included():
    k1 = _teacher_words(12, "K", "a")
    host = _words([("question", "O")], start=k1[-1]["end"] + 0.05)
    k2 = _teacher_words(12, "K", "b", start=host[-1]["end"] + 0.05)
    words = k1 + host + k2

    clips, stats = build_clips_from_labelled_words(words, "vid2")

    assert stats["runs"] == 2
    assert len(clips) == 2
    for clip in clips:
        assert "question" not in clip["verbatim_text"]


def test_c_long_unknown_gap_forces_a_split():
    k1 = _teacher_words(12, "K", "a")
    gap = _teacher_words(10, "?", "u", start=k1[-1]["end"] + 0.05)
    k2 = _teacher_words(12, "K", "b", start=gap[-1]["end"] + 0.05)
    words = k1 + gap + k2

    clips, stats = build_clips_from_labelled_words(words, "vid3", max_unknown_words=8)

    assert stats["runs"] == 2
    assert stats["merged_unknown_gaps"] == 0
    assert len(clips) == 2


def test_d_cut_lands_after_sentence_end_not_mid_sentence():
    # 5 short "sentences" of 4 words each, period on the 4th word of each.
    words = _teacher_words(20, "K", "s", sentence_every=4)
    # Force a split partway through: total duration ~= 20*0.35 = 7s; cap at 3.5s
    # so the cut must land inside the run, at a sentence boundary.
    clips, stats = build_clips_from_labelled_words(words, "vid4", parent_max_s=3.5, min_words=1)

    assert stats["cut_at_sentence"] >= 1
    assert len(clips) >= 2
    # every clip except conceivably the last must end on '.', '?' or '!'
    for clip in clips[:-1]:
        last_word = clip["verbatim_text"].split()[-1]
        assert last_word[-1] in ".?!", clip["verbatim_text"]


def test_e_short_parent_yields_exactly_one_clip_no_child():
    words = _teacher_words(150, "P", "w")
    clips, stats = build_clips_from_labelled_words(words, "vid5")

    assert len(clips) == 1
    assert clips[0]["verbatim_text"] == _joined(words)


def test_f_isolated_short_run_is_dropped_and_counted():
    words = _teacher_words(5, "K", "a")
    clips, stats = build_clips_from_labelled_words(words, "vid6", min_words=12)

    assert clips == []
    assert stats["dropped_short"] == 1
    assert stats["runs"] == 1


def test_g_verbatim_text_is_substring_of_joined_layer_and_hash_matches():
    words = _teacher_words(30, "P", "w")
    clips, stats = build_clips_from_labelled_words(words, "vid7")
    joined_layer = _joined(words)

    assert clips
    for clip in clips:
        assert clip["verbatim_text"] in joined_layer
        assert clip["transcript_hash"] == hashlib.sha256(clip["verbatim_text"].encode()).hexdigest()


def test_h_adjacent_different_teachers_are_separate_clips():
    p = _teacher_words(12, "P", "a")
    k = _teacher_words(12, "K", "b", start=p[-1]["end"] + 0.05)
    words = p + k

    clips, stats = build_clips_from_labelled_words(words, "vid8")

    assert stats["runs"] == 2
    assert len(clips) == 2
    speakers = {c["speaker"] for c in clips}
    assert speakers == {"preethaji", "krishnaji"}


def test_i_start_pad_is_floored_at_zero():
    words = _teacher_words(12, "K", "a", start=0.05)
    clips, stats = build_clips_from_labelled_words(words, "vid9", pad_s=0.2)

    assert clips[0]["start"] == 0.0


def test_self_check_runs():
    from services.speaker_diarization import _clips_v2_self_check

    _clips_v2_self_check()
