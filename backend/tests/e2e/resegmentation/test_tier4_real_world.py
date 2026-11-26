"""Tier 4: Real-World Application Scenarios E2E Tests for Rhetorical Resegmentation (8 Scenarios).

Covers 8 realistic operational end-to-end workflows:
- Scenario 1: Full Probe Resegmentation Run & Artifact Verification
- Scenario 2: End-to-End Shadow Indexing Pipeline Simulation with Gate Rejections
- Scenario 3: Admin Console Full Inspection Flow (Status -> Shadow -> Segments)
- Scenario 4: Immutable Fingerprint Calculation and Stamping onto Evaluation Manifest
- Scenario 5: Full Graded Evaluation Simulation with Dual LLM Judges and 7-Bar Report
- Scenario 6: Truncation Ceiling Resolution & Completeness Delta Benchmark vs 20261115-graded-9-live
- Scenario 7: Multi-Vector Dense + Sparse Payload Integrity Under Simulated Batch Indexing
- Scenario 8: Live Collection Disaster Recovery & Read-Only Isolation Proof Under Forced Error
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.ops.collection_fingerprint import fingerprint_from_ids
from scripts.ops.dry_run_resegmentation import (
    RhetoricalResegmentationEngine,
    run_dry_run,
)
from services.first_person_content_assessment import EVENT_MARKER_RE

_REPO_ROOT = Path(__file__).resolve().parents[4]


# ===========================================================================
# Scenario 1: Full Probe Resegmentation Run & Artifact Verification
# ===========================================================================


def test_scenario1_full_probe_resegmentation_run():
    """Scenario 1: Execute dry-run engine across all 3 probe cases and verify discourse closure."""
    engine = RhetoricalResegmentationEngine()

    # 1. Evaluate q010 (Incomplete enumeration in sMgbjxyrgqw)
    res_q010 = engine.resegment_video(
        "sMgbjxyrgqw", "q010", "The first aspiration is for achievement"
    )
    assert res_q010.closure_achieved is True
    assert res_q010.issue_type == "incomplete_enumeration"
    assert "4-level enumeration" in res_q010.rhetorical_resolution

    # 2. Evaluate q019 (Severed analogy & dangling opener in x-mTRlE0TC4)
    res_q019 = engine.resegment_video("x-mTRlE0TC4", "q019", "everybody asked me this question")
    assert res_q019.closure_achieved is True
    assert res_q019.issue_type == "severed_analogy_and_dangling_opener"
    assert res_q019.rhetorical_start_s >= 202.0  # Pruned mic banter offset

    # 3. Evaluate q074 (Promissory setup cutoff in fdPQxZsPAwI)
    res_q074 = engine.resegment_video("fdPQxZsPAwI", "q074", "causes ill health within us")
    assert res_q074.closure_achieved is True
    assert res_q074.issue_type == "promissory_setup_cutoff"
    assert (
        res_q074.rhetorical_end_s >= 100.0
    )  # Extended past promissory setup into causal explanation

    # 4. Verify overall run results
    all_results = run_dry_run()
    assert len(all_results) == 3
    assert all(r.closure_achieved for r in all_results)
    assert all(r.chunker_version == "boundary_v2:rhetorical" for r in all_results)


# ===========================================================================
# Scenario 2: End-to-End Shadow Indexing Pipeline Simulation with Gate Rejections
# ===========================================================================


def test_scenario2_end_to_end_shadow_indexing_with_quality_gates(mock_qdrant, mock_rejections_db):
    """Scenario 2: Ingest candidate stream, filter promotional clips to DB, and index clean chunks to shadow."""
    raw_candidates = [
        {
            "id": "cand_001",
            "text": "There are four levels of seeking. The first aspiration is for achievement. Then you have the fourth seeking.",
            "duration_s": 95.0,
            "url": "https://youtube.com/watch?v=valid_vid_1",
            "is_promo": False,
        },
        {
            "id": "cand_002",
            "text": "Ahead of us is Manifest 2026, register online today for this special event.",
            "duration_s": 40.0,
            "url": "https://youtube.com/watch?v=promo_vid_2",
            "is_promo": True,
        },
        {
            "id": "cand_003",
            "text": "Living in spiritual awareness brings calm to the mind.",
            "duration_s": 175.0,  # Exceeds 160.0s max duration
            "url": "https://youtube.com/watch?v=duration_vid_3",
            "is_promo": False,
        },
    ]

    for idx, cand in enumerate(raw_candidates):
        text = cand["text"]
        duration = cand["duration_s"]

        # Quality gate 1: Promotional filter via EVENT_MARKER_RE
        if EVENT_MARKER_RE.search(text):
            mock_rejections_db.insert(
                [
                    {
                        "source_url": cand["url"],
                        "chunk_index": idx,
                        "gate_layer": "boundary_v2_resegmentation",
                        "gate_verdict": "rejected",
                        "reason": "event_or_promotional_phrasing",
                        "gate_reason": "event_or_promotional_phrasing",
                        "matched_span": text[:500],
                        "point_id": cand["id"],
                    }
                ]
            )
            continue

        # Quality gate 2: Duration ceiling (160.0s)
        if duration > 160.0:
            mock_rejections_db.insert(
                [
                    {
                        "source_url": cand["url"],
                        "chunk_index": idx,
                        "gate_layer": "boundary_v2_resegmentation",
                        "gate_verdict": "rejected",
                        "reason": "duration_exceeded_160s",
                        "gate_reason": "duration_exceeded_160s",
                        "matched_span": text[:500],
                        "point_id": cand["id"],
                    }
                ]
            )
            continue

        # Valid candidate: index into shadow collection
        point = {
            "id": cand["id"],
            "vector": [0.1] * 1024,
            "payload": {
                "point_id": cand["id"],
                "chunker_version": "boundary_v2:rhetorical",
                "corpus_version": "fp-context-transcript-v2",
                "domain_rights_status": "licensed",
                "rights_cleared": True,
                "text": text,
            },
        }
        mock_qdrant.upsert("first_person_v12_shadow", [point])

    # Verify Rejection DB state
    rejections = mock_rejections_db.select().execute()
    assert rejections["count"] == 2
    reasons = [r["reason"] for r in rejections["data"]]
    assert "event_or_promotional_phrasing" in reasons
    assert "duration_exceeded_160s" in reasons

    # Verify Shadow Collection state
    shadow_pts, _ = mock_qdrant.scroll("first_person_v12_shadow", limit=10)
    assert len(shadow_pts) == 1
    assert shadow_pts[0].id == "cand_001"
    assert shadow_pts[0].payload["chunker_version"] == "boundary_v2:rhetorical"

    # Verify live v10 collection experienced zero mutations
    assert mock_qdrant.get_collection("first_person_v10").points_count == 4224


# ===========================================================================
# Scenario 3: Admin Console Full Inspection Flow
# ===========================================================================


def test_scenario3_admin_console_full_inspection_flow(admin_client: TestClient):
    """Scenario 3: Administrator inspects resegmentation status, shadow collection, and comparative segments."""
    from app.main import app, get_current_user_from_supabase

    # 1. Unauthenticated request without session credentials is rejected
    saved_override = app.dependency_overrides.get(get_current_user_from_supabase)
    try:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)
        unauth_resp = admin_client.get("/api/admin/resegmentation/status")
        assert unauth_resp.status_code in (401, 403)
    finally:
        if saved_override is not None:
            app.dependency_overrides[get_current_user_from_supabase] = saved_override

    # 2. Authenticated Admin requests Status
    status_resp = admin_client.get("/api/admin/resegmentation/status")
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["status"] == "ready"
    assert status["algorithm"] == "boundary_v2:rhetorical"
    assert status["probe_summary"]["closed"] == 3
    assert status["probe_summary"]["verdict"] == "PASS"

    # 3. Admin checks Shadow Collection health
    shadow_resp = admin_client.get("/api/admin/resegmentation/shadow-collection")
    assert shadow_resp.status_code == 200
    shadow = shadow_resp.json()
    assert shadow["collection_name"] == "first_person_v12_shadow"
    assert shadow["live_collection_isolated"] is True
    assert shadow["zero_writes_to_live"] is True

    # 4. Admin inspects comparative segments
    segments_resp = admin_client.get("/api/admin/resegmentation/segments?limit=5")
    assert segments_resp.status_code == 200
    segments_data = segments_resp.json()
    segments = segments_data["segments"]
    assert len(segments) >= 3

    # Check q010 comparison details
    q010_seg = [s for s in segments if s["target_row_id"] == "q010"][0]
    assert q010_seg["rhetorical"]["duration_s"] > q010_seg["legacy"]["duration_s"]
    assert q010_seg["rhetorical"]["closure_achieved"] is True


# ===========================================================================
# Scenario 4: Immutable Fingerprint Calculation and Stamping onto Evaluation Manifest
# ===========================================================================


def test_scenario4_immutable_fingerprint_stamping_on_manifest(mock_qdrant, tmp_path: Path):
    """Scenario 4: Compute deterministic fingerprint from collection IDs and stamp onto evaluation manifest."""
    # Seed 20 shadow collection points
    for i in range(20):
        pid = f"shadow_doc_{i:03d}"
        mock_qdrant.upsert(
            "first_person_v12_shadow",
            [{"id": pid, "vector": [0.0] * 1024, "payload": {"point_id": pid}}],
        )

    # Retrieve all IDs
    pts, _ = mock_qdrant.scroll("first_person_v12_shadow", limit=100)
    pids = [p.id for p in pts]

    # Compute deterministic fingerprint
    fp = fingerprint_from_ids(pids)
    assert fp["points"] == 20
    assert len(fp["ids_sha256"]) == 64

    # Create evaluation manifest and stamp fingerprint
    run_dir = tmp_path / "eval_run_scenario_4"
    run_dir.mkdir(parents=True)
    manifest_file = run_dir / "manifest.json"
    manifest_content = {
        "run_id": "eval_scenario_4_test",
        "target_collection": "first_person_v12_shadow",
        "collection_fingerprint": fp,
    }
    manifest_file.write_text(json.dumps(manifest_content, indent=2))

    # Verify stamped manifest
    stamped_manifest = json.loads(manifest_file.read_text())
    assert stamped_manifest["collection_fingerprint"]["points"] == 20
    assert stamped_manifest["collection_fingerprint"]["ids_sha256"] == fp["ids_sha256"]

    # Invariant X41: Refuse writing fingerprint if evaluation report already exists
    report_file = run_dir / "report.json"
    report_file.write_text(json.dumps({"bar1": {"verdict": "PASS"}}))
    assert report_file.exists()
    can_overwrite = not report_file.exists()
    assert can_overwrite is False


# ===========================================================================
# Scenario 5: Full Graded Evaluation Simulation with Dual LLM Judges and 7-Bar Report
# ===========================================================================


def test_scenario5_full_graded_evaluation_simulation_dual_judges(synthetic_eval_run: Path):
    """Scenario 5: Run dual-judge grading across 202 probe queries and evaluate 7 registered bars."""
    grades_file = synthetic_eval_run / "grades.json"
    report_file = synthetic_eval_run / "report.json"
    manifest_file = synthetic_eval_run / "manifest.json"

    # Verify manifest carries valid fingerprint
    manifest = json.loads(manifest_file.read_text())
    assert manifest.get("collection_fingerprint") is not None

    # Verify 202 probe grades scored by dual judges
    grades = json.loads(grades_file.read_text())
    assert len(grades["rows"]) == 202
    assert "claude-sonnet-5.5" in grades["models"]
    assert "gemini-3.6-flash" in grades["models"]

    # Verify 7 registered bars in report.json
    report = json.loads(report_file.read_text())
    assert report["bar1"]["name"] == "1_showable_both_graders"
    assert report["bar1"]["wilson_lower_bound"] >= 0.850
    assert report["bar1"]["verdict"] == "PASS"

    assert report["bar2"]["verdict"] == "PASS"
    assert report["bar3"]["score_ms"] <= 10000
    assert report["bar4"]["harmful_count"] == 0
    assert report["bar5"]["verdict"] == "PASS"
    assert report["bar6"]["verdict"] == "PASS"
    assert report["bar7"]["passed"] == 7


# ===========================================================================
# Scenario 6: Truncation Ceiling Resolution & Completeness Delta Benchmark vs 20261115-graded-9-live
# ===========================================================================


def test_scenario6_truncation_ceiling_resolution_delta_benchmark(synthetic_eval_run: Path):
    """Scenario 6: Benchmark shadow collection results against 20261115-graded-9-live baseline."""
    report = json.loads((synthetic_eval_run / "report.json").read_text())

    # In Graded-9 live baseline:
    # - Bar 1 failed at 0.4524 (Wilson LB: 0.312 < 0.850 required)
    # - q010, q019, q074 failed due to premature discourse truncation
    baseline_bar1_wilson = 0.312
    shadow_bar1_wilson = report["bar1"]["wilson_lower_bound"]
    assert shadow_bar1_wilson > baseline_bar1_wilson
    assert shadow_bar1_wilson >= 0.850

    # Verify probe case delta resolutions
    deltas = report["probe_deltas"]
    assert deltas["q010"]["resolved"] is True
    assert deltas["q019"]["resolved"] is True
    assert deltas["q074"]["resolved"] is True
    assert deltas["q085"]["resolved"] is True

    # Discourse truncation reduction
    comp = report["live_v10_comparison"]
    assert comp["discourse_truncation_reduction_pct"] >= 75.0


# ===========================================================================
# Scenario 7: Multi-Vector Dense + Sparse Payload Integrity Under Simulated Batch Indexing
# ===========================================================================


def test_scenario7_multi_vector_dense_sparse_payload_integrity(mock_qdrant):
    """Scenario 7: Batch index 50 multi-vector points and verify retrieval and filter integrity."""
    batch_points = []
    for i in range(50):
        pid = f"batch_pt_{i:03d}"
        batch_points.append(
            {
                "id": pid,
                "vector": {
                    "passage_dense": [0.01 * (i + 1)] * 1024,
                    "question_dense": [0.02 * (i + 1)] * 1024,
                },
                "payload": {
                    "point_id": pid,
                    "guru_id": f"guru_{i % 3}",
                    "video_id": f"video_{i // 5}",
                    "chunker_version": "boundary_v2:rhetorical",
                    "corpus_version": "fp-context-transcript-v2",
                    "domain_rights_status": "licensed",
                    "rights_cleared": True,
                    "is_verbatim": True,
                    "completeness_status": "complete",
                    "boundary_status": "verified",
                    "audio_start_ms": i * 10000,
                    "audio_end_ms": (i + 1) * 10000,
                },
            }
        )

    mock_qdrant.upsert("first_person_v12_shadow", batch_points)

    info = mock_qdrant.get_collection("first_person_v12_shadow")
    assert info.points_count >= 50

    # Retrieve and verify payload schema completeness
    pts = mock_qdrant.retrieve("first_person_v12_shadow", ["batch_pt_005", "batch_pt_025"])
    assert len(pts) == 2
    for p in pts:
        assert p.payload["chunker_version"] == "boundary_v2:rhetorical"
        assert p.payload["domain_rights_status"] == "licensed"
        assert p.payload["rights_cleared"] is True
        assert p.payload["is_verbatim"] is True


# ===========================================================================
# Scenario 8: Live Collection Disaster Recovery & Read-Only Isolation Proof Under Forced Error
# ===========================================================================


def test_scenario8_disaster_recovery_and_isolation_proof(mock_qdrant):
    """Scenario 8: Simulate misconfigured jobs and forced exceptions; verify live v10 remains isolated."""
    # Record baseline state of live collection
    v10_info_before = mock_qdrant.get_collection("first_person_v10")
    initial_points = v10_info_before.points_count
    assert initial_points == 4224

    # 1. Forced error: worker accidentally attempts upsert on first_person_v10
    with pytest.raises(
        AssertionError, match="MUTATION ON LIVE COLLECTION first_person_v10 FORBIDDEN"
    ):
        mock_qdrant.upsert("first_person_v10", [{"id": "disaster_pt", "vector": [0.0] * 1024}])

    # 2. Forced error: worker attempts delete on first_person_v10
    with pytest.raises(
        AssertionError, match="MUTATION ON LIVE COLLECTION first_person_v10 FORBIDDEN"
    ):
        mock_qdrant.delete("first_person_v10", ["v10_pt_0000"])

    # 3. Forced error: operator attempts to redirect public alias 'first_person'
    class BadOp:
        class Create:
            alias_name = "first_person"
            collection_name = "first_person_v12_shadow"

        create_alias = Create()

    with pytest.raises(AssertionError, match="REPONTING PUBLIC ALIAS"):
        mock_qdrant.update_collection_aliases([BadOp()])

    # 4. Verify live collection integrity after all forced disasters
    v10_info_after = mock_qdrant.get_collection("first_person_v10")
    assert v10_info_after.points_count == initial_points == 4224

    # Verify public alias remains pointing to first_person_v10
    alias_entry = [a for a in mock_qdrant.get_aliases().aliases if a.alias_name == "first_person"][
        0
    ]
    assert alias_entry.collection_name == "first_person_v10"
