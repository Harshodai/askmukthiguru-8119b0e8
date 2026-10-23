"""Index-time completeness stage of scripts/ops/build_first_person_index.py:
extend a fragment to a complete thought with same-teacher words only, drop what
cannot be repaired, and dedupe contained clips. Synthetic fixtures, no network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.ops import build_first_person_index as bfpi


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _words(text: str, labels: str | None = None, step: float = 1.0) -> list[dict]:
    """One transcript word per token, ``step`` seconds apart; ``labels`` one char per word."""
    toks = text.split()
    labels = labels or "P" * len(toks)
    assert len(labels) == len(toks)
    return [
        {"w": w, "start": i * step, "end": i * step + step * 0.9, "spk": lab}
        for i, (w, lab) in enumerate(zip(toks, labels))
    ]


def _clip(words: list[dict], a: int, b: int, speaker: str = "preethaji") -> dict:
    text = " ".join(w["w"] for w in words[a:b])
    return {
        "video_id": "vid",
        "start": words[a]["start"],
        "end": words[b - 1]["end"],
        "speaker": speaker,
        "verbatim_text": text,
        "display_text": text,
        "transcript_hash": _sha(text),
        "parent_id": "vid_p1",
    }


_BACK = "Peace is your nature. Because you are love, you are free."


def _assert_exact(words: list[dict], clip: dict, original: str) -> None:
    full = " ".join(w["w"] for w in words)
    assert clip["verbatim_text"] in full
    assert original in clip["verbatim_text"]  # only whole sentences were added
    assert clip["transcript_hash"] == _sha(clip["verbatim_text"])


def test_orphan_opener_extends_back_to_same_teacher_sentence():
    words = _words(_BACK)
    clip = _clip(words, 4, len(words))  # "Because you are love, you are free."
    out, reason = bfpi.complete_clip(clip, words, None)
    assert reason is None and out["thought_extended"] is True
    assert out["verbatim_text"] == _BACK
    assert out["start"] == 0.0
    _assert_exact(words, out, clip["verbatim_text"])


def test_cut_tail_extends_forward():
    words = _words("Suffering is only a perception, not a fact of life.")
    clip = _clip(words, 0, 5)  # ends on ","
    out, reason = bfpi.complete_clip(clip, words, None)
    assert reason is None
    assert out["verbatim_text"].endswith("life.")
    _assert_exact(words, out, clip["verbatim_text"])


def test_refuses_to_extend_across_host_word():
    words = _words(_BACK, labels="OOOO" + "P" * 7)  # previous sentence is the host's
    out, reason = bfpi.complete_clip(_clip(words, 4, len(words)), words, None)
    assert out is None and reason == "incomplete:orphan_opener"


def test_refuses_to_extend_across_unknown_word():
    words = _words("Suffering is only a perception, not a fact of life.", labels="PPPPP?PPPP")
    out, reason = bfpi.complete_clip(_clip(words, 0, 5), words, None)
    assert out is None and reason == "incomplete:ends_mid_sentence"


def test_respects_duration_cap():
    words = _words(_BACK, step=10.0)
    out, reason = bfpi.complete_clip(_clip(words, 4, len(words)), words, None, max_s=50.0)
    assert out is None and reason == "incomplete:orphan_opener:over_50s"


def test_health_claim_is_never_extended():
    words = _words("This practice will cure you, my friend.")
    out, reason = bfpi.complete_clip(_clip(words, 0, 5), words, None)
    assert out is None and reason == "incomplete:health_claim"


def test_complete_clip_passes_unchanged():
    words = _words("Peace is your nature and it is always here.")
    clip = _clip(words, 0, len(words))
    out, reason = bfpi.complete_clip(clip, words, None)
    assert reason is None and out is clip


def test_missing_speaker_labels_means_no_extension():
    words = [{k: v for k, v in w.items() if k != "spk"} for w in _words(_BACK)]
    out, reason = bfpi.complete_clip(_clip(words, 4, len(words)), words, None)
    assert out is None and reason == "incomplete:orphan_opener"


def test_extended_clip_store_hash_matches_stored_text():
    words = _words(_BACK)
    out, _ = bfpi.complete_clip(_clip(words, 4, len(words)), words, None)
    store = bfpi.build_store_clip(out, "vid", "chan", True, "layer", 60_000)
    assert store["transcript_hash"] == _sha(store["verbatim_text"])
    assert store["verbatim_text"] in " ".join(w["w"] for w in words)


def _sc(start_ms: int, end_ms: int, text: str) -> dict:
    return {"video_id": "vid", "start_ms": start_ms, "end_ms": end_ms, "verbatim_text": text}


def test_containment_dedupe_keeps_parent_and_drops_duplicate_text():
    parent = _sc(0, 10_000, "parent")
    child = _sc(2_000, 5_000, "child")
    dup = _sc(20_000, 25_000, "parent")
    other_video = {**_sc(2_000, 5_000, "child"), "video_id": "vid2"}
    kept, contained, dupes = bfpi.dedupe_contained([child, parent, dup, other_video])
    assert parent in kept and other_video in kept and child not in kept
    assert (contained, dupes) == (1, 1)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@pytest.fixture
def two_video_corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(bfpi, "lookup_channel_metadata", lambda v: ("UNKNOWN", None))
    words = _words(_BACK)
    videos = []
    for vid in ("vidA", "vidB"):
        clip = {**_clip(words, 4, len(words)), "video_id": vid}
        _write(tmp_path / "passages_B" / f"{vid}.json", [clip])
        _write(tmp_path / "transcripts_B" / f"{vid}.json", words)
        _write(tmp_path / "raw" / f"{vid}_vote.json", {"ok": True, "agreement_rate": 0.95})
        videos.append({"video_id": vid, "duration_s": 100.0})
    _write(tmp_path / "videos.json", {"videos": videos, "substitutions": []})
    return tmp_path


def test_only_videos_and_complete_thoughts_in_build(two_video_corpus):
    clips: list[dict] = []
    report = bfpi.build_index(
        passages_dirs=[two_video_corpus / "passages_B"],
        videos_json=two_video_corpus / "videos.json",
        report_dir=two_video_corpus / "report",
        collection="first_person_test",
        min_clip_duration_s=0.0,
        complete_thoughts=True,
        only_videos={"vidA"},
        clips_out=clips,
    )
    assert report["videos_discovered"] == 1 and report["only_videos"] == ["vidA"]
    assert report["clips_extended"] == 1 and report["clips_dropped_incomplete"] == 0
    assert report["standalone_pass_share"] == 1.0
    assert [c["video_id"] for c in clips] == ["vidA"]
    assert clips[0]["verbatim_text"] == _BACK


def test_does_not_stop_on_lowercase_fragment_left_by_stray_full_stop():
    # ASR put a full stop after "forgive." so "yourself." looks like a sentence start.
    words = _words("Life challenges us. We forgive. yourself. But forgiveness frees you.")
    clip = _clip(words, 6, len(words))  # "But forgiveness frees you."
    out, reason = bfpi.complete_clip(clip, words, None)
    assert reason is None
    assert not out["verbatim_text"].startswith("yourself.")
    _assert_exact(words, out, clip["verbatim_text"])


def test_containment_keeps_verified_child_under_unverified_parent():
    parent = _sc(0, 10_000, "parent")
    child = {**_sc(2_000, 5_000, "child"), "speaker_verified": True}
    kept, contained, _ = bfpi.dedupe_contained([parent, child])
    assert child in kept and parent in kept and contained == 0
    verified_parent = {**parent, "speaker_verified": True}
    kept, contained, _ = bfpi.dedupe_contained([verified_parent, child])
    assert kept == [verified_parent] and contained == 1


def test_extended_orphan_opener_yes_comma_extends_back():
    text = "Are you seeking freedom from suffering? Yes, this practice brings freedom."
    words = _words(text)
    clip = _clip(words, 6, len(words))  # "Yes, this practice brings freedom."
    out, reason = bfpi.complete_clip(clip, words, None)
    assert reason is None and out["thought_extended"] is True
    assert out["verbatim_text"] == text
    _assert_exact(words, out, clip["verbatim_text"])


def test_extended_orphan_opener_demonstrative_copula_extends_back():
    for opener in ("These are", "This is", "Those were", "That was"):
        text = f"Anxiety and anger destroy peace. {opener} states of inner suffering."
        words = _words(text)
        clip = _clip(words, 5, len(words))  # opener + "states of inner suffering."
        out, reason = bfpi.complete_clip(clip, words, None)
        assert reason is None and out["thought_extended"] is True
        assert out["verbatim_text"] == text
        _assert_exact(words, out, clip["verbatim_text"])


def test_so_opener_is_allowed_as_complete():
    # E5: "So" is permitted — "So both Preethaji and I..." is a valid complete speech opener
    text = "So both Preethaji and I travel across the world and meet people."
    assert bfpi.completeness_problem(text) is None


def test_complete_thoughts_respects_120s_default_cap():
    # 11 tokens at step=12.0s = 130.8s span, which exceeds the 120.0s complete thoughts cap
    words = _words(_BACK, step=12.0)
    clip = _clip(words, 4, len(words))  # "Because you are love, you are free."
    out, reason = bfpi.complete_clip(clip, words, None)
    assert out is None
    assert reason == "incomplete:orphan_opener:over_120s"


# ---------------------------------------------------------------------------
# E5 passage assembly: a repair that overshoots the cap keeps the sentences that
# fit instead of discarding the whole teaching (the live `over_120s` drop bucket).
# ---------------------------------------------------------------------------

_LONG_HEAD = "You suffer a great deal because you cling to what is passing and you resist what is here."  # 18 words
_LONG_MID = "Because you resist the present moment, the pain continues and it grows stronger."  # 13
_LONG_TAIL = "Let go of resistance and you will see that peace is already your nature."  # 14


def _assert_fitted(words: list[dict], out: dict, max_s: float) -> None:
    full = " ".join(w["w"] for w in words)
    assert out["verbatim_text"] in full  # stays an exact transcript substring
    assert out["transcript_hash"] == _sha(out["verbatim_text"])
    assert out["end"] - out["start"] <= max_s


def test_over_cap_orphan_repair_keeps_the_sentences_that_fit():
    """Growing back to the antecedent overshoots the cap -> keep head + clip sentences.

    Old behaviour dropped all 45 words. The repair is the teacher's own speech, still an
    exact substring, and it now fits the cap, so pruning the trailing sentence is strictly
    better than serving nothing.
    """
    text = f"{_LONG_HEAD} {_LONG_MID} {_LONG_TAIL}"
    words = _words(text)
    head_words = len(_LONG_HEAD.split())
    clip = _clip(words, head_words, len(words))  # starts on the orphan opener "Because"

    out, reason = bfpi.complete_clip(clip, words, None, max_s=32.0)

    assert reason is None
    assert out["verbatim_text"] == f"{_LONG_HEAD} {_LONG_MID}"
    assert _LONG_TAIL not in out["verbatim_text"]  # the pruned sentence really was there
    assert out["start"] == words[0]["start"] and out["end"] == words[30]["end"]
    assert out["thought_extended"] is True
    _assert_fitted(words, out, 32.0)


def test_over_cap_keeps_nothing_when_only_the_grown_scaffold_fits():
    """If the only fitting sentence is the one we grew back over, drop -- never serve the
    scaffold as if it were the teaching."""
    words = _words(f"{_LONG_HEAD} {_LONG_MID}")
    head_words = len(_LONG_HEAD.split())
    clip = _clip(words, head_words, len(words))  # the orphan-opener sentence alone

    out, reason = bfpi.complete_clip(clip, words, None, max_s=20.0)

    assert out is None
    assert reason == "incomplete:orphan_opener:over_20s"


def test_over_cap_cut_tail_repair_keeps_the_completed_tail():
    """Forward growth (cut tail) overshoots -> keep the completed sentence, drop the head."""
    text = (
        "Peace is your nature. "
        "Suffering is only a perception, and it is never a fact of your whole life."
    )
    words = _words(text)
    clip = _clip(words, 0, 9)  # ends on "perception," -> ends_mid_sentence
    assert bfpi.completeness_problem(clip["verbatim_text"]) == "ends_mid_sentence"

    out, reason = bfpi.complete_clip(clip, words, None, max_s=16.0)

    assert reason is None
    assert (
        out["verbatim_text"]
        == "Suffering is only a perception, and it is never a fact of your whole life."
    )
    assert "Peace is your nature." not in out["verbatim_text"]
    assert out["start"] == words[4]["start"]
    assert out["thought_extended"] is True
    _assert_fitted(words, out, 16.0)


def test_over_cap_fitted_clip_is_not_offered_when_too_thin_to_serve():
    """A remainder below the serve-time word floor is dropped at INDEX, not handed to a
    serve gate that would reject it anyway."""
    text = f"Peace is your nature. Because you resist, it grows. {_LONG_TAIL}"
    words = _words(text)
    clip = _clip(words, 4, len(words))  # orphan opener, 19 words

    # max_s=10 fits "Peace is your nature. Because you resist, it grows." (9 words) -- which
    # overlaps the clip, so the scaffold guard passes and ONLY the word floor can reject it.
    out, reason = bfpi.complete_clip(clip, words, None, max_s=10.0)

    assert out is None and reason == "incomplete:orphan_opener:over_10s"


# ---------------------------------------------------------------------------
# Already-standalone clips over the cap: this is the bucket serve refuses with
# "%.0fs exceeds the %.0fs cap" -- the largest reject bucket in the live funnel.
# ---------------------------------------------------------------------------

_SA = "Peace is your nature and it is always here with you."  # 11 words, stands alone


def test_standalone_over_cap_clip_is_trimmed_to_the_sentences_that_fit():
    """Nothing capped standalone clips before: they were stored too long, then refused on
    serve. Cut to a sentence-aligned prefix that fits, flagged thought_trimmed."""
    text = f"{_SA} {_LONG_HEAD} {_LONG_TAIL}"
    words = _words(text)
    clip = _clip(words, 0, len(words))  # stands alone; 42.9s at step=1.0

    out, reason = bfpi.complete_clip(clip, words, None, max_s=32.0)

    assert reason is None
    assert out["thought_trimmed"] is True
    assert out["verbatim_text"] == f"{_SA} {_LONG_HEAD}"
    assert _LONG_TAIL not in out["verbatim_text"]
    assert out["end"] - out["start"] <= 32.0
    _assert_fitted(words, out, 32.0)


def test_standalone_over_cap_clip_is_kept_unchanged_when_it_cannot_be_trimmed():
    """A single long sentence has no sentence boundary to cut on. Keep the clip exactly as
    before -- never drop a clip that serve's cap was already guarding (strictly additive)."""
    one_sentence = (
        "You suffer a great deal because you cling to what is passing and you resist what "
        "is here and you keep repeating the same old pattern without ever noticing it at all."
    )
    words = _words(one_sentence)
    clip = _clip(words, 0, len(words))

    out, reason = bfpi.complete_clip(clip, words, None, max_s=20.0)

    assert out is clip and reason is None
    assert out["end"] - out["start"] > 20.0  # still long; serve's cap is the guard


def test_standalone_clip_within_the_cap_is_untouched():
    words = _words(f"{_SA} {_LONG_HEAD}")
    clip = _clip(words, 0, len(words))
    out, reason = bfpi.complete_clip(clip, words, None, max_s=120.0)
    assert out is clip and reason is None
    assert "thought_trimmed" not in out
