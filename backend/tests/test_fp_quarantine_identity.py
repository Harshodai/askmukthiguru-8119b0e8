"""Quarantine-identity tests for the first-person corpus tiers.

Ten ``unlocatable_quarantine`` rows used to carry an **empty**
``source_span_id``, and two of their ``(video_id, guru_id)`` pairs repeated —
so neither the span id nor the pair identified a row. A quarantine record that
cannot be identified cannot be reviewed, cannot be excluded by id, and cannot
be reconciled.

These tests pin the repaired identity: the live span id is **recovered** when
the Phase-3 manifest carries it (never invented), every quarantine row gets a
unique immutable ``quarantine_record_id``, and two rows that share a
``(video_id, guru_id)`` pair stay distinguishable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
    }
    row.update(overrides)
    return row


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


def _build(tmp_path, candidates, quarantines, verdicts=None, rights_rows=None):
    candidate = _write_jsonl(tmp_path / "candidate.jsonl", candidates)
    quarantine = _write_jsonl(tmp_path / "quarantine.jsonl", quarantines)
    verdict_path = _write_json(
        tmp_path / "verdicts.json",
        {
            "verdicts": verdicts or {},
            "run_id": "r" * 64,
            "calibration_revision": "c" * 64,
        },
    )
    rights = _write_jsonl(tmp_path / "rights_join.jsonl", rights_rows or [])

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


def _unlocatable(live_span_id: str, *, video: str = "vid-a", guru: str = "krishnaji") -> dict:
    return _candidate_row(
        "",
        video_id=video,
        source_asset_id=video,
        guru_id=guru,
        reconstruction_tier="",
        reconstruction_exact=False,
        quarantine_reasons=["span_not_located_in_asr"],
        live_source_span_id=live_span_id,
        live_parent_unit_id="parent-" + video,
        live_start_ms=628943,
        live_end_ms=1171820,
        live_word_start=475,
        live_word_end=885,
        live_source_text_hash="s" * 64,
        live_transcript_hash="lt" * 32,
        live_corpus_version="fp-context-transcript-v1",
        source_span_index=2,
        turn_id="parent-" + video + ":t2",
        turn_index=2,
    )


def test_the_live_span_identity_is_recovered_not_invented(tmp_path):
    built = _build(tmp_path, [], [_unlocatable("live-span-1")], {}, [])
    rows = built["tier_rows"][tiers.TIER_UNLOCATABLE]
    assert len(rows) == 1
    row = rows[0]
    assert row["source_span_id"] == "live-span-1"
    assert row["source_span_id_namespace"] == tiers.LIVE_NAMESPACE
    assert row["rebuilt_source_span_id"] is None
    assert row["identity_status"] == "recovered"
    assert "live_source_span_id" in row["identity_resolution_reason"]


def test_a_row_without_a_live_span_id_is_marked_unresolved_but_still_identifiable(tmp_path):
    built = _build(tmp_path, [], [_unlocatable("")], {}, [])
    row = built["tier_rows"][tiers.TIER_UNLOCATABLE][0]
    assert row["source_span_id"] == ""
    assert row["identity_status"] == "unresolved"
    assert row["identity_resolution_reason"]
    assert row["quarantine_record_id"]
    assert len(row["quarantine_record_id"]) == 64


def test_two_rows_that_share_a_video_and_guru_pair_stay_distinguishable(tmp_path):
    """The (video, guru) pair is not a key — it repeats inside one video."""
    built = _build(
        tmp_path,
        [],
        [_unlocatable("live-a", video="vid-x"), _unlocatable("live-b", video="vid-x")],
        {},
        [],
    )
    rows = built["tier_rows"][tiers.TIER_UNLOCATABLE]
    assert len(rows) == 2
    record_ids = {row["quarantine_record_id"] for row in rows}
    assert len(record_ids) == 2
    live_ids = {row["live_source_span_id"] for row in rows}
    assert live_ids == {"live-a", "live-b"}


def test_the_quarantine_record_id_is_stable_across_runs(tmp_path):
    first = _build(tmp_path, [], [_unlocatable("live-a")], {}, [])
    second = _build(tmp_path, [], [_unlocatable("live-a")], {}, [])
    assert (
        first["tier_rows"][tiers.TIER_UNLOCATABLE][0]["quarantine_record_id"]
        == second["tier_rows"][tiers.TIER_UNLOCATABLE][0]["quarantine_record_id"]
    )


def test_the_quarantine_record_id_changes_when_the_evidence_changes(tmp_path):
    first = _build(tmp_path, [], [_unlocatable("live-a")], {}, [])
    second = _build(tmp_path, [], [_unlocatable("live-a", video="vid-y")], {}, [])
    assert (
        first["tier_rows"][tiers.TIER_UNLOCATABLE][0]["quarantine_record_id"]
        != second["tier_rows"][tiers.TIER_UNLOCATABLE][0]["quarantine_record_id"]
    )


def test_every_quarantine_row_carries_its_provenance_and_source_row_number(tmp_path):
    built = _build(
        tmp_path,
        [],
        [_unlocatable("live-a"), _unlocatable("live-b", video="vid-b")],
        {},
        [],
    )
    rows = built["tier_rows"][tiers.TIER_UNLOCATABLE]
    assert [row["source_row_number"] for row in rows] == [1, 2]
    for row in rows:
        assert row["input_record_sha256"]
        assert len(row["input_record_sha256"]) == 64
        assert row["live_parent_unit_id"]
        assert row["live_start_ms"] is not None
        assert row["live_word_start"] is not None
        assert row["turn_id"]
        assert row["source_span_index"] is not None


def test_the_tier_row_separates_the_file_duration_from_the_slice_duration(tmp_path):
    built = _build(tmp_path, [], [_unlocatable("live-a")], {}, [])
    row = built["tier_rows"][tiers.TIER_UNLOCATABLE][0]
    assert row["audio_file_duration_ms"] == 900000
    assert row["audio_slice_duration_ms"] == 4000
    assert row["audio_file_duration_ms"] != row["audio_slice_duration_ms"]
