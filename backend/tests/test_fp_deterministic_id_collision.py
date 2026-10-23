"""Deterministic-id collision tests for the first-person corpus tiers.

The rebuilt span id is a function of the reconstructed **word window** only::

    sha256(guru_id | video_id | corpus_version | word_start | word_end | transcript_hash)

Two distinct source spans whose locators resolve to the same word window
therefore produce the same id. When the tier builder deduplicated on that id,
it kept one row and dropped the other — the corpus *looked* healthy while an
identity was ambiguous.

These tests pin the repair: a collision is detected, every member is
quarantined, a dedicated collision record carries all the colliding inputs, and
the variant tier is one row per **source span**.
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


def _variant(span_id: str, *, live_span_id: str, video: str = "vid-a") -> dict:
    return _candidate_row(
        span_id,
        video_id=video,
        source_asset_id=video,
        reconstruction_tier="variant",
        reconstruction_exact=False,
        quarantine_reasons=[
            "audio_window_coverage_below_floor",
            "reconstruction_variant_not_exact",
        ],
        live_source_span_id=live_span_id,
        live_parent_unit_id="parent-" + video,
        live_start_ms=2605280,
        live_end_ms=2673810,
        live_word_start=2284,
        live_word_end=2307,
        live_source_text_hash="s" * 64,
        live_transcript_hash="lt" * 32,
        live_corpus_version="fp-context-transcript-v1",
        source_span_index=77,
        turn_id="parent-" + video + ":t77",
        turn_index=77,
        locator_start_token=2282,
        locator_end_token=2299,
        locator_similarity=0.7,
        timed_transcript_sha256="tt" * 32,
    )


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


def test_two_distinct_source_spans_with_the_same_rebuilt_id_are_both_quarantined(tmp_path):
    """The owner brief's exact case: live spans 3c4862e8… and 8a330f28…."""
    shared = "b7d1c4a06dccace5e689ab7a18d7f0668b4fadebb972bdab62f0ccb34063c6d9"
    built = _build(
        tmp_path,
        [],
        [
            _variant(
                shared,
                live_span_id="3c4862e8d4c36aee1211215171a662516bbedb20b2120dc8326a818deb1a13a8",
                video="MmiI3xo5Ju4",
            ),
            _variant(
                shared,
                live_span_id="8a330f28575000c1e3de668e0819655de21f58bca6b0fd9fdcf34afed34630d5",
                video="MmiI3xo5Ju4",
            ),
        ],
        {},
        [],
    )
    assert not built["tier_rows"][tiers.TIER_VARIANT]
    collision_rows = built["tier_rows"][tiers.TIER_COLLISION]
    assert len(collision_rows) == 2
    assert built["collision_count"] == 1
    assert built["collision_member_count"] == 2
    for row in collision_rows:
        assert row["serve_by_default"] is False
        assert row["collision_source_span_id"] == shared
        assert row["collision_member_count"] == 2
        assert "deterministic_id_collision" in row["tier_reasons"]


def test_the_collision_record_carries_every_colliding_input(tmp_path):
    shared = "b7d1c4a06dccace5e689ab7a18d7f0668b4fadebb972bdab62f0ccb34063c6d9"
    live_a = "3c4862e8d4c36aee1211215171a662516bbedb20b2120dc8326a818deb1a13a8"
    live_b = "8a330f28575000c1e3de668e0819655de21f58bca6b0fd9fdcf34afed34630d5"
    built = _build(
        tmp_path,
        [],
        [
            _variant(shared, live_span_id=live_a, video="MmiI3xo5Ju4"),
            _variant(shared, live_span_id=live_b, video="MmiI3xo5Ju4"),
        ],
        {},
        [],
    )
    record = built["collision_records"][0]
    assert record["schema"] == tiers.COLLISION_SCHEMA
    assert record["collided_source_span_id"] == shared
    assert record["member_count"] == 2
    assert record["distinct_source_span_count"] == 2
    assert record["distinct_live_span_ids"] == sorted([live_a, live_b])
    assert {member["live_source_span_id"] for member in record["members"]} == {live_a, live_b}
    for member in record["members"]:
        assert member["source_row_number"]
        assert member["input_record_sha256"]
        assert member["quarantine_record_id"]
        assert member["video_id"] == "MmiI3xo5Ju4"


def test_the_collision_cause_is_derived_from_the_data_not_assumed(tmp_path):
    """Same window, same normalization, same artifact → incomplete namespace."""
    shared = "b7d1c4a06dccace5e689ab7a18d7f0668b4fadebb972bdab62f0ccb34063c6d9"
    built = _build(
        tmp_path,
        [],
        [
            _variant(shared, live_span_id="live-a"),
            _variant(shared, live_span_id="live-b"),
        ],
        {},
        [],
    )
    record = built["collision_records"][0]
    assert record["collision_cause"] == tiers.COLLISION_CAUSE
    evidence = record["collision_cause_evidence"]
    assert evidence["distinct_rebuilt_id_windows"] == 1
    assert evidence["distinct_normalization_versions"] == ["fp-norm-unicode-v1"]
    assert evidence["distinct_timed_transcript_artifact_hashes"] == ["tt" * 32]
    assert evidence["distinct_live_source_span_ids"] == ["live-a", "live-b"]


def test_no_namespace_fix_is_claimed_and_the_collision_stays_unresolved(tmp_path):
    shared = "b7d1c4a06dccace5e689ab7a18d7f0668b4fadebb972bdab62f0ccb34063c6d9"
    built = _build(
        tmp_path,
        [],
        [
            _variant(shared, live_span_id="live-a"),
            _variant(shared, live_span_id="live-b"),
        ],
        {},
        [],
    )
    record = built["collision_records"][0]
    assert record["namespace_fix_applied"] is False
    assert record["resolution_status"] == "unresolved"
    assert "invalidates" in record["namespace_fix_reason"]
    assert record["span_id_namespace_missing_component"] == tiers.SPAN_ID_NAMESPACE_MISSING


def test_a_collision_never_leaks_into_the_servable_tier(tmp_path):
    shared = "b7d1c4a06dccace5e689ab7a18d7f0668b4fadebb972bdab62f0ccb34063c6d9"
    built = _build(
        tmp_path,
        [],
        [
            _variant(shared, live_span_id="live-a"),
            _variant(shared, live_span_id="live-b"),
        ],
        {},
        [],
    )
    assert not built["tier_rows"][tiers.TIER_LOCAL]
    assert all(row["serve_by_default"] is False for row in built["tier_rows"][tiers.TIER_COLLISION])


def test_the_variant_tier_is_one_row_per_source_span(tmp_path):
    """Three variants with three distinct ids produce three rows."""
    built = _build(
        tmp_path,
        [],
        [
            _variant("v1", live_span_id="live-1"),
            _variant("v2", live_span_id="live-2"),
            _variant("v3", live_span_id="live-3"),
        ],
        {},
        [],
    )
    rows = built["tier_rows"][tiers.TIER_VARIANT]
    assert len(rows) == 3
    assert len({row["source_span_id"] for row in rows}) == 3
    assert len({row["live_source_span_id"] for row in rows}) == 3
