"""Focused tests for ``scripts.ops.build_fp_corpus_tiers`` and
``scripts.ops.build_fp_speaker_conflict_review``.

The corpus tiers are what make the first-person populations governable:

* ``local_review_candidate`` — exact reconstruction + a verified Phase-2
  speaker verdict + a confirmed rights entry. The only servable tier.
* ``review_required`` — the 45 speaker-label conflicts, rights-pending spans
  and any span whose acoustic evidence did not pass.
* ``variant_candidate`` — transcript/text variants. Never served by default.
* ``unlocatable_quarantine`` — spans that could not be located in the
  authoritative word-timed artifact.

The conflict review package turns each contradictory speaker label into a
reviewable row and must never relabel anything on its own.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]
_REPO_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import build_fp_corpus_tiers as tiers  # noqa: E402
from scripts.ops import build_fp_speaker_conflict_review as conflicts  # noqa: E402


def _candidate_row(span_id: str, *, guru: str = "krishnaji", video: str = "vid-a") -> dict:
    return {
        "source_span_id": span_id,
        "video_id": video,
        "source_asset_id": video,
        "guru_id": guru,
        "reconstructed_text": "Meditation is a practice of awareness.",
        "source_text_hash": "h" * 64,
        "transcript_hash": "t" * 64,
        "archived_audio_sha256": "a" * 64,
        "archived_audio_path": f"/audio/{video}.wav",
        "audio_start_ms": 1000,
        "audio_end_ms": 5000,
        "word_start": 0,
        "word_end": 10,
        "corpus_version": "fp-context-transcript-v2",
        "normalization_version": "fp-norm-unicode-v1",
        "coordinate_space_version": "fp-coords-v1",
        "reconstruction_tier": "exact",
        "reconstruction_exact": True,
    }


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return path


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _verdict(span_id: str, reason: str = "verified") -> dict:
    return {
        "source_span_id": span_id,
        "video_id": "vid-a",
        "reason_code": reason,
        "expected_guru": "krishnaji",
        "predicted_guru": "krishnaji",
        "cosine": 0.8,
        "runner_up_cosine": 0.2,
        "margin": 0.6,
        "cosine_floor": 0.28,
        "margin_threshold": 1e-06,
        "audio_start_ms": 1000,
        "audio_end_ms": 5000,
        "audio_path": "/audio/vid-a.wav",
        "audio_sha256": "a" * 64,
        "audio_sample_rate": 16000,
        "speaker_model": "speechbrain/spkrec-ecapa-voxceleb",
        "speaker_model_revision": "m" * 40,
        "calibration_revision": "c" * 64,
        "run_id": "r" * 64,
        "split": "train",
        "transcript_hash": "t" * 64,
        "source_text_hash": "h" * 64,
    }


def _build(tmp_path, candidates, quarantines, verdicts, rights_rows):
    candidate = _write_jsonl(tmp_path / "candidate.jsonl", candidates)
    quarantine = _write_jsonl(tmp_path / "quarantine.jsonl", quarantines)
    verdict_path = _write_json(
        tmp_path / "verdicts.json",
        {"verdicts": verdicts, "run_id": "r" * 64, "calibration_revision": "c" * 64},
    )
    rights = _write_jsonl(tmp_path / "rights_join.jsonl", rights_rows)

    class _Args:
        pass

    args = _Args()
    args.candidate = str(candidate)
    args.quarantine = str(quarantine)
    args.verdicts = str(verdict_path)
    args.rights_join = str(rights)
    args.out_dir = str(tmp_path / "out")
    args.date = "2026-10-22"
    args.generated_at_utc = "2026-10-22T00:00:00+00:00"
    return tiers.build_tiers(args)


# ---------------------------------------------------------------------------
# tiers
# ---------------------------------------------------------------------------
def test_verified_and_rights_cleared_spans_reach_the_candidate_tier(tmp_path):
    built = _build(
        tmp_path,
        [_candidate_row("s1")],
        [],
        {"s1": _verdict("s1")},
        [{"source_span_id": "s1", "rights_status": "confirmed_channel_owner", "servable": True}],
    )
    assert len(built["tier_rows"][tiers.TIER_LOCAL]) == 1


def test_a_speaker_conflict_lands_in_review_required(tmp_path):
    built = _build(
        tmp_path,
        [_candidate_row("s1")],
        [],
        {"s1": _verdict("s1", "refused_guru_mismatch")},
        [{"source_span_id": "s1", "rights_status": "confirmed_channel_owner", "servable": True}],
    )
    assert not built["tier_rows"][tiers.TIER_LOCAL]
    review = built["tier_rows"][tiers.TIER_REVIEW]
    assert len(review) == 1
    assert "speaker_label_conflict_acoustic_contradiction" in review[0]["tier_reasons"]
    assert review[0]["serve_by_default"] is False


def test_a_below_floor_refusal_lands_in_review_required(tmp_path):
    built = _build(
        tmp_path,
        [_candidate_row("s1")],
        [],
        {"s1": _verdict("s1", "refused_below_cosine_floor")},
        [{"source_span_id": "s1", "rights_status": "confirmed_channel_owner", "servable": True}],
    )
    assert not built["tier_rows"][tiers.TIER_LOCAL]
    assert len(built["tier_rows"][tiers.TIER_REVIEW]) == 1


def test_a_rights_pending_span_lands_in_review_required(tmp_path):
    built = _build(
        tmp_path,
        [_candidate_row("s1")],
        [],
        {"s1": _verdict("s1")},
        [{"source_span_id": "s1", "rights_status": "pending_owner_review", "servable": False}],
    )
    assert not built["tier_rows"][tiers.TIER_LOCAL]
    review = built["tier_rows"][tiers.TIER_REVIEW]
    assert "rights_not_confirmed:pending_owner_review" in review[0]["tier_reasons"]


def test_variants_land_in_the_variant_tier_and_are_never_served(tmp_path):
    variant = _candidate_row("v1")
    variant["reconstruction_tier"] = "variant"
    variant["reconstruction_exact"] = False
    variant["quarantine_reasons"] = ["reconstruction_variant_not_exact"]
    built = _build(
        tmp_path,
        [],
        [variant],
        {},
        [],
    )
    assert len(built["tier_rows"][tiers.TIER_VARIANT]) == 1
    assert built["tier_rows"][tiers.TIER_VARIANT][0]["serve_by_default"] is False
    assert built["tier_rows"][tiers.TIER_VARIANT][0]["owner_decision_required"]


def test_unlocatable_spans_land_in_the_unlocatable_tier(tmp_path):
    unlocatable = _candidate_row("")
    unlocatable["source_span_id"] = ""
    unlocatable["reconstruction_tier"] = ""
    unlocatable["quarantine_reasons"] = ["span_not_located_in_asr"]
    built = _build(tmp_path, [], [unlocatable], {}, [])
    assert len(built["tier_rows"][tiers.TIER_UNLOCATABLE]) == 1


def test_two_rows_with_the_same_rebuilt_id_are_quarantined_not_deduplicated(tmp_path):
    """A rebuilt id must identify exactly one source span.

    Two rows that share a rebuilt id are a **collision**, not a duplicate:
    keeping one and dropping the other would hide a broken identity behind a
    healthy-looking count.
    """
    variant_a = _candidate_row("v1")
    variant_a["reconstruction_tier"] = "variant"
    variant_a["quarantine_reasons"] = ["reconstruction_variant_not_exact"]
    variant_a["live_source_span_id"] = "live-a"
    variant_b = _candidate_row("v1")
    variant_b["reconstruction_tier"] = "variant"
    variant_b["quarantine_reasons"] = ["reconstruction_variant_not_exact"]
    variant_b["live_source_span_id"] = "live-b"
    built = _build(tmp_path, [], [variant_a, variant_b], {}, [])
    assert not built["tier_rows"][tiers.TIER_VARIANT]
    collision_rows = built["tier_rows"][tiers.TIER_COLLISION]
    assert len(collision_rows) == 2
    assert built["collision_count"] == 1
    assert built["collision_member_count"] == 2
    assert {row["live_source_span_id"] for row in collision_rows} == {"live-a", "live-b"}
    for row in collision_rows:
        assert row["serve_by_default"] is False
        assert "deterministic_id_collision" in row["tier_reasons"]
    record = built["collision_records"][0]
    assert record["collision_cause"] == tiers.COLLISION_CAUSE
    assert record["namespace_fix_applied"] is False
    assert record["resolution_status"] == "unresolved"
    assert len(record["members"]) == 2


def test_a_span_without_a_verdict_fails_closed(tmp_path):
    with pytest.raises(tiers.CorpusTierError):
        _build(
            tmp_path,
            [_candidate_row("s1")],
            [],
            {},
            [{"source_span_id": "s1", "rights_status": "confirmed_channel_owner", "servable": True}],
        )


def test_a_span_without_a_rights_row_fails_closed(tmp_path):
    with pytest.raises(tiers.CorpusTierError):
        _build(tmp_path, [_candidate_row("s1")], [], {"s1": _verdict("s1")}, [])


# ---------------------------------------------------------------------------
# speaker conflict review package
# ---------------------------------------------------------------------------
def test_every_conflict_carries_the_full_evidence_record(tmp_path):
    candidates = [_candidate_row("s1")]
    verdicts = {"s1": _verdict("s1", "refused_guru_mismatch")}
    built = conflicts.build_conflicts(verdicts, candidates)
    assert len(built) == 1
    row = built[0]
    for key in (
        "source_span_id",
        "video_id",
        "expected_guru",
        "predicted_guru",
        "cosine",
        "margin",
        "audio_start_ms",
        "audio_end_ms",
        "audio_sha256",
        "speaker_model_revision",
        "calibration_revision",
        "transcript_hash",
        "source_text_hash",
        "reason_code",
        "recommended_review_action",
    ):
        assert key in row, key
    assert row["quarantined"] is True
    assert row["review_decision"] == ""
    assert row["playback"]["youtube_url"].startswith("https://www.youtube.com/watch?v=vid-a")


def test_a_conflict_never_relabels_anything(tmp_path):
    candidates = [_candidate_row("s1")]
    verdicts = {"s1": _verdict("s1", "refused_guru_mismatch")}
    built = conflicts.build_conflicts(verdicts, candidates)
    row = built[0]
    assert row["corpus_teacher_label"] == "krishnaji"
    assert row["expected_guru"] == "krishnaji"
    assert row["predicted_guru"] == "krishnaji"
    assert "Do not relabel" in row["recommended_review_action"]


def test_a_verdict_for_an_unknown_span_fails_closed():
    with pytest.raises(conflicts.SpeakerConflictError):
        conflicts.build_conflicts({"s9": _verdict("s9", "refused_guru_mismatch")}, [])


def test_non_conflict_verdicts_are_not_in_the_package(tmp_path):
    built = conflicts.build_conflicts({"s1": _verdict("s1")}, [_candidate_row("s1")])
    assert built == []
