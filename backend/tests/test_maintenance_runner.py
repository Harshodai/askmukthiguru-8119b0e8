"""
Tests for standalone Maintenance & Migration Runner (Phase 1.2).

Verifies:
1. --list outputs all registered operations.
2. --dry-run plans mutations without executing them.
3. --apply executes operations successfully and is idempotent when run twice.
4. Distributed Redis lock prevents concurrent execution.
5. Precondition failure handling.
6. Application startup in app.main is strictly read-only and executes no maintenance mutations.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.models import CollectionsResponse

from migrations.maintenance_runner import (
    OPERATIONS,
    CleanupStaleCollectionsOperation,
    DistributedLock,
    ExitCode,
    LightRAGEntityDedupOperation,
    MaintenanceContext,
    Neo4jOntologyOperation,
    QdrantContractOperation,
    QdrantPayloadIndexesOperation,
    list_operations,
    main,
    run_operation,
)


class MockCollection:
    def __init__(self, name: str):
        self.name = name


@pytest.fixture
def mock_qdrant_client():
    client = MagicMock()
    client.get_collections.return_value = MagicMock(
        collections=[
            MockCollection("spiritual_wisdom"),
            MockCollection("lightrag_vdb_entities_baai_bge_m3_1024d"),
            MockCollection("lightrag_vdb_relationships_baai_bge_m3_1024d"),
            MockCollection("lightrag_vdb_chunks_baai_bge_m3_1024d"),
        ]
    )

    col_info = MagicMock()
    col_info.config.hnsw_config.m = 0
    col_info.points_count = 0
    client.get_collection.return_value = col_info

    return client


@pytest.fixture
def mock_neo4j_driver():
    driver = MagicMock()
    driver.verify_connectivity.return_value = None
    session_mock = MagicMock()
    driver.session.return_value.__enter__.return_value = session_mock
    return driver


@pytest.fixture
def mock_redis_client():
    r = MagicMock()
    r.set.return_value = True
    r.eval.return_value = 1
    r.ping.return_value = True
    return r


# =============================================================================
# 1. Operation Listing Tests
# =============================================================================

def test_list_operations_contains_all_registered():
    ops = list_operations()
    op_names = {item["name"] for item in ops}
    expected = {
        "qdrant-contract-v1",
        "neo4j-ontology-schema-v1",
        "qdrant-payload-indexes-v1",
        "lightrag-entity-dedup-v1",
        "cleanup-stale-collections-v1",
    }
    assert expected.issubset(op_names)


def test_cli_list_stdout(capsys):
    with patch("sys.argv", ["maintenance_runner.py", "--list"]):
        exit_code = main()
        assert exit_code == ExitCode.SUCCESS

    captured = capsys.readouterr()
    assert "qdrant-contract-v1" in captured.out
    assert "neo4j-ontology-schema-v1" in captured.out
    assert "qdrant-payload-indexes-v1" in captured.out
    assert "lightrag-entity-dedup-v1" in captured.out
    assert "cleanup-stale-collections-v1" in captured.out


def test_cli_list_json(capsys):
    with patch("sys.argv", ["maintenance_runner.py", "--list", "--json"]):
        exit_code = main()
        assert exit_code == ExitCode.SUCCESS

    captured = capsys.readouterr()
    import json
    data = json.loads(captured.out)
    assert "operations" in data
    names = [o["name"] for o in data["operations"]]
    assert "qdrant-contract-v1" in names


# =============================================================================
# 2. Dry-Run Planning Tests (No Mutations Allowed)
# =============================================================================

def test_qdrant_contract_dry_run_does_not_mutate(mock_qdrant_client):
    ctx = MaintenanceContext(qdrant_client=mock_qdrant_client, dry_run=True)
    res = run_operation("qdrant-contract-v1", dry_run=True, ctx=ctx)

    assert res.status == "PLANNED"
    assert res.exit_code == ExitCode.SUCCESS
    assert len(res.plan) > 0
    # Verify no mutation methods were called
    mock_qdrant_client.update_collection.assert_not_called()
    mock_qdrant_client.create_collection.assert_not_called()
    mock_qdrant_client.delete_collection.assert_not_called()


def test_neo4j_ontology_dry_run_does_not_mutate(mock_neo4j_driver, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "neo4j_uri", "bolt://test", raising=False)
    ctx = MaintenanceContext(neo4j_driver=mock_neo4j_driver, dry_run=True)
    with patch("app.db.seed_ontology.seed_spiritual_ontology") as mock_seed:
        res = run_operation("neo4j-ontology-schema-v1", dry_run=True, ctx=ctx)
        assert res.status == "PLANNED"
        assert res.exit_code == ExitCode.SUCCESS
        assert len(res.plan) > 0
        mock_seed.assert_not_called()


def test_qdrant_payload_indexes_dry_run_does_not_mutate(mock_qdrant_client):
    ctx = MaintenanceContext(qdrant_client=mock_qdrant_client, dry_run=True)
    res = run_operation("qdrant-payload-indexes-v1", dry_run=True, ctx=ctx)

    assert res.status == "PLANNED"
    assert res.exit_code == ExitCode.SUCCESS
    assert len(res.plan) > 0
    mock_qdrant_client.create_payload_index.assert_not_called()


def test_lightrag_entity_dedup_dry_run_does_not_mutate():
    mock_rag = MagicMock()
    ctx = MaintenanceContext(lightrag_instance=mock_rag, dry_run=True)
    res = run_operation("lightrag-entity-dedup-v1", dry_run=True, ctx=ctx)

    assert res.status == "PLANNED"
    assert res.exit_code == ExitCode.SUCCESS
    assert len(res.plan) == len(LightRAGEntityDedupOperation.ENTITY_MERGES)
    mock_rag.merge_entities.assert_not_called()


def test_cleanup_stale_collections_dry_run_does_not_mutate(mock_qdrant_client):
    ctx = MaintenanceContext(qdrant_client=mock_qdrant_client, dry_run=True)
    res = run_operation("cleanup-stale-collections-v1", dry_run=True, ctx=ctx)

    assert res.status == "PLANNED"
    assert res.exit_code == ExitCode.SUCCESS
    mock_qdrant_client.delete_collection.assert_not_called()


# =============================================================================
# 3. Apply Execution & Idempotency Tests
# =============================================================================

def test_qdrant_contract_apply_and_idempotency(mock_qdrant_client, mock_redis_client):
    ctx = MaintenanceContext(qdrant_client=mock_qdrant_client, redis_client=mock_redis_client, dry_run=False)

    # First apply: updates collections with m=0
    res1 = run_operation("qdrant-contract-v1", dry_run=False, ctx=ctx)
    assert res1.status == "SUCCESS"
    assert res1.exit_code == ExitCode.SUCCESS
    assert mock_qdrant_client.update_collection.call_count >= 1

    # Second apply: simulate collections already having m=16
    mock_qdrant_client.update_collection.reset_mock()
    info_m16 = MagicMock()
    info_m16.config.hnsw_config.m = 16
    mock_qdrant_client.get_collection.return_value = info_m16
    # Also simulate semantic_query_cache exists now
    mock_qdrant_client.get_collections.return_value = MagicMock(
        collections=[
            MockCollection("spiritual_wisdom"),
            MockCollection("semantic_query_cache"),
            MockCollection("lightrag_vdb_entities_baai_bge_m3_1024d"),
            MockCollection("lightrag_vdb_relationships_baai_bge_m3_1024d"),
            MockCollection("lightrag_vdb_chunks_baai_bge_m3_1024d"),
        ]
    )

    res2 = run_operation("qdrant-contract-v1", dry_run=False, ctx=ctx)
    assert res2.status == "SUCCESS"
    assert res2.exit_code == ExitCode.SUCCESS
    # Should not re-patch collections that are already m=16
    mock_qdrant_client.update_collection.assert_not_called()


def test_neo4j_ontology_apply_and_idempotency(mock_neo4j_driver, mock_redis_client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "neo4j_uri", "bolt://test", raising=False)
    ctx = MaintenanceContext(neo4j_driver=mock_neo4j_driver, redis_client=mock_redis_client, dry_run=False)
    with patch("app.db.seed_ontology.seed_spiritual_ontology") as mock_seed:
        # Run 1
        res1 = run_operation("neo4j-ontology-schema-v1", dry_run=False, ctx=ctx)
        assert res1.status == "SUCCESS"
        assert res1.exit_code == ExitCode.SUCCESS
        assert mock_seed.call_count == 1

        # Run 2 (idempotent re-run)
        res2 = run_operation("neo4j-ontology-schema-v1", dry_run=False, ctx=ctx)
        assert res2.status == "SUCCESS"
        assert res2.exit_code == ExitCode.SUCCESS
        assert mock_seed.call_count == 2


def test_qdrant_payload_indexes_apply_and_idempotency(mock_qdrant_client, mock_redis_client):
    ctx = MaintenanceContext(qdrant_client=mock_qdrant_client, redis_client=mock_redis_client, dry_run=False)

    # First apply
    res1 = run_operation("qdrant-payload-indexes-v1", dry_run=False, ctx=ctx)
    assert res1.status == "SUCCESS"
    assert res1.exit_code == ExitCode.SUCCESS
    total_fields = len(QdrantPayloadIndexesOperation.INT_FIELDS) + len(QdrantPayloadIndexesOperation.KW_FIELDS)
    assert mock_qdrant_client.create_payload_index.call_count == total_fields

    # Second apply: indexes exist (mock raises conflict / already exists)
    mock_qdrant_client.create_payload_index.side_effect = Exception("Index already exists")
    res2 = run_operation("qdrant-payload-indexes-v1", dry_run=False, ctx=ctx)
    assert res2.status == "SUCCESS"
    assert res2.exit_code == ExitCode.SUCCESS


def test_lightrag_entity_dedup_apply_and_idempotency(mock_redis_client):
    mock_rag = MagicMock()
    ctx = MaintenanceContext(lightrag_instance=mock_rag, redis_client=mock_redis_client, dry_run=False)

    # First apply
    res1 = run_operation("lightrag-entity-dedup-v1", dry_run=False, ctx=ctx)
    assert res1.status == "SUCCESS"
    assert res1.exit_code == ExitCode.SUCCESS
    assert mock_rag.merge_entities.call_count == len(LightRAGEntityDedupOperation.ENTITY_MERGES)

    # Second apply
    mock_rag.merge_entities.reset_mock()
    res2 = run_operation("lightrag-entity-dedup-v1", dry_run=False, ctx=ctx)
    assert res2.status == "SUCCESS"
    assert res2.exit_code == ExitCode.SUCCESS
    assert mock_rag.merge_entities.call_count == len(LightRAGEntityDedupOperation.ENTITY_MERGES)


def test_cleanup_stale_collections_apply_and_idempotency(mock_qdrant_client, mock_redis_client):
    # Stale collections present
    mock_qdrant_client.get_collections.return_value = MagicMock(
        collections=[
            MockCollection("spiritual_wisdom"),
            MockCollection("lightrag_vdb_entities_intfloat_multilingual_e5_small_384d"),
            MockCollection("semantic_query_cache"),
        ]
    )
    col_info = MagicMock()
    col_info.points_count = 0
    mock_qdrant_client.get_collection.return_value = col_info

    ctx = MaintenanceContext(qdrant_client=mock_qdrant_client, redis_client=mock_redis_client, dry_run=False, force=True)

    # First apply: deletes stale 384d and empty semantic_query_cache
    res1 = run_operation("cleanup-stale-collections-v1", dry_run=False, ctx=ctx)
    assert res1.status == "SUCCESS"
    assert res1.exit_code == ExitCode.SUCCESS
    assert mock_qdrant_client.delete_collection.call_count == 2

    # Second apply: stale collections gone
    mock_qdrant_client.delete_collection.reset_mock()
    mock_qdrant_client.get_collections.return_value = MagicMock(
        collections=[MockCollection("spiritual_wisdom")]
    )
    res2 = run_operation("cleanup-stale-collections-v1", dry_run=False, ctx=ctx)
    assert res2.status == "SUCCESS"
    assert res2.exit_code == ExitCode.SUCCESS
    mock_qdrant_client.delete_collection.assert_not_called()


def test_cleanup_stale_collections_apply_requires_force(mock_qdrant_client, mock_redis_client):
    # Stale collections present but --force not set: must SKIP without deleting
    mock_qdrant_client.get_collections.return_value = MagicMock(
        collections=[
            MockCollection("spiritual_wisdom"),
            MockCollection("lightrag_vdb_entities_intfloat_multilingual_e5_small_384d"),
        ]
    )
    col_info = MagicMock()
    col_info.points_count = 0
    mock_qdrant_client.get_collection.return_value = col_info

    ctx = MaintenanceContext(qdrant_client=mock_qdrant_client, redis_client=mock_redis_client, dry_run=False)

    res = run_operation("cleanup-stale-collections-v1", dry_run=False, ctx=ctx)
    assert res.status == "SKIPPED"
    assert res.exit_code == ExitCode.SUCCESS
    mock_qdrant_client.delete_collection.assert_not_called()


# =============================================================================
# 4. Distributed Redis Lock Tests
# =============================================================================

def test_lock_prevents_concurrent_execution(mock_qdrant_client):
    mock_redis = MagicMock()
    # Simulate lock held by another process: set with nx=True returns None
    mock_redis.set.return_value = None

    ctx = MaintenanceContext(qdrant_client=mock_qdrant_client, redis_client=mock_redis, dry_run=False)
    res = run_operation("qdrant-contract-v1", dry_run=False, ctx=ctx)

    assert res.status == "LOCK_HELD"
    assert res.exit_code == ExitCode.LOCK_HELD
    mock_qdrant_client.update_collection.assert_not_called()


def test_lock_acquire_and_release(mock_redis_client):
    lock = DistributedLock(mock_redis_client, "test-op", ttl_seconds=300)
    assert lock.acquire() is True
    assert lock.acquired is True
    assert lock.release() is True


def test_lock_redis_error_returns_precondition_failed(mock_qdrant_client):
    mock_redis = MagicMock()
    mock_redis.set.side_effect = Exception("Connection refused")

    ctx = MaintenanceContext(qdrant_client=mock_qdrant_client, redis_client=mock_redis, dry_run=False)
    res = run_operation("qdrant-contract-v1", dry_run=False, ctx=ctx)

    assert res.status == "PRECONDITION_FAILED"
    assert res.exit_code == ExitCode.PRECONDITION_FAILED
    assert "Connection refused" in res.details.get("reason", "")
    mock_qdrant_client.update_collection.assert_not_called()


def test_lock_error_with_force_proceeds(mock_qdrant_client):
    mock_redis = MagicMock()
    mock_redis.set.side_effect = Exception("Connection refused")

    ctx = MaintenanceContext(qdrant_client=mock_qdrant_client, redis_client=mock_redis, dry_run=False, force=True)
    res = run_operation("qdrant-contract-v1", dry_run=False, ctx=ctx)

    assert res.status == "SUCCESS"
    assert res.exit_code == ExitCode.SUCCESS
    assert mock_qdrant_client.update_collection.call_count >= 1


# =============================================================================
# 5. Precondition Failure Handling
# =============================================================================

def test_precondition_failure_when_qdrant_unreachable():
    failing_client = MagicMock()
    failing_client.get_collections.side_effect = Exception("Connection refused")

    ctx = MaintenanceContext(qdrant_client=failing_client, dry_run=True)
    res = run_operation("qdrant-contract-v1", dry_run=True, ctx=ctx)

    assert res.status == "PRECONDITION_FAILED"
    assert res.exit_code == ExitCode.PRECONDITION_FAILED


def test_unknown_operation_returns_invalid_operation():
    res = run_operation("non-existent-op-v99", dry_run=True)
    assert res.status == "FAILED"
    assert res.exit_code == ExitCode.INVALID_OPERATION


# =============================================================================
# 6. Read-Only Startup Guarantee in app.main
# =============================================================================

@pytest.mark.asyncio
async def test_startup_body_does_not_execute_maintenance_mutations():
    """Verify that _background_startup_body in app.main makes 0 schema/collection mutations."""
    from app.main import _background_startup_body

    mock_container = MagicMock()
    mock_qdrant_svc = MagicMock()
    mock_qclient = MagicMock()
    mock_qdrant_svc._client = mock_qclient
    mock_container.qdrant = mock_qdrant_svc
    mock_container.job_queue = None
    mock_container.llm_queue = None
    mock_container.request_queue = None
    mock_container.embedding = MagicMock()
    mock_container.embedding.encode_single.return_value = [0.0] * 1024

    mock_app = MagicMock()

    with patch("app.db.seed_ontology.seed_spiritual_ontology") as mock_seed, \
         patch("app.main.init_observability") as mock_obs, \
         patch("app.main.telemetry_worker.start") as mock_tel, \
         patch("services.config_watcher.start_config_watcher", new=AsyncMock()):

        await _background_startup_body(mock_container, mock_app)

        # 1. Neo4j ontology seeding must NOT be called on startup
        mock_seed.assert_not_called()

        # 2. Qdrant mutations must NOT be called on startup
        mock_qclient.update_collection.assert_not_called()
        mock_qclient.create_collection.assert_not_called()
        mock_qclient.delete_collection.assert_not_called()
        mock_qclient.create_payload_index.assert_not_called()

        # 3. LightRAG entity merge must NOT be called on startup
        if hasattr(mock_container, "lightrag") and hasattr(mock_container.lightrag, "_rag"):
            mock_container.lightrag._rag.merge_entities.assert_not_called()
