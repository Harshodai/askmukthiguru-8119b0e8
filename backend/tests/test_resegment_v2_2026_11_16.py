"""resegment_v2: word-timed re-cut keeps the serving contract (SourceSpan/ParentUnit/ids/hashes)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
import resegment_v2 as r2  # noqa: E402

SENTS = [
    "Anger is a signal that your inner state needs care and attention right now.",
    "When you pause and breathe you can see what the anger is protecting within you today.",
    "The practice is simple, you return to your breath again and again with kindness.",
    "Over weeks this changes how you meet every difficult moment in your daily life.",
    "Let us understand this.",
]


def _words(host_at: int | None = None) -> list[dict]:
    out, t, i = [], 1000, 0
    for n, sent in enumerate(SENTS):
        for w in sent.split():
            spk = "O" if n == host_at else "K"
            out.append({"i": i, "w": w, "s": t, "e": t + 300, "spk": spk, "al": True})
            t += 350
            i += 1
        t += 400
    return out


V10 = [
    {
        "guru_id": "krishnaji",
        "video_id": "vid",
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "caption_status": "auto",
        "source_url": "https://www.youtube.com/watch?v=vid",
        "asr_engine": "x",
        "asr_model_version": "y",
        "start_ms": 0,
        "end_ms": 1,
        "speaker_verified": False,
    }
]


def _build(words):
    res = r2.build_video("vid", {"words": words}, V10, [], art_sha="0" * 64)
    parents = r2.assemble(res["runs"], {})
    return res, parents


def test_clips_validate_as_serving_models_and_are_unverified():
    res, parents = _build(_words())
    assert res["clips"], "expected at least one clip"
    v = r2.validate_models(res["clips"], parents)
    assert (
        v["children_invalid"] == 0
        and v["parents_invalid"] == 0
        and v["speaker_write_violations"] == 0
    )
    for c in res["clips"]:
        assert c["speaker_verified"] is False and c["voice_verification_method"] is None
        assert c["transcript_hash"] == c["source_text_hash"] == r2.v1._sha(c["verbatim_text"])
        assert "inv4_point_id" not in c  # SourceSpan is extra=forbid; id goes to the sidecar JSONL


def test_ids_chain_and_no_overlap():
    res, parents = _build(_words())
    from services.first_person_context_store import point_id_for_record

    clips = res["clips"]
    for a, b in zip(clips, clips[1:]):
        assert a["end_ms"] <= b["start_ms"]
        assert (
            a["next_span_id"] == b["source_span_id"]
            and b["previous_span_id"] == a["source_span_id"]
        )
    pid, inv4 = r2.point_id_pair(clips[0])
    assert pid == point_id_for_record(clips[0]["source_span_id"]) and pid != inv4
    assert parents[0]["ordered_source_span_ids"] == [c["source_span_id"] for c in clips]


def test_host_sentence_breaks_parent_and_is_not_in_any_clip():
    res, parents = _build(_words(host_at=1))
    text = " ".join(c["verbatim_text"] for c in res["clips"])
    assert "protecting within you" not in text


def test_short_noise_run_between_same_teacher_is_absorbed():
    w = _words()
    w[8]["spk"] = "?"
    lab, absorbed = r2.smooth_labels(w, {"K"})
    assert absorbed == 1 and set(lab) == {"K"}


def test_promissory_tail_is_not_a_clip_end():
    res, _ = _build(_words())
    assert all(
        not c["verbatim_text"].rstrip(".").endswith("Let us understand this") for c in res["clips"]
    )


def test_apply_refuses_protected_and_unapproved():
    args = SimpleNamespace(
        snapshot_confirmed=True,
        approved_by="x",
        target_collection="first_person_v10",
        source_collection="first_person_v10",
    )
    with pytest.raises(SystemExit):
        r2.v1.check_apply_guards(args)
    args.snapshot_confirmed = False
    args.target_collection = "first_person_v12_shadow"
    with pytest.raises(SystemExit):
        r2.v1.check_apply_guards(args)


def test_apply_decision_blocks_unverified_unless_waived():
    m = {
        "seconds": {"p95": 50, "max": 90},
        "pct_outside_8_60s": 1,
        "pct_contained": 0,
        "duplicate_text_clips": 0,
        "under_15_words": 0,
        "standalone_gate_pass_pct": 90,
    }
    card = {
        "v2_recut_only": m,
        "v10_recut_videos": {"standalone_gate_pass_pct": 67},
        "validation": {"children_invalid": 0, "parents_invalid": 0},
        "verified_share_pct": {"v2_recut_only": 0.0, "v10": 99.2},
    }
    assert r2.apply_decision(card, False)["apply_ok"] is False
    assert r2.apply_decision(card, True)["apply_ok"] is True
