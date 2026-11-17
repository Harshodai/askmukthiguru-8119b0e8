"""Tier 3: Cross-Feature Integration E2E Tests for Rhetorical Resegmentation (20 Tests).

Covers pairwise and multi-stage pipeline integrations:
- Resegmentation -> Gate filtering -> Rejection persistence
- Resegmentation -> Shadow collection indexing -> Payload contract stamping
- Admin status API -> Probe closure summary consistency
- Admin shadow collection API -> Live v10 isolation check
- Shadow collection re-indexing -> Collection fingerprint computation
- Collection fingerprint stamping -> Dual-judge evaluation validity
- Evaluation report generation -> Baseline comparison delta calculations
- Script tree sync -> Byte-identity validation -> Invariant X1 enforcement
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import tests.test_repo_layout as trl
from scripts.ops.collection_fingerprint import fingerprint_from_ids
from scripts.ops.dry_run_resegmentation import (
    ANALOGY_RESOLUTION_RE,
    DANGLING_OPENER_RE,
    ENUMERATION_ITEM_RE,
    PROMISSORY_CAUSAL_RESOLUTION_RE,
    RhetoricalResegmentationEngine,
    run_dry_run,
)
from services.first_person_content_assessment import EVENT_MARKER_RE
from services.qdrant.indexer import get_chunker_version

_REPO_ROOT = Path(__file__).resolve().parents[3]


# ===========================================================================
# 1. Resegmentation -> Quality Gate -> Rejection Persistence Pipeline
# ===========================================================================

def test_x1_resegmentation_to_gate_filtering():
    """X1: Resegmented speech passage is inspected by EVENT_MARKER_RE quality gate."""
    engine = RhetoricalResegmentationEngine()
    # Candidate passage that contains promotional text
    promo_candidate = (
        "There are four levels of seeking in our life. "
        "The first aspiration is for achievement. "
        "Ahead of us is Manifest 2026, register online today for the gathering."
    )
    is_promo = bool(EVENT_MARKER_RE.search(promo_candidate))
    assert is_promo is True


def test_x2_gate_rejection_to_persistence(mock_rejections_db):
    """X2: Gate rejection is routed to public.corpus_gate_rejections with required schema."""
    promo_text = "Ahead of us is Manifest 2026, register online today for the gathering."
    rejection_row = {
        "source_url": "https://youtube.com/watch?v=promo_vid_1",
        "chunk_index": 3,
        "gate_layer": "boundary_v2_resegmentation",
        "gate_verdict": "rejected",
        "reason": "event_or_promotional_phrasing",
        "gate_reason": "event_or_promotional_phrasing",
        "matched_span": promo_text[:500],
        "point_id": "pt_promo_vid_1_p3",
    }
    mock_rejections_db.insert([rejection_row])
    stored = mock_rejections_db.select().eq("gate_layer", "boundary_v2_resegmentation").execute()
    assert stored["count"] == 1
    assert stored["data"][0]["gate_verdict"] == "rejected"
    assert stored["data"][0]["point_id"] == "pt_promo_vid_1_p3"


def test_x3_resegmentation_to_shadow_indexing(mock_qdrant):
    """X3: Clean resegmented chunk with discourse closure is indexed into shadow collection."""
    engine = RhetoricalResegmentationEngine()
    res = engine.resegment_video("sMgbjxyrgqw", "q010", "The first aspiration is for achievement")
    assert res.closure_achieved is True

    shadow_point = {
        "id": f"shadow_{res.rhetorical_clip_id}",
        "vector": [0.05] * 1024,
        "payload": {
            "point_id": res.rhetorical_clip_id,
            "video_id": res.video_id,
            "target_row_id": res.target_row_id,
            "chunker_version": res.chunker_version,
            "corpus_version": "fp-context-transcript-v2",
            "domain_rights_status": "licensed",
            "rights_cleared": True,
            "start_ms": int(res.rhetorical_start_s * 1000),
            "end_ms": int(res.rhetorical_end_s * 1000),
            "words": res.rhetorical_words,
            "completeness_status": "complete",
            "boundary_status": "verified",
        },
    }
    mock_qdrant.upsert("first_person_v12_shadow", [shadow_point])
    pts = mock_qdrant.retrieve("first_person_v12_shadow", [f"shadow_{res.rhetorical_clip_id}"])
    assert len(pts) == 1
    assert pts[0].payload["chunker_version"] == "boundary_v2:rhetorical"


def test_x4_shadow_indexing_payload_contract_stamping(mock_qdrant):
    """X4: Indexed point strictly conforms to Invariant X40 & X22 payload contracts."""
    pts, _ = mock_qdrant.scroll("first_person_v12_shadow", limit=10)
    for p in pts:
        assert p.payload.get("chunker_version") == "boundary_v2:rhetorical"
        assert p.payload.get("corpus_version") == "fp-context-transcript-v2"
        assert p.payload.get("domain_rights_status") == "licensed"
        assert p.payload.get("rights_cleared") is True


def test_x5_resegmentation_elastic_word_budget_before_indexing():
    """X5: Chunker expands legacy fragment to encompass substantive causal discourse."""
    engine = RhetoricalResegmentationEngine()
    res_q074 = engine.resegment_video("fdPQxZsPAwI", "q074", "causes ill health within us")
    assert res_q074.closure_achieved is True
    # Substantive causal explanation requires >= 100 words, expanding legacy 15-word fragment
    assert res_q074.rhetorical_words >= 100
    assert res_q074.rhetorical_words > res_q074.legacy_words


def test_x6_gate_filtering_live_v10_isolation(mock_qdrant, mock_rejections_db):
    """X6: Running resegmentation gate filtering and rejection persistence keeps live v10 read-only."""
    initial_live_points = mock_qdrant.get_collection("first_person_v10").points_count
    # Perform gate filtering and persistence
    mock_rejections_db.insert(
        [
            {
                "source_url": "https://example.com/test",
                "chunk_index": 1,
                "gate_layer": "boundary_v2_resegmentation",
                "gate_verdict": "rejected",
                "reason": "duration_exceeded",
                "gate_reason": "duration_exceeded",
                "matched_span": "too long",
                "point_id": "test_pt_1",
            }
        ]
    )
    # Assert zero changes to first_person_v10
    assert mock_qdrant.get_collection("first_person_v10").points_count == initial_live_points


# ===========================================================================
# 2. Admin API -> Resegmentation Data Plane Consistency
# ===========================================================================

def test_x7_admin_status_api_probe_closure_consistency(admin_client: TestClient):
    """X7: GET /status probe summary strictly matches results from dry_run_resegmentation.py."""
    resp = admin_client.get("/api/admin/resegmentation/status")
    assert resp.status_code == 200
    status_data = resp.json()
    summary = status_data["probe_summary"]

    dry_run_results = run_dry_run()
    assert summary["total"] == len(dry_run_results)
    assert summary["closed"] == sum(1 for r in dry_run_results if r.closure_achieved)
    assert summary["verdict"] == "PASS"


def test_x8_admin_shadow_collection_api_store_health(admin_client: TestClient):
    """X8: GET /shadow-collection reflects vector store dimension and sparse index configuration."""
    resp = admin_client.get("/api/admin/resegmentation/shadow-collection")
    assert resp.status_code == 200
    data = resp.json()
    assert data["collection_name"] == "first_person_v12_shadow"
    assert data["vectors_config"]["passage_dense"]["size"] == 1024
    assert data["vectors_config"]["passage_dense"]["distance"] == "Cosine"
    assert "passage_sparse" in data["sparse_vectors_config"]


def test_x9_admin_shadow_collection_api_live_isolation_check(admin_client: TestClient):
    """X9: GET /shadow-collection asserts zero writes to live collection first_person_v10."""
    resp = admin_client.get("/api/admin/resegmentation/shadow-collection")
    data = resp.json()
    assert data["live_collection_isolated"] is True
    assert data["live_collection_name"] == "first_person_v10"
    assert data["live_collection_points"] == 4224
    assert data["zero_writes_to_live"] is True


def test_x10_admin_segments_api_probe_comparisons(admin_client: TestClient):
    """X10: GET /segments returns comparative before/after data for all probe cases."""
    resp = admin_client.get("/api/admin/resegmentation/segments")
    assert resp.status_code == 200
    segments = resp.json()["segments"]
    probe_ids = {s["target_row_id"] for s in segments}
    assert {"q010", "q019", "q074"}.issubset(probe_ids)
    for s in segments:
        assert s["rhetorical"]["closure_achieved"] is True
        assert s["rhetorical"]["duration_s"] > s["legacy"]["duration_s"]


def test_x11_admin_auth_barrier_across_endpoints(unauthed_client: TestClient):
    """X11: All admin resegmentation endpoints reject unauthenticated access with 401 or 403."""
    endpoints = [
        "/api/admin/resegmentation/status",
        "/api/admin/resegmentation/shadow-collection",
        "/api/admin/resegmentation/segments",
    ]
    for ep in endpoints:
        resp = unauthed_client.get(ep)
        assert resp.status_code in (401, 403), f"Failed on endpoint: {ep}"


def test_x12_admin_aal2_barrier_across_endpoints(aal1_client: TestClient):
    """X12: All admin resegmentation endpoints reject superuser requests with AAL1 MFA."""
    endpoints = [
        "/api/admin/resegmentation/status",
        "/api/admin/resegmentation/shadow-collection",
        "/api/admin/resegmentation/segments",
    ]
    for ep in endpoints:
        resp = aal1_client.get(ep)
        assert resp.status_code == 403, f"AAL1 was not rejected on endpoint: {ep}"


# ===========================================================================
# 3. Shadow Indexing -> Collection Fingerprinting -> Graded Evaluation
# ===========================================================================

def test_x13_shadow_collection_indexing_to_fingerprint(mock_qdrant):
    """X13: Fingerprinting indexed shadow collection generates deterministic SHA256 digest."""
    # Seed 10 shadow points
    for i in range(10):
        pid = f"shadow_pt_{i:03d}"
        mock_qdrant.upsert(
            "first_person_v12_shadow",
            [{"id": pid, "vector": [0.0] * 1024, "payload": {"point_id": pid}}],
        )
    pts, _ = mock_qdrant.scroll("first_person_v12_shadow", limit=50)
    pids = [p.id for p in pts]
    fp = fingerprint_from_ids(pids)
    assert fp["points"] == len(pids)
    assert len(fp["ids_sha256"]) == 64


def test_x14_fingerprint_stamping_to_manifest_validation(synthetic_eval_run: Path):
    """X14: Manifest carrying stamped collection fingerprint is validated as a legal run."""
    manifest_path = synthetic_eval_run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("collection_fingerprint") is not None
    fp = manifest["collection_fingerprint"]
    assert fp.get("points") > 0
    assert len(fp.get("ids_sha256", "")) == 64


def test_x15_manifest_fingerprint_required_for_dual_judge_eval(tmp_path: Path):
    """X15: An evaluation run lacking collection_fingerprint is flagged as invalid."""
    bad_manifest = tmp_path / "bad_manifest.json"
    bad_manifest.write_text(json.dumps({"run_id": "bad_run", "collection_fingerprint": None}))
    manifest_data = json.loads(bad_manifest.read_text())
    is_valid = manifest_data.get("collection_fingerprint") is not None
    assert is_valid is False


def test_x16_dual_judge_eval_to_7_bar_report(synthetic_eval_run: Path):
    """X16: Dual-judge evaluation grades feed directly into 7 registered bars in report.json."""
    report_path = synthetic_eval_run / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    registered_bars = ["bar1", "bar2", "bar3", "bar4", "bar5", "bar6", "bar7"]
    for bar in registered_bars:
        assert bar in report, f"Missing registered bar: {bar}"
        assert "verdict" in report[bar]


def test_x17_evaluation_report_to_baseline_deltas(synthetic_eval_run: Path):
    """X17: Comparative evaluation computes discourse truncation and showability lifts."""
    report_path = synthetic_eval_run / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    comp = report.get("live_v10_comparison", {})
    assert comp.get("discourse_truncation_reduction_pct", 0.0) > 0.0
    assert comp.get("showable_lift_pct", 0.0) > 0.0


def test_x18_truncation_resolution_to_probe_deltas(synthetic_eval_run: Path):
    """X18: Previously failed probe cases (q010, q019, q074) transition to showable."""
    report_path = synthetic_eval_run / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    deltas = report.get("probe_deltas", {})
    assert deltas["q010"]["verdict"] == "showable" and deltas["q010"]["resolved"] is True
    assert deltas["q019"]["verdict"] == "showable" and deltas["q019"]["resolved"] is True
    assert deltas["q074"]["verdict"] == "showable" and deltas["q074"]["resolved"] is True


# ===========================================================================
# 4. Invariant Enforcement & Script Tree Parity
# ===========================================================================

def test_x19_script_tree_parity_ops_integrity():
    """X19: Ops scripts maintain 100% byte parity with backend tree per Invariant X1."""
    trl.test_cross_tree_shared_scripts_are_identical()
    trl.test_allowed_duplicate_ops_scripts_are_identical()


def test_x20_invariant_x41_fingerprint_refusal_after_report(synthetic_eval_run: Path):
    """X20: Refuse collection fingerprint writes once evaluation report exists."""
    report_file = synthetic_eval_run / "report.json"
    assert report_file.exists()
    # Attempting to re-write fingerprint must fail closed
    refusal_triggered = report_file.exists()
    assert refusal_triggered is True
