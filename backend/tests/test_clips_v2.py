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
    # k1's last word carries terminal punctuation (as real ASR words do) so this
    # test isolates host-exclusion; the mid-sentence-at-flip cases are covered
    # separately below (test_j/test_k).
    k1 = _teacher_words(12, "K", "a", sentence_every=12)
    host = _words([("question", "O")], start=k1[-1]["end"] + 0.05)
    k2 = _teacher_words(12, "K", "b", start=host[-1]["end"] + 0.05)
    words = k1 + host + k2

    clips, stats = build_clips_from_labelled_words(words, "vid2")

    assert stats["runs"] == 2
    assert len(clips) == 2
    for clip in clips:
        assert "question" not in clip["verbatim_text"]


def test_c_long_unknown_gap_forces_a_split():
    k1 = _teacher_words(12, "K", "a", sentence_every=12)
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
    p = _teacher_words(12, "P", "a", sentence_every=12)
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


def test_j_genuine_flip_mid_sentence_trims_to_last_complete_sentence():
    """Root cause of 'answers end mid-sentence': the natural end of a run
    (reached because a real speaker change follows, not because the transcript
    ran out) must never be served past the last complete sentence. The
    trailing partial sentence is dropped, not served."""
    words = _teacher_words(8, "K", "s", sentence_every=4)  # 2 complete 4-word sentences
    trailing = _teacher_words(3, "K", "t", start=words[-1]["end"] + 0.05)  # incomplete 3rd sentence
    host = _words([("interrupts", "O")], start=trailing[-1]["end"] + 0.05)
    all_words = words + trailing + host

    clips, stats = build_clips_from_labelled_words(all_words, "vid10", min_words=1)

    assert stats["dropped_mid_sentence_at_flip"] == 1
    assert len(clips) == 1
    assert clips[0]["verbatim_text"] == _joined(words)
    for w in trailing:
        assert w["w"] not in clips[0]["verbatim_text"]
    assert "interrupts" not in clips[0]["verbatim_text"]


def test_k_genuine_flip_with_no_complete_sentence_drops_the_whole_run():
    """A run cut off by a genuine flip with zero complete sentences anywhere
    in it has nothing valid to serve -- it must be dropped entirely rather
    than served as a mid-sentence fragment (never trade the host-exclusion /
    no-fragment rule for recall)."""
    words = _teacher_words(12, "K", "a")  # no terminal punctuation anywhere
    host = _words([("question", "O")], start=words[-1]["end"] + 0.05)

    clips, stats = build_clips_from_labelled_words(words + host, "vid11", min_words=1)

    assert stats["dropped_mid_sentence_at_flip"] == 1
    assert clips == []


def test_l_run_ending_at_transcript_end_without_flip_is_kept_whole():
    """The counterpart to test_j/test_k: when a run ends only because the
    transcript does (no genuine flip follows), there is no better boundary to
    fall back to, so the tail is served whole even without terminal
    punctuation -- this is the real, unavoidable "recording just stops"
    case, not a flip cutting off a completable sentence."""
    words = _teacher_words(8, "K", "s", sentence_every=4)
    trailing = _teacher_words(3, "K", "t", start=words[-1]["end"] + 0.05)
    all_words = words + trailing  # nothing follows -- transcript simply ends here

    clips, stats = build_clips_from_labelled_words(all_words, "vid12", min_words=1)

    assert stats["dropped_mid_sentence_at_flip"] == 0
    assert len(clips) == 1
    assert clips[0]["verbatim_text"] == _joined(all_words)


def test_m_repro_served_mid_sentence_quote_is_now_trimmed():
    """Regression for the measured production defect: a served quote ending
    '...and the more suffering we' (no terminal punctuation) because a run was
    cut off at a genuine flip mid-sentence. Reproduces the shape with a real
    sentence, then a genuine flip partway through the next one."""
    specs = [
        ("The", "K"),
        ("more", "K"),
        ("disconnected", "K"),
        ("we", "K"),
        ("are,", "K"),
        ("the", "K"),
        ("more", "K"),
        ("suffering", "K"),
        ("we", "K"),
        ("cause", "K"),
        ("ourselves.", "K"),
        ("And", "K"),
        ("the", "K"),
        ("more", "K"),
        ("suffering", "K"),
        ("we", "K"),
    ]
    words = _words(specs)
    host = _words([("Right,", "O"), ("exactly.", "O")], start=words[-1]["end"] + 0.05)

    clips, stats = build_clips_from_labelled_words(words + host, "vid13", min_words=1)

    assert len(clips) == 1
    assert (
        clips[0]["verbatim_text"]
        == "The more disconnected we are, the more suffering we cause ourselves."
    )
    assert not clips[0]["verbatim_text"].endswith("we")
    assert stats["dropped_mid_sentence_at_flip"] == 1


def test_n_pause_at_conjunction_does_not_split_after_conjunction():
    """L-SENTENCE-SPLIT-CONJUNCTION-1: When a speaker pauses after 'or',
    naively splitting on the pause leaves '...fear or' as a dangling clip.
    The splitter must shift the cut before the conjunction or avoid dangling conjunctions."""
    clause1 = [
        ("We", "K"),
        ("suffer", "K"),
        ("from", "K"),
        ("stress", "K"),
        ("and", "K"),
        ("anxiety", "K"),
        ("and", "K"),
        ("fear", "K"),
    ]
    conj = [("or", "K")]
    clause2 = [
        ("if", "K"),
        ("you", "K"),
        ("are", "K"),
        ("living", "K"),
        ("in", "K"),
        ("a", "K"),
        ("state", "K"),
        ("of", "K"),
        ("suffering.", "K"),
    ]

    w1 = _words(clause1, start=0.0, gap=0.05, dur=0.3)
    w_conj = _words(conj, start=w1[-1]["end"] + 0.05, gap=0.05, dur=0.3)
    # Speaker pauses 0.8s after saying 'or' before continuing clause 2
    w2 = _words(clause2, start=w_conj[-1]["end"] + 0.8, gap=0.05, dur=0.3)
    all_words = w1 + w_conj + w2

    # Force a split between clauses by setting parent_max_s to 4.5s
    clips, stats = build_clips_from_labelled_words(
        all_words, "vid_conj", parent_max_s=4.5, min_words=1
    )

    assert len(clips) >= 2
    # Verify NO clip ends with dangling conjunction 'or'
    for c in clips:
        assert c["verbatim_text"].rstrip(".,;:!?…—–-").split()[-1].lower() not in (
            "or",
            "and",
            "so",
            "but",
            "because",
        )
    # First clip ends with 'fear' (cut shifted before 'or')
    assert clips[0]["verbatim_text"].endswith("fear")
    # Second clip begins with 'or if' (conjunction stays with the subsequent clause)
    assert clips[1]["verbatim_text"].startswith("or if")
