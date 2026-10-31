"""Ingestion Isolation & Safe Rollback Matrix Tests.

Covers the specification in SPEC-ingestion-isolation.md:
- Target collection isolation: target in {default, scratch}
- Source state in {new, existing}
- Downstream in {success, injected failure}
- Probe failures and backup failures fail closed (SafeIngestionAbort)
- Rollback cleanly restores (existing) or deletes (new) on selected target only
- Snapshot namespaces across collections never collide
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ingest.pipeline import IngestionPipeline, SafeIngestionAbort


def _make_mock_qdrant(collection: str = "spiritual_wisdom") -> MagicMock:
    """Create a mock Qdrant service simulating isolated collection operations."""
    mock = MagicMock()
    mock._collection = collection
    mock.check_source_exists = MagicMock(return_value=False)
    mock.backup_source = MagicMock(return_value=True)
    mock.prune_backups = MagicMock(return_value=None)
    mock.restore_from_backup = MagicMock(return_value=True)
    mock.delete_by_source = MagicMock(return_value=None)
    mock.upsert_chunks = MagicMock(return_value=1)
    return mock


@pytest.fixture
def mock_pipeline_env(monkeypatch):
    """Setup pipeline with isolated mocks and common patch points."""
    from app.config import settings

    monkeypatch.setattr(settings, "use_adaptive_chunking", False)
    monkeypatch.setattr(settings, "use_boundary_chunker", False)
    monkeypatch.setattr(settings, "use_hyper_extract_enrichment", False)
    monkeypatch.setattr(
        "ingest.pipeline.IngestionCheckpoint.acquire_lock",
        lambda self, lock_key, ttl=3600: "mock_token",
    )
    monkeypatch.setattr(
        "ingest.pipeline.IngestionCheckpoint.release_lock",
        lambda self, lock_key, lock_token: True,
    )
    monkeypatch.setattr(
        "ingest.pipeline.IngestionCheckpoint.is_processed",
        lambda self, chunk_id: False,
    )
    monkeypatch.setattr(
        "ingest.pipeline.IngestionCheckpoint.save",
        lambda self, chunk_id, metadata=None: None,
    )
    monkeypatch.setattr("ingest.pipeline.is_valid_text_deterministic", lambda text: (True, ""))
    monkeypatch.setattr("ingest.pipeline.clean_transcript", lambda text: text)

    default_qdrant = _make_mock_qdrant(collection="spiritual_wisdom")
    scratch_qdrant = _make_mock_qdrant(collection="scratch_test_collection")

    # Patch QdrantService in ingest.pipeline so scratch requests get scratch_qdrant
    def _qdrant_factory(collection=None, client=None):
        if collection == "scratch_test_collection":
            return scratch_qdrant
        return _make_mock_qdrant(collection=collection or "spiritual_wisdom")

    monkeypatch.setattr("ingest.pipeline.QdrantService", _qdrant_factory)

    embedder = MagicMock()
    embedder.encode_batch = MagicMock(return_value={"dense": [[0.1] * 384], "sparse": [None]})
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value='{"score": 90, "verdict": "PASS", "is_spiritual": true, "coherence": "high", "reasons": ["Coherent"]}'
    )

    pipeline = IngestionPipeline(default_qdrant, embedder, llm)
    pipeline._auditor.run = AsyncMock(return_value=MagicMock(passed=True, score=90, reasons=[]))
    pipeline._raptor.build_tree = AsyncMock(return_value=1)
    pipeline._raptor.summarize_parent_chunks = AsyncMock(side_effect=lambda chunks: chunks)
    pipeline._lightrag = None
    pipeline._implicit_teachings_connector = AsyncMock()
    pipeline._consolidate_graph_entities = AsyncMock()

    # Also patch RaptorIndexer so scratch doesn't make real LLM/embedder calls
    def _raptor_factory(emb, l_model, q_service):
        mock_raptor = MagicMock()
        mock_raptor.build_tree = AsyncMock(return_value=1)
        mock_raptor.summarize_parent_chunks = AsyncMock(side_effect=lambda chunks: chunks)
        return mock_raptor

    monkeypatch.setattr("ingest.pipeline.RaptorIndexer", _raptor_factory)

    return {
        "pipeline": pipeline,
        "default_qdrant": default_qdrant,
        "scratch_qdrant": scratch_qdrant,
    }


# ==============================================================================
# 1. Unit Tests for _backup_before_reindex and _rollback_reindex
# ==============================================================================


def test_backup_probe_failure_raises_safe_ingestion_abort():
    """Probe failure (exception on check_source_exists) must fail closed."""
    qdrant = _make_mock_qdrant()
    qdrant.check_source_exists.side_effect = RuntimeError("Qdrant connection timeout")
    pipeline = IngestionPipeline(qdrant, MagicMock(), MagicMock())

    with pytest.raises(SafeIngestionAbort) as exc_info:
        pipeline._backup_before_reindex("https://example.com/probe-fail")

    assert "Source existence probe failed" in str(exc_info.value)
    assert qdrant.backup_source.call_count == 0


def test_backup_new_source_returns_none():
    """Unindexed source returns None and performs no backup."""
    qdrant = _make_mock_qdrant()
    qdrant.check_source_exists.return_value = False
    pipeline = IngestionPipeline(qdrant, MagicMock(), MagicMock())

    result = pipeline._backup_before_reindex("https://example.com/new-source")
    assert result is None
    assert qdrant.backup_source.call_count == 0
    assert qdrant.prune_backups.call_count == 0


def test_backup_existing_source_success():
    """Existing source triggers backup and pruning, returning collection name."""
    qdrant = _make_mock_qdrant(collection="spiritual_wisdom")
    qdrant.check_source_exists.return_value = True
    qdrant.backup_source.return_value = True
    pipeline = IngestionPipeline(qdrant, MagicMock(), MagicMock())

    backup_coll = pipeline._backup_before_reindex("https://example.com/existing-source")
    assert backup_coll is not None
    assert backup_coll.startswith("spiritual_wisdom_ingest_backup_")

    qdrant.backup_source.assert_called_once_with("https://example.com/existing-source", backup_coll)
    qdrant.prune_backups.assert_called_once_with("spiritual_wisdom_ingest_backup", max_backups=5)


def test_backup_failure_on_existing_source_raises_safe_ingestion_abort():
    """If backup_source returns False, SafeIngestionAbort must be raised."""
    qdrant = _make_mock_qdrant(collection="spiritual_wisdom")
    qdrant.check_source_exists.return_value = True
    qdrant.backup_source.return_value = False
    pipeline = IngestionPipeline(qdrant, MagicMock(), MagicMock())

    with pytest.raises(SafeIngestionAbort) as exc_info:
        pipeline._backup_before_reindex("https://example.com/backup-fail")

    assert "Pre-reindex backup failed for existing source" in str(exc_info.value)
    assert "spiritual_wisdom" in str(exc_info.value)


def test_backup_exception_on_existing_source_raises_safe_ingestion_abort():
    """If backup_source raises an exception, SafeIngestionAbort must be raised."""
    qdrant = _make_mock_qdrant(collection="scratch_test")
    qdrant.check_source_exists.return_value = True
    qdrant.backup_source.side_effect = OSError("Qdrant disk write failed")
    pipeline = IngestionPipeline(qdrant, MagicMock(), MagicMock())

    with pytest.raises(SafeIngestionAbort) as exc_info:
        pipeline._backup_before_reindex("https://example.com/backup-err", qdrant_service=qdrant)

    assert "Pre-reindex backup failed for existing source" in str(exc_info.value)
    assert "scratch_test" in str(exc_info.value)


def test_rollback_reindex_with_backup_restores():
    """When backup_collection is present, restore_from_backup is invoked."""
    default_qdrant = _make_mock_qdrant()
    scratch_qdrant = _make_mock_qdrant(collection="scratch_target")
    pipeline = IngestionPipeline(default_qdrant, MagicMock(), MagicMock())

    pipeline._rollback_reindex(
        "https://example.com/item", "scratch_target_backup_20261027", qdrant_service=scratch_qdrant
    )

    scratch_qdrant.restore_from_backup.assert_called_once_with(
        "https://example.com/item", "scratch_target_backup_20261027"
    )
    scratch_qdrant.delete_by_source.assert_not_called()
    default_qdrant.restore_from_backup.assert_not_called()
    default_qdrant.delete_by_source.assert_not_called()


def test_rollback_reindex_without_backup_deletes():
    """When backup_collection is None, delete_by_source is invoked."""
    default_qdrant = _make_mock_qdrant()
    scratch_qdrant = _make_mock_qdrant(collection="scratch_target")
    pipeline = IngestionPipeline(default_qdrant, MagicMock(), MagicMock())

    pipeline._rollback_reindex("https://example.com/new-item", None, qdrant_service=scratch_qdrant)

    scratch_qdrant.delete_by_source.assert_called_once_with(
        source_url="https://example.com/new-item"
    )
    scratch_qdrant.restore_from_backup.assert_not_called()
    default_qdrant.restore_from_backup.assert_not_called()
    default_qdrant.delete_by_source.assert_not_called()


def test_snapshots_across_default_vs_scratch_do_not_collide():
    """Snapshots for the same source across different target collections have distinct namespaces."""
    default_qdrant = _make_mock_qdrant(collection="spiritual_wisdom")
    scratch_qdrant = _make_mock_qdrant(collection="scratch_target")
    default_qdrant.check_source_exists.return_value = True
    scratch_qdrant.check_source_exists.return_value = True

    pipeline = IngestionPipeline(default_qdrant, MagicMock(), MagicMock())

    def_backup = pipeline._backup_before_reindex("https://example.com/shared")
    scratch_backup = pipeline._backup_before_reindex(
        "https://example.com/shared", qdrant_service=scratch_qdrant
    )

    assert def_backup != scratch_backup
    assert def_backup.startswith("spiritual_wisdom_ingest_backup_")
    assert scratch_backup.startswith("scratch_target_ingest_backup_")

    default_qdrant.backup_source.assert_called_once_with("https://example.com/shared", def_backup)
    scratch_qdrant.backup_source.assert_called_once_with(
        "https://example.com/shared", scratch_backup
    )


# ==============================================================================
# 2. Matrix Tests: target × source × downstream
# ==============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["default", "scratch"])
@pytest.mark.parametrize("source_state", ["new", "existing"])
@pytest.mark.parametrize("downstream", ["success", "failure"])
async def test_ingest_raw_text_matrix(
    mock_pipeline_env, monkeypatch, target: str, source_state: str, downstream: str
):
    """Test full matrix of target {default, scratch} × source {new, existing} × downstream {success, failure}."""
    pipeline: IngestionPipeline = mock_pipeline_env["pipeline"]
    default_qdrant: MagicMock = mock_pipeline_env["default_qdrant"]
    scratch_qdrant: MagicMock = mock_pipeline_env["scratch_qdrant"]

    is_scratch = target == "scratch"
    qdrant_collection = "scratch_test_collection" if is_scratch else None
    active_service = scratch_qdrant if is_scratch else default_qdrant
    idle_service = default_qdrant if is_scratch else scratch_qdrant

    is_existing = source_state == "existing"
    active_service.check_source_exists.return_value = is_existing

    # Configure downstream failure if requested
    if downstream == "failure":
        # Inject downstream failure during RAPTOR tree build
        if is_scratch:
            # raptor_override was created for scratch
            def _failing_raptor_factory(emb, l_model, q_service):
                mock_raptor = MagicMock()
                mock_raptor.build_tree = AsyncMock(
                    side_effect=RuntimeError("Injected downstream failure")
                )
                mock_raptor.summarize_parent_chunks = AsyncMock(side_effect=lambda chunks: chunks)
                return mock_raptor

            monkeypatch.setattr("ingest.pipeline.RaptorIndexer", _failing_raptor_factory)
        else:
            pipeline._raptor.build_tree = AsyncMock(
                side_effect=RuntimeError("Injected downstream failure")
            )

    source_url = f"https://example.com/test-{target}-{source_state}-{downstream}"
    text = (
        "Spiritual wisdom teaching about presence, awareness, and universal truth. "
        "Mindfulness brings calmness to every moment of contemplation and peace."
    )

    result = await pipeline.ingest_raw_text(
        text=text,
        source_url=source_url,
        title="Matrix Test Doc",
        qdrant_collection=qdrant_collection,
    )

    # 1. Target isolation check: idle service MUST have zero calls
    assert idle_service.check_source_exists.call_count == 0
    assert idle_service.backup_source.call_count == 0
    assert idle_service.restore_from_backup.call_count == 0
    assert idle_service.delete_by_source.call_count == 0
    assert idle_service.upsert_chunks.call_count == 0

    # 2. Check source probe on active service
    assert active_service.check_source_exists.call_count >= 1
    active_service.check_source_exists.assert_any_call(source_url)

    # 3. Source state behavior
    if is_existing:
        assert active_service.backup_source.call_count == 1
        call_backup_coll = active_service.backup_source.call_args[0][1]
        expected_prefix = (
            "scratch_test_collection_ingest_backup"
            if is_scratch
            else "spiritual_wisdom_ingest_backup"
        )
        assert call_backup_coll.startswith(expected_prefix)
    else:
        assert active_service.backup_source.call_count == 0

    # 4. Downstream outcome
    if downstream == "success":
        assert result["status"] == "success"
        assert active_service.upsert_chunks.call_count >= 1
        assert active_service.delete_by_source.call_count == 0
        assert active_service.restore_from_backup.call_count == 0
    else:
        assert result["status"] == "error"
        assert "Ingestion rolled back" in result["message"]
        if is_existing:
            # Rolled back by restoring backup
            assert active_service.restore_from_backup.call_count == 1
            assert active_service.delete_by_source.call_count == 0
        else:
            # Rolled back by deleting partial new points
            assert active_service.delete_by_source.call_count == 1
            assert active_service.restore_from_backup.call_count == 0


# ==============================================================================
# 3. Safety Gate Abort Tests in ingest_raw_text
# ==============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["default", "scratch"])
async def test_ingest_raw_text_aborts_on_backup_failure(mock_pipeline_env, target: str):
    """When backup fails for an existing source, ingestion must abort immediately without writes."""
    pipeline: IngestionPipeline = mock_pipeline_env["pipeline"]
    default_qdrant: MagicMock = mock_pipeline_env["default_qdrant"]
    scratch_qdrant: MagicMock = mock_pipeline_env["scratch_qdrant"]

    is_scratch = target == "scratch"
    qdrant_collection = "scratch_test_collection" if is_scratch else None
    active_service = scratch_qdrant if is_scratch else default_qdrant

    active_service.check_source_exists.return_value = True
    active_service.backup_source.return_value = False  # Backup fails

    result = await pipeline.ingest_raw_text(
        text="Teaching about stillness and awareness in the present moment.",
        source_url="https://example.com/backup-fail-abort",
        title="Backup Fail Test",
        qdrant_collection=qdrant_collection,
    )

    assert result["status"] == "error"
    assert "safety gate prevented overwrite" in result["message"]
    assert result["chunks_indexed"] == 0

    # Crucial safety invariants:
    # No upsert into Qdrant occurred
    assert active_service.upsert_chunks.call_count == 0
    # No delete occurred
    assert active_service.delete_by_source.call_count == 0
    # The other service was not touched
    idle_service = default_qdrant if is_scratch else scratch_qdrant
    assert idle_service.check_source_exists.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["default", "scratch"])
async def test_ingest_raw_text_aborts_on_probe_exception(mock_pipeline_env, target: str):
    """When existence probe raises an exception, ingestion must abort immediately without writes."""
    pipeline: IngestionPipeline = mock_pipeline_env["pipeline"]
    default_qdrant: MagicMock = mock_pipeline_env["default_qdrant"]
    scratch_qdrant: MagicMock = mock_pipeline_env["scratch_qdrant"]

    is_scratch = target == "scratch"
    qdrant_collection = "scratch_test_collection" if is_scratch else None
    active_service = scratch_qdrant if is_scratch else default_qdrant

    active_service.check_source_exists.side_effect = RuntimeError("Qdrant service unreachable")

    result = await pipeline.ingest_raw_text(
        text="Teaching about stillness and awareness in the present moment.",
        source_url="https://example.com/probe-fail-abort",
        title="Probe Fail Test",
        qdrant_collection=qdrant_collection,
    )

    assert result["status"] == "error"
    assert "safety gate prevented overwrite" in result["message"]
    assert result["chunks_indexed"] == 0

    # Crucial safety invariants:
    # No backup attempted
    assert active_service.backup_source.call_count == 0
    # No upsert into Qdrant occurred
    assert active_service.upsert_chunks.call_count == 0
    # No delete occurred
    assert active_service.delete_by_source.call_count == 0


# ==============================================================================
# 4. Abort Safety Gates on Video & Playlist Paths
# ==============================================================================


@pytest.mark.asyncio
async def test_ingest_video_aborts_on_safe_ingestion_abort(mock_pipeline_env, monkeypatch):
    """_ingest_video catches SafeIngestionAbort and returns error without proceeding."""
    pipeline: IngestionPipeline = mock_pipeline_env["pipeline"]
    pipeline._backup_before_reindex = MagicMock(
        side_effect=SafeIngestionAbort("Pre-reindex backup failed for existing source")
    )
    pipeline._hierarchical_split = MagicMock(return_value=(["chunk one"], [{"is_child": False}]))

    monkeypatch.setattr(
        "ingest.pipeline.fetch_transcript_hybrid",
        lambda video_id, title="", max_accuracy=False: {
            "text": "A valid transcript for spiritual discourse about presence."
        },
    )
    monkeypatch.setattr(
        "ingest.pipeline.extract_video_metadata",
        lambda text, vid, metadata_enrichment=False: {
            "title": "Discourse",
            "speaker": "Guru",
            "language": "en",
        },
    )
    monkeypatch.setattr(
        "ingest.chunkers.youtube_chunker.chunk_youtube_transcript",
        lambda video_id, text, chunk_size=0, chunk_overlap=0, languages=None: [
            {"text": "chunk one"}
        ],
    )

    result = await pipeline._ingest_video("https://youtube.com/watch?v=dQw4w9WgXcQ")
    assert result["status"] == "error"
    assert "safety gate prevented overwrite" in result["message"]
    assert result["chunks_indexed"] == 0


@pytest.mark.asyncio
async def test_ingest_playlist_aborts_per_video_on_safe_ingestion_abort(
    mock_pipeline_env, monkeypatch
):
    """_ingest_playlist catches SafeIngestionAbort for a video, appends error, and continues."""
    pipeline: IngestionPipeline = mock_pipeline_env["pipeline"]
    pipeline._backup_before_reindex = MagicMock(
        side_effect=SafeIngestionAbort("Pre-reindex backup failed for video")
    )
    pipeline._split_text = MagicMock(return_value=["chunk 1"])

    monkeypatch.setattr(
        "ingest.pipeline.get_playlist_video_urls",
        lambda url: [{"url": "https://youtube.com/watch?v=dQw4w9WgXcQ", "title": "Vid 1"}],
    )
    monkeypatch.setattr(
        "ingest.pipeline.fetch_transcripts_concurrent",
        AsyncMock(
            return_value=[{"text": "Transcript of video one in playlist", "method": "caption"}]
        ),
    )

    result = await pipeline._ingest_playlist("https://youtube.com/playlist?list=PL123")
    assert result["status"] == "success"
    assert result["videos_failed"] == 1
    assert result["chunks_indexed"] == 0
