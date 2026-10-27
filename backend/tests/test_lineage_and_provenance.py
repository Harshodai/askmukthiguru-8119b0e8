"""Tests for Phase 4 Lineage, Anti-Entropy, and Provenance (DE-2.1, DE-2.2, DE-2.3, DE-2.4)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.admin import admin_router
from app.dependencies import get_container
from app.main import app, get_current_user_from_supabase
from app.metrics import CORPUS_DRIFT_POINTS_TOTAL
from ingest.raptor import RaptorIndexer
from scripts.ops.cross_store_audit import audit_store_drift
from services.qdrant.indexer import QdrantIndexer


# ==============================================================================
# DE-2.1: RAPTOR Lineage (source_point_ids & parent_summary_id)
# ==============================================================================


@pytest.mark.asyncio
async def test_raptor_summary_carries_source_point_ids_and_sets_parent():
    """Test that RAPTOR summary carries source_point_ids: list[str] and sets parent_summary_id."""
    mock_embedder = MagicMock()
    # 8 chunks, each vector 10-dim
    mock_embedder.encode.return_value = [[0.1 * i] * 10 for i in range(8)]
    mock_embedder.encode_batch.return_value = {
        "dense": [[0.5] * 10 for _ in range(2)],
        "sparse": [{} for _ in range(2)],
    }

    mock_llm = MagicMock()
    mock_llm.summarize = AsyncMock(return_value="Hierarchical summary of the cluster teachings.")
    mock_llm._generate_fast = AsyncMock(return_value="Inner Peace")

    mock_qdrant = MagicMock()
    mock_qdrant.upsert_chunks.return_value = 1

    indexer = RaptorIndexer(mock_embedder, mock_llm, mock_qdrant)
    indexer._cluster_size = 4

    chunks = [
        {
            "text": f"Spiritual teaching excerpt number {i} regarding awareness.",
            "source_url": "https://example.com/lecture-1",
            "title": "Awareness Talk",
            "point_id": f"pt_id_{i}",
        }
        for i in range(8)
    ]

    # Force 2 clusters and bypass real LettuceDetect faithfulness check in unit test
    with patch.object(indexer, "_cluster_texts", return_value={0: [0, 1, 2, 3], 1: [4, 5, 6, 7]}):
        with patch.object(indexer, "_reduce_dimensions", return_value=[[0.1] * 2 for _ in range(8)]):
            with patch("ingest.quality_gate.gate_summary_faithfulness", return_value=(True, 1.0)):
                res = await indexer.build_tree(chunks)

    assert res == 1
    assert mock_qdrant.upsert_chunks.called
    call_args = mock_qdrant.upsert_chunks.call_args[0]
    metadatas = call_args[2]

    # Summary metadata assertions
    assert len(metadatas) == 2
    for meta in metadatas:
        assert "source_point_ids" in meta
        assert isinstance(meta["source_point_ids"], list)
        assert len(meta["source_point_ids"]) == 4
        assert "source_chunks" in meta
        assert meta["source_chunks"] == 4
        assert "cluster_id" in meta
        assert "point_id" in meta
        assert meta["point_id"] is not None

    assert metadatas[0]["source_point_ids"] == ["pt_id_0", "pt_id_1", "pt_id_2", "pt_id_3"]
    assert metadatas[1]["source_point_ids"] == ["pt_id_4", "pt_id_5", "pt_id_6", "pt_id_7"]

    # Verify source chunks received parent_summary_id
    for c in chunks[:4]:
        assert c.get("parent_summary_id") == metadatas[0]["point_id"]
    for c in chunks[4:]:
        assert c.get("parent_summary_id") == metadatas[1]["point_id"]


@pytest.mark.asyncio
async def test_raptor_summary_unfaithful_gated_out_and_logs_source_point_ids():
    """Test that unfaithful summary is dropped and logs its source_point_ids."""
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = [[0.1] * 10 for _ in range(4)]
    mock_embedder.encode_batch.return_value = {"dense": [[0.5] * 10], "sparse": [{}]}

    mock_llm = MagicMock()
    mock_llm.summarize = AsyncMock(return_value="Hallucinated summary.")
    mock_llm._generate_fast = AsyncMock(return_value="Topic")

    mock_qdrant = MagicMock()
    mock_qdrant.upsert_chunks.return_value = 0

    indexer = RaptorIndexer(mock_embedder, mock_llm, mock_qdrant)
    indexer._cluster_size = 4

    chunks = [
        {
            "text": f"Real chunk {i}",
            "source_url": "https://example.com/lecture-2",
            "title": "Real Talk",
            "point_id": f"real_pt_{i}",
        }
        for i in range(4)
    ]

    with patch.object(indexer, "_cluster_texts", return_value={0: [0, 1, 2, 3]}):
        with patch.object(indexer, "_reduce_dimensions", return_value=[[0.1] * 2 for _ in range(4)]):
            with patch("ingest.quality_gate.gate_summary_faithfulness", return_value=(False, 0.2)):
                with patch("ingest.raptor.logger.warning") as mock_log:
                    res = await indexer.build_tree(chunks)

    assert res == 0
    # Check that logger.warning was called explicitly logging source_point_ids
    found_log = False
    for call in mock_log.call_args_list:
        args = call[0]
        if "source_point_ids" in str(args):
            found_log = True
            break
    assert found_log, f"Expected logger.warning to mention source_point_ids: {mock_log.call_args_list}"

    # Verify that parent_summary_id was un-set on source chunks
    for c in chunks:
        assert "parent_summary_id" not in c


# ==============================================================================
# DE-2.2: Per-candidate gate_verdict at chokepoint
# ==============================================================================


def test_qdrant_indexer_stamps_gate_verdict_accepted():
    """Test that accepted points in QdrantIndexer receive gate_verdict='accepted' and gate_reason='clean'."""
    mock_client = MagicMock()
    mock_client.scroll.return_value = ([], None)

    indexer = QdrantIndexer(mock_client, collection="test_corpus")

    texts = ["Meditation brings deep stillness to the conscious mind and heart."]
    vectors = [[0.1] * 128]
    metadatas = [{"source_url": "https://example.com/meditation", "chunk_index": 0}]

    count = indexer.upsert_chunks(texts, vectors, metadatas)
    assert count == 1
    assert mock_client.upsert.called

    call_kwargs = mock_client.upsert.call_args[1]
    points = call_kwargs["points"]
    assert len(points) == 1
    point = points[0]

    assert point.payload.get("gate_verdict") == "accepted"
    assert point.payload.get("gate_reason") == "clean"


def test_qdrant_indexer_records_gate_verdict_rejected():
    """Test that rejected points record gate_verdict='rejected' with its reason."""
    mock_client = MagicMock()
    indexer = QdrantIndexer(mock_client, collection="test_corpus")

    # String that triggers graceful degradation artifact rejection
    degraded_text = "I am currently experiencing a temporary connection issue. Please try again."
    vectors = [[0.0] * 128]
    metadatas = [{"source_url": "https://example.com/bad", "chunk_index": 0}]

    mock_telemetry_client = MagicMock()
    mock_table = MagicMock()
    mock_telemetry_client.table.return_value = mock_table
    mock_table.insert.return_value.execute.return_value = None

    with patch("app.telemetry_db._get_client", return_value=mock_telemetry_client):
        count = indexer.upsert_chunks([degraded_text], vectors, metadatas)

    assert count == 0
    assert not mock_client.upsert.called
    assert mock_table.insert.called

    inserted_rows = mock_table.insert.call_args[0][0]
    assert len(inserted_rows) == 1
    row = inserted_rows[0]
    assert row["gate_verdict"] == "rejected"
    assert "graceful" in row["reason"].lower() or "graceful" in row.get("gate_reason", "").lower()


# ==============================================================================
# DE-2.3: Anti-Entropy Cross-Store Audit
# ==============================================================================


def test_audit_store_drift_detects_seeded_drift():
    """Test audit_store_drift detects drift between Qdrant points and Supabase/Graph records."""
    mock_qdrant = MagicMock()

    # Seed Qdrant with p1, p2, p3
    pt1 = MagicMock()
    pt1.id = "p1"
    pt2 = MagicMock()
    pt2.id = "p2"
    pt3 = MagicMock()
    pt3.id = "p3"
    mock_qdrant.scroll.return_value = ([pt1, pt2, pt3], None)

    # Seed Supabase with p1, p2, p4 (p3 is orphan in Qdrant, p4 is missing from Qdrant)
    mock_supabase = MagicMock()
    mock_res = MagicMock()
    mock_res.data = [{"point_id": "p1"}, {"point_id": "p2"}, {"point_id": "p4"}]
    mock_supabase.table.return_value.select.return_value.execute.return_value = mock_res

    res = audit_store_drift(mock_qdrant, supabase_client=mock_supabase, fix=False)

    assert res["status"] == "drift_detected"
    assert res["drift_count"] == 2
    assert res["orphan_qdrant_ids"] == ["p3"]
    assert res["missing_qdrant_ids"] == ["p4"]
    assert res["store_pair_drift"]["qdrant_supabase"] == 2
    assert not mock_qdrant.delete.called


def test_audit_store_drift_fix_mode_deletes_orphans():
    """Test audit_store_drift with fix=True deletes orphan Qdrant points."""
    mock_qdrant = MagicMock()
    pt1 = MagicMock(id="p1")
    pt2 = MagicMock(id="p2")
    mock_qdrant.scroll.return_value = ([pt1, pt2], None)

    mock_supabase = MagicMock()
    mock_res = MagicMock(data=[{"point_id": "p1"}])
    mock_supabase.table.return_value.select.return_value.execute.return_value = mock_res

    res = audit_store_drift(mock_qdrant, supabase_client=mock_supabase, fix=True)

    assert res["fix_applied"] is True
    assert res["repaired_count"] == 1
    assert mock_qdrant.delete.called
    call_kwargs = mock_qdrant.delete.call_args[1]
    assert call_kwargs["points_selector"] == ["p2"]


# ==============================================================================
# DE-2.4: Admin Provenance API
# ==============================================================================


def mock_admin_user():
    return {
        "id": "admin-1",
        "email": "admin@askmukthiguru.org",
        "is_superuser": True,
        "aal": "aal2",
    }


def test_admin_provenance_endpoint_returns_exact_fields():
    """Test /api/admin/corpus/provenance/{point_id} returns exact stored provenance fields."""
    app.dependency_overrides[get_current_user_from_supabase] = mock_admin_user

    mock_container = MagicMock()
    mock_qclient = MagicMock()
    mock_container.qdrant_client = mock_qclient

    stored_payload = {
        "source_url": "https://youtube.com/watch?v=sample123",
        "source_release_version": 2,
        "content_checksum": "sha256_mock_abcdef123456",
        "embedding_model": "bge-m3",
        "embedding_dimension": 1024,
        "chunker_version": "boundary_v1:1200/1",
        "gate_verdict": "accepted",
        "gate_reason": "clean",
        "asr_method": "whisper-large-v3",
        "align_method": "ecapa_tdnn",
        "rights_status": "licensed",
        "parent_id": "parent_uuid_789",
        "parent_id_scheme": "deterministic_v1",
        "created_at": "2026-10-27T12:00:00Z",
        "ingested_at": "2026-10-27T12:00:00Z",
    }
    retrieved_pt = MagicMock()
    retrieved_pt.id = "test-point-uuid-1"
    retrieved_pt.payload = stored_payload

    mock_qclient.retrieve.return_value = [retrieved_pt]
    app.dependency_overrides[get_container] = lambda: mock_container

    try:
        client = TestClient(app)
        response = client.get("/api/admin/corpus/provenance/test-point-uuid-1")

        assert response.status_code == 200
        data = response.json()

        assert data["point_id"] == "test-point-uuid-1"
        assert data["source_url"] == "https://youtube.com/watch?v=sample123"
        assert data["source_release_version"] == 2
        assert data["content_checksum"] == "sha256_mock_abcdef123456"
        assert data["embedding_model"] == "bge-m3"
        assert data["embedding_dimension"] == 1024
        assert data["chunker_version"] == "boundary_v1:1200/1"
        assert data["gate_verdict"] == "accepted"
        assert data["gate_reason"] == "clean"
        assert data["asr_method"] == "whisper-large-v3"
        assert data["align_method"] == "ecapa_tdnn"
        assert data["rights_status"] == "licensed"
        assert data["parent_id"] == "parent_uuid_789"
        assert data["parent_id_scheme"] == "deterministic_v1"
        assert data["created_at"] == "2026-10-27T12:00:00Z"
        assert data["ingested_at"] == "2026-10-27T12:00:00Z"

    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)
        app.dependency_overrides.pop(get_container, None)


def test_admin_provenance_endpoint_404_not_found():
    """Test /api/admin/corpus/provenance/{point_id} returns 404 when point is not in Qdrant."""
    app.dependency_overrides[get_current_user_from_supabase] = mock_admin_user

    mock_container = MagicMock()
    mock_qclient = MagicMock()
    mock_container.qdrant_client = mock_qclient
    mock_qclient.retrieve.return_value = []
    mock_qclient.scroll.return_value = ([], None)

    app.dependency_overrides[get_container] = lambda: mock_container

    try:
        client = TestClient(app)
        response = client.get("/api/admin/corpus/provenance/non-existent-id")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)
        app.dependency_overrides.pop(get_container, None)
