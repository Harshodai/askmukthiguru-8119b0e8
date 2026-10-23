"""Tier-reconciliation tests: the counts must add up with nothing hidden.

Before this repair the tier builder deduplicated on the rebuilt span id, so
the tier counts reconciled against ``inputs − 1`` and the report presented
2,736 rows for a corpus of 2,737 live spans. The single missing row was a
deterministic-id collision that had been absorbed.

These tests pin the arithmetic: every input row produces exactly one output
row, the totals equal the live span count, and the collision count is reported
in every summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import build_fp_corpus_tiers as tiers  # noqa: E402


def _candidate_row(span_id: str, **overrides) -> dict:
    row = {
        "source_span_id": span_id,
        "video_id": "vid-a",
        "source_asset_id": "vid-a",
        "guru_id": "krishnaji",
        "reconstructed_text": "Meditation is a practice of awareness.",
        "source_text_hash": "h" * 64,
        "transcript_hash": "t" * 64,
        "archived_audio_sha256": "a" * 64,
        "archived_audio_path": "/audio/vid-a.wav",
        "archived_audio_duration_ms": 900000,
        "audio_start_ms": 1000,
        "audio_end_ms": 5000,
        "word_start": 0,
        "word_end": 10,
        "corpus_version": "fp-context-transcript-v2",
        "normalization_version": "fp-norm-unicode-v1",
        "coordinate_space_version": "fp-coords-v1",
        "reconstruction_tier": "exact",
        "reconstruction_exact": True,
        "live_source_span_id": "live-" + (span_id or "x"),
    }
    row.update(overrides)
    return row


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
    args.rights_manifest = None
    args.out_dir = str(tmp_path / "out")
    args.date = "2026-10-22"
    args.generated_at_utc = "2026-10-22T00:00:00+00:00"
    return tiers.build_tiers(args)


def test_every_input_row_produces_exactly_one_output_row(tmp_path):
    candidates = [_candidate_row("s1"), _candidate_row("s2")]
    quarantines = [
        _candidate_row(
            "v1",
            reconstruction_tier="variant",
            reconstruction_exact=False,
            quarantine_reasons=["reconstruction_variant_not_exact"],
        ),
        _candidate_row(
            "",
            reconstruction_tier="",
            reconstruction_exact=False,
            quarantine_reasons=["span_not_located_in_asr"],
        ),
    ]
    built = _build(
        tmp_path,
        candidates,
        quarantines,
        {"s1": _verdict("s1"), "s2": _verdict("s2")},
        [
            {"source_span_id": "s1", "rights_status": "confirmed_channel_owner", "servable": True},
            {"source_span_id": "s2", "rights_status": "confirmed_channel_owner", "servable": True},
        ],
    )
    total = sum(len(rows) for rows in built["tier_rows"].values())
    assert total == len(candidates) + len(quarantines)
    assert built["candidate_count"] == 2
    assert built["quarantine_count"] == 2


def test_the_summary_reports_the_collision_count(tmp_path):
    shared = "shared-id"
    built = _build(
        tmp_path,
        [],
        [
            _candidate_row(
                shared,
                reconstruction_tier="variant",
                reconstruction_exact=False,
                quarantine_reasons=["reconstruction_variant_not_exact"],
                live_source_span_id="live-a",
            ),
            _candidate_row(
                shared,
                reconstruction_tier="variant",
                reconstruction_exact=False,
                quarantine_reasons=["reconstruction_variant_not_exact"],
                live_source_span_id="live-b",
            ),
        ],
        {},
        [],
    )
    assert built["collision_count"] == 1
    assert built["collision_member_count"] == 2


def test_the_summary_and_the_manifest_agree_on_the_counts(tmp_path):
    """A summary that disagrees with the manifest is a broken summary."""
    candidates = [_candidate_row("s1")]
    _build(
        tmp_path,
        candidates,
        [],
        {"s1": _verdict("s1")},
        [{"source_span_id": "s1", "rights_status": "confirmed_channel_owner", "servable": True}],
    )
    out_dir = tmp_path / "out"
    argv = [
        "--candidate",
        str(tmp_path / "candidate.jsonl"),
        "--quarantine",
        str(tmp_path / "quarantine.jsonl"),
        "--verdicts",
        str(tmp_path / "verdicts.json"),
        "--rights-join",
        str(tmp_path / "rights_join.jsonl"),
        "--out-dir",
        str(out_dir),
        "--date",
        "2026-10-22",
    ]
    assert tiers.main(argv) == 0
    summary = json.loads(
        (out_dir / "public_release_phase4_tiers_summary_2026-10-22.json").read_text()
    )
    manifest = json.loads(
        (out_dir / "public_release_phase4_tiers_manifest_2026-10-22.json").read_text()
    )
    assert summary["tier_counts"] == manifest["tier_counts"]
    assert summary["tier_counts"][tiers.TIER_LOCAL] == 1
    assert summary["output_counts"]["total_rows"] == 1
    assert summary["output_counts"]["rows_dropped"] == 0
    assert summary["output_counts"]["rows_deduplicated"] == 0
    assert summary["deterministic_id_collisions"]["collision_count"] == 0
    assert manifest["deterministic_id_collisions"]["row_count"] == 0
    assert summary["public_verified_claim"] is False


def test_the_shipped_tier_artifacts_reconcile_with_the_live_span_count():
    """The real, shipped artifact set: 2,737 rows for 2,737 live spans."""
    evidence = _BACKEND.parent / "audits" / "evidence"
    summary_path = evidence / "public_release_phase4_tiers_summary_2026-10-22.json"
    if not summary_path.is_file():
        pytest.skip("shipped tier summary is not present in this checkout")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    counts = summary["tier_counts"]
    assert sum(counts.values()) == summary["input_counts"]["phase3_total_rows"]
    assert summary["output_counts"]["total_rows"] == 2737
    assert summary["output_counts"]["total_unique_live_source_span_ids"] == 2737
    assert summary["output_counts"]["rows_dropped"] == 0
    assert summary["output_counts"]["rows_deduplicated"] == 0
    assert summary["deterministic_id_collisions"]["collision_count"] == 1
    assert summary["deterministic_id_collisions"]["collision_member_count"] == 2
    assert summary["duplicate_ids_by_identity_level"]["by_live_source_span_id"]["group_count"] == 0
    assert summary["duplicate_ids_by_identity_level"]["by_quarantine_record_id"]["group_count"] == 0
    assert (
        summary["duplicate_ids_by_identity_level"]["by_rebuilt_source_span_id"]["group_count"] == 1
    )
