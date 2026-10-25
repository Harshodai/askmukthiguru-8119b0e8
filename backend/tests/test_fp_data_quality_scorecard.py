"""Tests for ``scripts.ops.fp_data_quality_scorecard`` (read-only data-quality gate).

Synthetic fixtures pin each check (it must fail on a planted defect and pass on
clean data). One test pins the committed 2026-10-21 v10 export so a change in
the scorecard's measurements, not only in its code, is noticed.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import fp_data_quality_scorecard as sc  # noqa: E402

_EXPORT = (
    _BACKEND.parent / "audits" / "evidence" / "public_release_v10_points_export_2026-10-21.json"
)
_NOW = dt.datetime(2026, 10, 25, tzinfo=dt.UTC)
_TEXT = (
    "When we look closely at how the mind works we notice that suffering begins "
    "when we resist what is happening. If we stay present with it, the resistance softens."
)


def _hex(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _span(i: int, *, video: str = "vid0000000a", text: str = _TEXT, **over) -> dict:
    start = 30_000 + i * 30_000
    row = {
        "record_type": "retrieval_child",
        "schema_version": "fp-context-v1",
        "corpus_version": "fp-context-transcript-v1",
        "source_span_id": _hex(f"span{i}{video}"),
        "video_id": video,
        "guru_id": "krishnaji" if i % 2 else "preethaji",
        "start_ms": start,
        "end_ms": start + 14_000,
        "word_start": i * 40,
        "word_end": i * 40 + 30,
        "speaker_role": "guru",
        "speaker_verified": True,
        "voice_verification_method": "ecapa_voxceleb_centroid_v1",
        "verbatim_text": text,
        "source_transcript_text": text,
        "source_text_hash": hashlib.sha256(text.encode()).hexdigest(),
        "boundary_status": "verified",
        "completeness_status": "complete",
        "asr_engine": "parakeet_mlx",
        "asr_model_version": "parakeet-tdt-0.6b-v3",
        "retrieval_text_version": "fp-retrieval-v1",
        "rights_cleared": True,
        "source_url": f"https://www.youtube.com/watch?v={video}",
    }
    row.update(over)
    return row


def _clean_set(n: int = 60) -> list[dict]:
    # Distinct text per span and spread over many videos so uniqueness and
    # concentration checks pass.
    return [
        _span(i, video=f"vid{i:08d}", text=f"{_TEXT} Variant number {i} of the same teaching.")
        for i in range(n)
    ]


def _by_id(report: dict) -> dict:
    return {c["id"]: c for c in report["checks"]}


def _report(pts: list[dict], **kw) -> dict:
    meta = {"exported_at_utc": "2026-10-24T00:00:00+00:00"}
    return sc.build_report(pts, meta, source="t", now=_NOW, **kw)


def _fix_hash(p: dict) -> dict:
    p["source_text_hash"] = hashlib.sha256(p["verbatim_text"].encode()).hexdigest()
    return p


def test_clean_fixture_passes_every_gating_check() -> None:
    rep = _report(_clean_set())
    failed = [c["id"] for c in rep["checks"] if c["status"] == "FAIL"]
    assert rep["summary"]["verdict"] == "PASS", failed
    assert not rep["summary"]["gating_failures"]


def test_text_hash_mismatch_is_blocker() -> None:
    pts = _clean_set()
    pts[0]["verbatim_text"] += " extra"
    c = _by_id(_report(pts))["text_hash_mismatch"]
    assert c["status"] == "FAIL" and c["count"] == 1 and c["severity"] == "BLOCKER"


def test_speaker_verified_without_method_is_blocker() -> None:
    pts = _clean_set()
    for p in pts[:3]:
        p.pop("voice_verification_method")
    c = _by_id(_report(pts))["speaker_verified_without_method"]
    assert c["status"] == "FAIL" and c["count"] == 3
    # an unverified span with no method is honest, not a defect
    pts2 = _clean_set()
    pts2[0].pop("voice_verification_method")
    pts2[0]["speaker_verified"] = False
    assert _by_id(_report(pts2))["speaker_verified_without_method"]["status"] == "PASS"


def test_duplicate_identity_and_text() -> None:
    pts = _clean_set()
    pts[1]["source_span_id"] = pts[0]["source_span_id"]
    pts[3] = copy.deepcopy(pts[2]) | {"source_span_id": _hex("other")}
    rep = _by_id(_report(pts))
    assert rep["duplicate_identity"]["status"] == "FAIL"
    assert rep["duplicate_text_rate"]["count"] == 2


def test_invalid_values_and_missing_fields() -> None:
    pts = _clean_set()
    pts[0]["start_ms"] = "100"
    pts[1]["source_text_hash"] = "xyz"
    pts[2]["speaker_role"] = "narrator"
    pts[3]["rights_cleared"] = None
    rep = _by_id(_report(pts))
    assert rep["invalid_values"]["count"] == 3
    assert rep["missing_required_fields"]["count"] == 1


def test_time_window_duration_and_speech_rate() -> None:
    pts = _clean_set()
    pts[0]["end_ms"] = pts[0]["start_ms"]  # zero width
    pts[1]["end_ms"] = pts[1]["start_ms"] + 590_000  # 590 s "clip"
    rep = _by_id(_report(pts))
    assert rep["invalid_time_window"]["count"] == 1
    assert rep["duration_out_of_band_rate"]["count"] == 1
    assert rep["speech_rate_out_of_band_rate"]["count"] == 1  # same long span: 0.06 w/s


def test_chain_must_close_and_be_symmetric() -> None:
    pts = _clean_set(4)
    pts[0]["next_span_id"] = pts[1]["source_span_id"]
    pts[1]["previous_span_id"] = pts[0]["source_span_id"]
    assert _by_id(_report(pts))["broken_chain"]["status"] == "PASS"
    pts[1]["previous_span_id"] = _hex("nobody")
    c = _by_id(_report(pts))["broken_chain"]
    # the dangling link, and the first span whose next no longer points back
    assert c["status"] == "FAIL" and c["count"] == 2


def test_containment_within_one_video() -> None:
    pts = _clean_set(10)
    pts[1].update(video_id=pts[0]["video_id"], start_ms=pts[0]["start_ms"] + 2_000)
    pts[1]["end_ms"] = pts[0]["end_ms"] - 2_000
    assert _by_id(_report(pts))["contained_in_other_span_rate"]["count"] == 1


def test_boundary_defect_and_label_disagreement() -> None:
    pts = _clean_set()
    bad = _fix_hash(
        pts[0] | {"verbatim_text": "and then it moved on to the next idea about the mind"}
    )
    bad["source_transcript_text"] = bad["verbatim_text"]
    pts[0] = bad
    rep = _by_id(_report(pts))
    assert rep["boundary_defect_rate"]["count"] == 1
    assert rep["boundary_label_disagreement_rate"]["count"] == 1  # labelled verified+complete


def test_text_edit_vs_source_is_measured_not_silently_accepted() -> None:
    pts = _clean_set()
    edited = _fix_hash(
        pts[0] | {"verbatim_text": pts[0]["verbatim_text"].replace("suffering", "pain")}
    )
    pts[0] = edited
    pts[1] = _fix_hash(pts[1] | {"verbatim_text": pts[1]["verbatim_text"].replace("mind", "heart")})
    rep = _by_id(_report(pts))
    assert rep["text_edited_vs_source_rate"]["count"] == 2
    # punctuation/case-only differences are not edits
    pts2 = _clean_set()
    pts2[0]["source_transcript_text"] = pts2[0]["verbatim_text"].upper()
    assert _by_id(_report(pts2))["text_edited_vs_source_rate"]["count"] == 0


def test_lineage_and_freshness() -> None:
    pts = _clean_set()
    pts[0]["asr_model_version"] = "other"
    rep = _by_id(_report(pts))
    assert rep["lineage_variants"]["measured"] == 2
    stale = sc.build_report(_clean_set(), {}, source="t", now=_NOW)
    assert _by_id(stale)["export_age_days"]["status"] == "FAIL"


def test_concentration_and_openings() -> None:
    pts = _clean_set(40)
    for p in pts[:10]:
        p["video_id"] = "hubvideo001"
        p["start_ms"] = 1_000  # also opening clips
    rep = _by_id(_report(pts))
    assert rep["max_video_share"]["status"] == "FAIL"
    assert rep["opening_clip_rate"]["count"] == 10


def test_drift_between_exports() -> None:
    old = _clean_set(5)
    new = copy.deepcopy(old)[:4] + [_span(99, video="vid00000099")]
    new[0] = _fix_hash(new[0] | {"verbatim_text": "A different text for the very same span id."})
    d = _report(new, baseline=old)["drift"]
    assert (d["added"], d["removed"], d["text_changed_same_id"]) == (1, 1, 1)


def test_loader_accepts_envelope_list_and_jsonl(tmp_path: Path) -> None:
    pts = _clean_set(3)
    env = tmp_path / "env.json"
    env.write_text(json.dumps({"result": {"points": [{"id": "a", "payload": p} for p in pts]}}))
    lst = tmp_path / "list.json"
    lst.write_text(json.dumps(pts))
    jl = tmp_path / "rows.jsonl"
    jl.write_text("\n".join(json.dumps(p) for p in pts))
    for path in (env, lst, jl):
        assert len(sc.load_points(path)[0]) == 3


def test_loader_ignores_non_child_rows_and_fails_closed(tmp_path: Path) -> None:
    pts = [_span(0), {"record_type": "parent_context", "source_span_id": "p"}]
    f = tmp_path / "x.json"
    f.write_text(json.dumps(pts))
    children, meta = sc.load_points(f)
    assert len(children) == 1 and meta["rows_non_child"] == 1
    empty = tmp_path / "e.json"
    empty.write_text("[]")
    with pytest.raises(sc.InputError):
        sc.load_points(empty)
    with pytest.raises(sc.InputError):
        sc.load_points(tmp_path / "missing.json")


def test_cli_exit_codes_and_read_only(tmp_path: Path) -> None:
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(
        json.dumps(
            {
                "exported_at_utc": dt.datetime.now(dt.UTC).isoformat(),
                "result": {"points": _clean_set()},
            }
        )
    )
    broken = _clean_set()
    broken[0]["verbatim_text"] += " tampered"
    bad.write_text(json.dumps(broken))
    before = good.read_bytes()
    out = tmp_path / "r.json"
    assert sc.main(["--points", str(good), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["read_only"] is True
    assert sc.main(["--points", str(bad)]) == 1
    assert sc.main(["--points", str(tmp_path / "nope.json")]) == 2
    assert good.read_bytes() == before


def test_redact_text_removes_teacher_text_from_report(tmp_path: Path) -> None:
    pts = _clean_set()
    pts[0]["verbatim_text"] += " tampered"
    f, out = tmp_path / "p.json", tmp_path / "r.json"
    f.write_text(json.dumps(pts))
    assert sc.main(["--points", str(f), "--out", str(out), "--redact-text"]) == 1
    assert "look closely" not in out.read_text()
    assert sc.main(["--points", str(f), "--out", str(out)]) == 1
    assert "look closely" in out.read_text()


def test_thresholds_override(tmp_path: Path) -> None:
    pts = _clean_set()
    pts[0]["verbatim_text"] += " extra"
    assert (
        _by_id(_report(pts, thresholds={"text_hash_mismatch": 5}))["text_hash_mismatch"]["status"]
        == "PASS"
    )


def test_strict_clean_rate_counts_only_spans_with_no_span_level_defect() -> None:
    pts = _clean_set(20)
    assert _by_id(_report(pts))["strict_clean_rate"]["count"] == 20
    pts[0]["verbatim_text"] += " x"  # hash mismatch
    pts[1]["end_ms"] = pts[1]["start_ms"] + 590_000  # duration + speech rate
    pts[2].pop("voice_verification_method")
    c = _by_id(_report(pts))["strict_clean_rate"]
    assert c["count"] == 17 and c["status"] == "PASS" and c["target_kind"] == "at_least"
    # opening-of-video and unverified labels are risks, not defects
    pts2 = _clean_set(20)
    pts2[0]["start_ms"] = 500
    pts2[0]["end_ms"] = 14_500
    pts2[1]["boundary_status"] = "uncertain"
    assert _by_id(_report(pts2))["strict_clean_rate"]["count"] == 20


def test_tier_rows_are_mapped_without_inventing_labels(tmp_path: Path) -> None:
    row = {
        "tier": "local_review_candidate",
        "source_span_id": _hex("t1"),
        "video_id": "vid0000000a",
        "guru_id": "krishnaji",
        "text": _TEXT,
        "source_text_hash": hashlib.sha256(_TEXT.encode()).hexdigest(),
        "audio_start_ms": 10_000,
        "audio_end_ms": 24_000,
        "word_start": 1,
        "word_end": 30,
        "speaker_verdict": "refused",
        "reconstruction_exact": True,
        "rights_status": "confirmed_channel_owner",
        "previous_span_id": _hex("outside"),
    }
    f = tmp_path / "tier.jsonl"
    f.write_text(json.dumps(row))
    (p,), _ = sc.load_points(f)
    assert p["verbatim_text"] == _TEXT and p["start_ms"] == 10_000
    assert p["speaker_verified"] is False and p["voice_verification_method"] is None
    assert p["boundary_status"] == "uncertain"  # unknown stays unknown
    assert "previous_span_id" not in p  # subset rows carry no chain


@pytest.mark.skipif(not _EXPORT.exists(), reason="committed v10 export not present")
def test_committed_v10_export_baseline_is_pinned() -> None:
    """Pins the measurements on the 2026-10-21 export (2,737 children). If these
    move, either the scorecard changed or the evidence file did: look before
    updating the numbers."""
    pts, meta = sc.load_points(_EXPORT)
    c = _by_id(sc.build_report(pts, meta, source=_EXPORT.name, now=_NOW))
    assert len(pts) == 2737
    # integrity and structure hold
    for cid in (
        "missing_required_fields",
        "invalid_values",
        "text_hash_mismatch",
        "duplicate_identity",
        "broken_chain",
        "invalid_time_window",
    ):
        assert c[cid]["count"] == 0, cid
    # measured defects (not targets)
    assert c["speaker_verified_without_method"]["count"] == 732
    assert c["asr_clean_not_idempotent"]["count"] == 37
    # The 37 are text stored UNCLEANED, not a cleaner defect: a second pass of
    # the cleaner changes nothing on any of the 2,737 spans.
    assert c["asr_cleaner_two_pass_unstable"]["count"] == 0
    assert c["boundary_defect_rate"]["count"] == 670
    assert c["duration_out_of_band_rate"]["count"] == 723
    assert c["speech_rate_out_of_band_rate"]["count"] == 99
    assert c["text_edited_vs_source_rate"]["count"] == 1339
    assert c["opening_clip_rate"]["count"] == 243
    assert c["max_video_share"]["count"] == 85
    assert c["strict_clean_rate"]["count"] == 1087


_TIER = (
    _BACKEND.parent
    / "audits"
    / "evidence"
    / "public_release_phase4_tier_local_review_candidate_2026-10-22.jsonl"
)


@pytest.mark.skipif(not _TIER.exists(), reason="committed tier candidate not present")
def test_committed_local_review_candidate_baseline_is_pinned() -> None:
    pts, meta = sc.load_points(_TIER)
    c = _by_id(sc.build_report(pts, meta, source=_TIER.name, now=_NOW))
    assert len(pts) == 1529
    for cid in ("text_hash_mismatch", "speaker_verified_without_method", "duplicate_identity"):
        assert c[cid]["count"] == 0, cid
    assert c["boundary_defect_rate"]["count"] == 587
    assert c["duration_out_of_band_rate"]["count"] == 265
    assert c["strict_clean_rate"]["count"] == 708
