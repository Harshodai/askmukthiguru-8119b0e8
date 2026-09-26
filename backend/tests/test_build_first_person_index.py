"""Tests for scripts/ops/build_first_person_index.py — the writer for the
`first_person_v1` Qdrant collection. All fixtures are synthetic (tmp_path),
no network, no real Qdrant. The channel lookup (yt-dlp) is monkeypatched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.ops import build_first_person_index as bfpi


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _words(text: str) -> list[dict]:
    return [{"w": w} for w in text.split(" ")]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _clip(video_id, verbatim_text, speaker="preethaji", start=1.0, end=2.0, **extra) -> dict:
    return {
        "clip_id": f"{video_id}_c0",
        "video_id": video_id,
        "start": start,
        "end": end,
        "speaker": speaker,
        "speaker_confidence": None,
        "verbatim_text": verbatim_text,
        "display_text": verbatim_text,
        "question_context": None,
        "transcript_hash": _hash(verbatim_text),
        "has_disputed_words": False,
        "parent_id": f"{video_id}_p1",
        **extra,
    }


def _make_video_dirs(tmp_path: Path, name: str, video_id: str, clips: list[dict], transcript_text: str):
    base = tmp_path / name
    _write_json(base / "passages_B" / f"{video_id}.json", clips)
    _write_json(base / "transcripts_B" / f"{video_id}.json", _words(transcript_text))
    _write_json(base / "raw" / f"{video_id}_vote.json", {"ok": True, "agreement_rate": 0.95})
    return base / "passages_B"


def _videos_json(tmp_path: Path, videos: list[dict]) -> Path:
    path = tmp_path / "videos_final.json"
    _write_json(path, {"videos": videos, "substitutions": []})
    return path


@pytest.fixture(autouse=True)
def _no_real_channel_lookup(monkeypatch):
    # Default: nobody should hit yt-dlp/network in a test unless explicitly patched.
    monkeypatch.setattr(bfpi, "lookup_channel_metadata", lambda video_id: ("UNKNOWN", None))


def _build(tmp_path, passages_dirs, videos_json, apply=False):
    return bfpi.build_index(
        passages_dirs=passages_dirs,
        videos_json=videos_json,
        report_dir=tmp_path / "report",
        collection="first_person_v1",
        apply=apply,
    )


def test_good_video_indexes_all_teacher_clips(tmp_path):
    text = "Suffering is not a fact it is only a perception."
    clip = _clip("vidA", "Suffering is not a fact")
    pdir = _make_video_dirs(tmp_path, "src1", "vidA", [clip], text)
    vjson = _videos_json(tmp_path, [{"video_id": "vidA", "duration_s": 100.0}])

    report = _build(tmp_path, [pdir], vjson)

    assert report["videos_quarantined"] == []
    assert report["clips_indexed_total"] == 1
    assert report["clips_per_teacher"] == {"preethaji": 1}


def test_substring_mismatch_quarantines_whole_video(tmp_path):
    text = "Suffering is not a fact it is only a perception."
    bad_clip = _clip("vidB", "Words that never appear in transcript")
    pdir = _make_video_dirs(tmp_path, "src1", "vidB", [bad_clip], text)
    vjson = _videos_json(tmp_path, [{"video_id": "vidB", "duration_s": 100.0}])

    report = _build(tmp_path, [pdir], vjson)

    assert report["clips_indexed_total"] == 0
    reasons = {q["video_id"]: q["reason"] for q in report["videos_quarantined"]}
    assert reasons["vidB"] == "substring_mismatch"


def test_hash_mismatch_quarantines(tmp_path):
    text = "Peace is within you always."
    clip = _clip("vidC", "Peace is within you")
    clip["transcript_hash"] = "0" * 64  # corrupt the hash
    pdir = _make_video_dirs(tmp_path, "src1", "vidC", [clip], text)
    vjson = _videos_json(tmp_path, [{"video_id": "vidC", "duration_s": 100.0}])

    report = _build(tmp_path, [pdir], vjson)

    reasons = {q["video_id"]: q["reason"] for q in report["videos_quarantined"]}
    assert reasons["vidC"] == "hash_mismatch"


def test_end_after_duration_quarantines(tmp_path):
    text = "Peace is within you always."
    clip = _clip("vidD", "Peace is within you", start=95.0, end=120.0)
    pdir = _make_video_dirs(tmp_path, "src1", "vidD", [clip], text)
    vjson = _videos_json(tmp_path, [{"video_id": "vidD", "duration_s": 100.0}])

    report = _build(tmp_path, [pdir], vjson)

    reasons = {q["video_id"]: q["reason"] for q in report["videos_quarantined"]}
    assert reasons["vidD"] == "bad_bounds"


def test_host_clip_is_skipped_not_indexed(tmp_path):
    text = "What is suffering? Suffering is not a fact."
    host_clip = _clip("vidE", "What is suffering?", speaker=None, start=0.0, end=1.0)
    teacher_clip = _clip("vidE", "Suffering is not a fact.", speaker="krishnaji", start=1.5, end=3.0)
    pdir = _make_video_dirs(tmp_path, "src1", "vidE", [host_clip, teacher_clip], text)
    vjson = _videos_json(tmp_path, [{"video_id": "vidE", "duration_s": 100.0}])

    report = _build(tmp_path, [pdir], vjson)

    assert report["clips_indexed_total"] == 1
    assert report["clips_per_teacher"] == {"krishnaji": 1}
    assert report["host_skipped_total"] == 1


def test_first_dir_wins_priority(tmp_path):
    text = "The beautiful state is here now."
    winning_clip = _clip("vidF", "The beautiful state is here")
    losing_clip = _clip("vidF", "This text will never be read")
    pdir_first = _make_video_dirs(tmp_path, "priority1", "vidF", [winning_clip], text)
    pdir_second = _make_video_dirs(tmp_path, "priority2", "vidF", [losing_clip], "This text will never be read.")
    vjson = _videos_json(tmp_path, [{"video_id": "vidF", "duration_s": 100.0}])

    report = _build(tmp_path, [pdir_first, pdir_second], vjson)

    # The losing dir's clip text doesn't exist in the winning dir's transcript,
    # so if priority were reversed or merged, this would quarantine or index wrong text.
    assert report["videos_quarantined"] == []
    assert report["clips_indexed_total"] == 1


def test_uncleared_channel_gives_rights_cleared_false(tmp_path, monkeypatch):
    text = "Love is the answer to everything."
    clip = _clip("vidG", "Love is the answer")
    pdir = _make_video_dirs(tmp_path, "src1", "vidG", [clip], text)
    vjson = _videos_json(tmp_path, [{"video_id": "vidG", "duration_s": 100.0}])

    monkeypatch.setattr(bfpi, "lookup_channel_metadata", lambda video_id: ("Some Random Channel", None))

    report = _build(tmp_path, [pdir], vjson)

    assert report["videos_quarantined"] == []
    assert report["channels"]["Some Random Channel"]["rights_cleared"] is False


def test_cleared_channel_gives_rights_cleared_true(tmp_path, monkeypatch):
    text = "Love is the answer to everything."
    clip = _clip("vidH", "Love is the answer")
    pdir = _make_video_dirs(tmp_path, "src1", "vidH", [clip], text)
    vjson = _videos_json(tmp_path, [{"video_id": "vidH", "duration_s": 100.0}])

    monkeypatch.setattr(bfpi, "lookup_channel_metadata", lambda video_id: ("Ekam", None))

    report = _build(tmp_path, [pdir], vjson)

    assert report["channels"]["Ekam"]["rights_cleared"] is True


def test_dry_run_makes_no_store_calls(tmp_path, monkeypatch):
    text = "Suffering is not a fact it is only a perception."
    clip = _clip("vidI", "Suffering is not a fact")
    pdir = _make_video_dirs(tmp_path, "src1", "vidI", [clip], text)
    vjson = _videos_json(tmp_path, [{"video_id": "vidI", "duration_s": 100.0}])

    called = {"apply": False}

    def _fake_apply(indexable_clips, collection):
        called["apply"] = True
        return len(indexable_clips)

    monkeypatch.setattr(bfpi, "apply_indexable_clips", _fake_apply)

    report = _build(tmp_path, [pdir], vjson, apply=False)

    assert called["apply"] is False
    assert report["applied"] is False


def test_first_person_eligible_always_true_rights_cleared_carried_separately():
    """first_person_eligible is a data-quality flag, never a rights gate — an
    uncleared clip still indexes as eligible; rights_cleared is what a caller
    (the serving route) must check independently."""
    clip = _clip("vidJ", "Some verbatim text", speaker="preethaji")

    store_clip = bfpi.build_store_clip(
        clip,
        video_id="vidJ",
        channel="Uncleared Channel",
        rights_cleared=False,
        layer_sha256="a" * 64,
        duration_ms=5000,
    )

    assert store_clip["first_person_eligible"] is True
    assert store_clip["rights_cleared"] is False
    assert store_clip["channel"] == "Uncleared Channel"


def test_missing_videos_final_duration_falls_back_to_yt_dlp(tmp_path, monkeypatch):
    text = "The beautiful state changes everything for us."
    clip = _clip("vidK", "The beautiful state changes everything", start=1.0, end=5.0)
    pdir = _make_video_dirs(tmp_path, "src1", "vidK", [clip], text)
    # duration_s is null in videos_final.json — the real, measured gap.
    vjson = _videos_json(tmp_path, [{"video_id": "vidK", "duration_s": None}])

    monkeypatch.setattr(bfpi, "lookup_channel_metadata", lambda video_id: ("Ekam", 42.0))

    report = _build(tmp_path, [pdir], vjson)

    assert report["videos_quarantined"] == []
    assert report["clips_indexed_total"] == 1
    assert report["duration_sources"]["vidK"] == "yt_dlp"


def test_duration_unknown_when_both_sources_missing(tmp_path, monkeypatch):
    text = "The beautiful state changes everything for us."
    clip = _clip("vidL", "The beautiful state changes everything", start=1.0, end=5.0)
    pdir = _make_video_dirs(tmp_path, "src1", "vidL", [clip], text)
    vjson = _videos_json(tmp_path, [{"video_id": "vidL", "duration_s": None}])

    monkeypatch.setattr(bfpi, "lookup_channel_metadata", lambda video_id: ("Ekam", None))

    report = _build(tmp_path, [pdir], vjson)

    reasons = {q["video_id"]: q["reason"] for q in report["videos_quarantined"]}
    assert reasons["vidL"] == "duration_unknown"
    assert report["duration_sources"]["vidL"] == "none"


def test_duration_cache_reused_without_requerying_when_source_is_videos_final(tmp_path, monkeypatch):
    """When videos_final.json already has the duration, no yt-dlp call is needed."""
    text = "Peace and joy are our true nature always."
    clip = _clip("vidM", "Peace and joy are our true nature", start=1.0, end=5.0)
    pdir = _make_video_dirs(tmp_path, "src1", "vidM", [clip], text)
    vjson = _videos_json(tmp_path, [{"video_id": "vidM", "duration_s": 100.0}])

    calls = []
    monkeypatch.setattr(
        bfpi,
        "lookup_channel_metadata",
        lambda video_id: (calls.append(video_id) or "Ekam", 999.0),
    )

    report = _build(tmp_path, [pdir], vjson)

    assert report["duration_sources"]["vidM"] == "videos_final"
    # Channel is still looked up exactly once (for rights), duration ignored.
    assert calls == ["vidM"]


def test_identical_parent_child_spans_collapse_and_count_check_passes(tmp_path, monkeypatch):
    """A <=150-word parent and its single child share text and bounds, so they are
    the same UUIDv5 point. The build must collapse them and compare the store count
    against unique points -- the first real apply (2026-09-25) tripped the count
    check with 573 clips vs 333 points."""
    text = "Suffering is not a fact it is only a perception."
    parent = _clip("vidD", "Suffering is not a fact", clip_id="vidD_vidD_p1_0")
    child = _clip("vidD", "Suffering is not a fact", clip_id="vidD_vidD_p1_1")
    pdir = _make_video_dirs(tmp_path, "src1", "vidD", [parent, child], text)
    vjson = _videos_json(tmp_path, [{"video_id": "vidD", "duration_s": 100.0}])
    monkeypatch.setattr(bfpi, "apply_indexable_clips", lambda clips, collection: len({c["transcript_hash"] for c in clips}))

    report = _build(tmp_path, [pdir], vjson, apply=True)

    assert report["duplicates_collapsed"] == 1
    assert report["clips_indexed_total"] == 1
    assert report.get("count_mismatch") in (False, None)


def _write_vote(pdir: Path, video_id: str, agreement) -> None:
    raw = pdir.parent / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    vote = raw / f"{video_id}_vote.json"
    if agreement is None:
        vote.unlink(missing_ok=True)
    else:
        _write_json(vote, {"ok": True, "agreement_rate": agreement})


def test_low_or_unknown_asr_agreement_quarantines_video(tmp_path):
    """A clip's hash proves it matches its own transcript, not the audio. When the
    two ASR systems disagree on most words (pilot: AK435vKMtlo 0.064), the words may
    never have been spoken, so the whole video is held back (fail closed)."""
    text = "Suffering is not a fact it is only a perception."
    vjson_rows = []
    dirs = []
    for vid, agree in (("vidLow", 0.06), ("vidNone", None), ("vidOk", 0.93)):
        pdir = _make_video_dirs(tmp_path, f"src_{vid}", vid, [_clip(vid, "Suffering is not a fact")], text)
        _write_vote(pdir, vid, agree)
        dirs.append(pdir)
        vjson_rows.append({"video_id": vid, "duration_s": 100.0})
    report = _build(tmp_path, dirs, _videos_json(tmp_path, vjson_rows))
    reasons = {q["video_id"]: q["reason"] for q in report["videos_quarantined"]}
    assert reasons["vidLow"].startswith("asr_agreement_low")
    assert reasons["vidNone"] == "asr_agreement_unknown"
    assert "vidOk" not in reasons


def _fake_store_env(monkeypatch, existing_ids):
    from unittest.mock import MagicMock

    import services.embedding_service as es
    import services.first_person_store as fps

    store = MagicMock()
    store.client.scroll.return_value = ([MagicMock(id=i) for i in existing_ids], None)
    store.count.return_value = 0
    monkeypatch.setattr(fps, "FirstPersonStore", lambda collection: store)
    embedder = MagicMock()
    embedder.encode_batch.side_effect = lambda texts: {"dense": [[0.0]] * len(texts), "sparse": [{} for _ in texts]}
    monkeypatch.setattr(es, "EmbeddingService", lambda: embedder)
    return store


def test_apply_deletes_only_stale_point_ids(monkeypatch):
    from services.first_person_store import make_first_person_point_id

    clip = {"verbatim_text": "x", "transcript_hash": "h1", "start_ms": 0, "end_ms": 1000}
    keep = make_first_person_point_id("h1", 0, 1000)
    store = _fake_store_env(monkeypatch, [keep, "stale-id"])
    bfpi.apply_indexable_clips([clip], "first_person_test")
    deleted = store.client.delete.call_args.kwargs["points_selector"].points
    assert deleted == ["stale-id"]


def test_apply_refuses_to_empty_a_collection_on_an_empty_build(monkeypatch):
    store = _fake_store_env(monkeypatch, ["a", "b"])
    with pytest.raises(RuntimeError, match="0 clips"):
        bfpi.apply_indexable_clips([], "first_person_test")
    store.client.delete.assert_not_called()
