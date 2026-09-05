from unittest.mock import MagicMock, patch

from ingest.pipeline import IngestionCheckpoint, IngestionPipeline


def test_checkpoint_redis_primary():
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True

    with (
        patch("redis.from_url", return_value=mock_redis),
        patch("app.config.settings.redis_url", "redis://localhost:6379/0"),
    ):
        checkpoint = IngestionCheckpoint()
        assert checkpoint.redis_client is not None
        assert checkpoint.supabase_client is None

        # Test save and check via Redis
        checkpoint.save("chunk_123", {"timestamp": 12345})
        mock_redis.set.assert_called_once()

        checkpoint.is_processed("chunk_123")
        mock_redis.exists.assert_called_once()


def test_checkpoint_supabase_fallback():
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table

    # Mock Redis failure, but Supabase active
    with (
        patch("redis.from_url", side_effect=Exception("Redis down")),
        patch("supabase.create_client", return_value=mock_supabase),
        patch("app.config.settings.redis_url", "redis://localhost:6379/0"),
        patch("app.config.settings.supabase_url", "http://localhost:54321"),
        patch("app.config.settings.supabase_key", "service-key"),
    ):
        checkpoint = IngestionCheckpoint()
        assert checkpoint.redis_client is None
        assert checkpoint.supabase_client is not None

        # Test save to Supabase
        checkpoint.save("chunk_abc", {"timestamp": 54321})
        mock_supabase.table.assert_called_with("ingestion_checkpoints")
        mock_table.upsert.assert_called_once()

        # Test check processed on Supabase
        mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"chunk_id": "chunk_abc"}])
        )
        processed = checkpoint.is_processed("chunk_abc")
        assert processed is True


def test_checkpoint_json_fallback(tmp_path):
    checkpoint_file = tmp_path / "ingest_checkpoint.json"

    # Mock both failure
    with (
        patch("redis.from_url", side_effect=Exception("Redis down")),
        patch("supabase.create_client", side_effect=Exception("Supabase down")),
    ):
        checkpoint = IngestionCheckpoint(filepath=str(checkpoint_file))
        assert checkpoint.redis_client is None
        assert checkpoint.supabase_client is None

        # Test save to JSON
        checkpoint.save("chunk_xyz", {"timestamp": 9999})
        assert checkpoint_file.exists()

        # Test check processed on JSON
        processed = checkpoint.is_processed("chunk_xyz")
        assert processed is True

        processed_not_existing = checkpoint.is_processed("chunk_missing")
        assert processed_not_existing is False


def test_playlist_checkpoint_uses_the_same_scoped_key_for_read_and_write():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "ingest" / "pipeline.py").read_text(
        encoding="utf-8"
    )
    # The current implementation keys both operations by the content hash so
    # the same source version/corpus scope is used for read and write.
    assert "checkpoint.is_processed(self._checkpoint_key(content_hash))" in source
    assert "checkpoint.save(self._checkpoint_key(content_hash))" in source


def test_checkpoint_key_isolated_by_corpus_and_source_version():
    pipeline = object.__new__(IngestionPipeline)
    pipeline._corpus_id = "preethaji-approved"

    release_one = pipeline._checkpoint_key("same-content-hash", source_version=1)
    release_two = pipeline._checkpoint_key("same-content-hash", source_version=2)

    assert release_one == "preethaji-approved:v1:same-content-hash"
    assert release_two == "preethaji-approved:v2:same-content-hash"
    assert release_one != release_two


def test_checkpoint_json_isolated_by_tenant(tmp_path):
    import json

    checkpoint_file = tmp_path / "ingest_checkpoint.json"

    with (
        patch("redis.from_url", side_effect=Exception("Redis down")),
        patch("supabase.create_client", side_effect=Exception("Supabase down")),
    ):
        default_ckpt = IngestionCheckpoint(filepath=str(checkpoint_file))
        other_ckpt = IngestionCheckpoint(filepath=str(checkpoint_file))
        other_ckpt.tenant_id = "teacher-a"

        default_ckpt.save("chunk_xyz", {"timestamp": 1})
        assert default_ckpt.is_processed("chunk_xyz") is True
        # Same chunk id under another tenant must not collide.
        assert other_ckpt.is_processed("chunk_xyz") is False

        other_ckpt.save("chunk_xyz", {"timestamp": 2})
        assert other_ckpt.is_processed("chunk_xyz") is True
        assert default_ckpt.is_processed("chunk_xyz") is True

        # File must contain both tenant-qualified entries, no unqualified key.
        stored = json.loads(checkpoint_file.read_text())
        assert f"tenant:{default_ckpt.tenant_id}:chunk_xyz" in stored
        assert f"tenant:{other_ckpt.tenant_id}:chunk_xyz" in stored
        assert "chunk_xyz" not in stored


def test_checkpoint_json_migrates_legacy_unqualified_keys(tmp_path):
    import json

    checkpoint_file = tmp_path / "ingest_checkpoint.json"
    checkpoint_file.write_text(json.dumps({"legacy-hash": {"timestamp": 1}}))

    with (
        patch("redis.from_url", side_effect=Exception("Redis down")),
        patch("supabase.create_client", side_effect=Exception("Supabase down")),
    ):
        ckpt = IngestionCheckpoint(filepath=str(checkpoint_file))
        assert ckpt.is_processed("legacy-hash") is True
        assert ckpt.is_processed("unrelated-hash") is False


def test_checkpoint_json_legacy_keys_migrate_to_default_tenant(tmp_path):
    import json

    checkpoint_file = tmp_path / "ingest_checkpoint.json"
    checkpoint_file.write_text(json.dumps({"legacy-hash": {"timestamp": 1}}))

    with (
        patch("redis.from_url", side_effect=Exception("Redis down")),
        patch("supabase.create_client", side_effect=Exception("Supabase down")),
        patch("app.config.settings.default_tenant_id", "configured-default"),
        patch("services.tenant_context.TenantContext.get", return_value="teacher-a"),
    ):
        teacher_ckpt = IngestionCheckpoint(filepath=str(checkpoint_file))
        assert teacher_ckpt.tenant_id == "teacher-a"

        # Legacy keys belong to the default tenant, not the loading instance.
        assert teacher_ckpt.is_processed("legacy-hash") is False

        stored = json.loads(checkpoint_file.read_text())
        assert "tenant:configured-default:legacy-hash" in stored
        assert "tenant:teacher-a:legacy-hash" not in stored

    with (
        patch("redis.from_url", side_effect=Exception("Redis down")),
        patch("supabase.create_client", side_effect=Exception("Supabase down")),
        patch("app.config.settings.default_tenant_id", "configured-default"),
        patch("services.tenant_context.TenantContext.get", return_value=None),
    ):
        default_ckpt = IngestionCheckpoint(filepath=str(checkpoint_file))
        assert default_ckpt.tenant_id == "configured-default"
        assert default_ckpt.is_processed("legacy-hash") is True


def test_checkpoint_failed_and_error_status_eligible_for_retry(tmp_path):
    checkpoint_file = tmp_path / "ingest_checkpoint.json"

    with (
        patch("redis.from_url", side_effect=Exception("Redis down")),
        patch("supabase.create_client", side_effect=Exception("Supabase down")),
    ):
        ckpt = IngestionCheckpoint(filepath=str(checkpoint_file))
        ckpt.save("success_chunk", {"status": "success", "chunks": 5})
        ckpt.save("failed_chunk", {"status": "failed", "error": "LLM rate limited"})
        ckpt.save("error_chunk", {"status": "error", "error": "Connection timeout"})

        assert ckpt.is_processed("success_chunk") is True
        assert ckpt.is_processed("failed_chunk") is False
        assert ckpt.is_processed("error_chunk") is False


def test_is_processed_falls_through_redis_miss_to_local_file(tmp_path):
    """production-audit finding checkpoint-multitier-fallback-broken: a clean
    miss at Redis must fall through to the local-file tier, not short-circuit
    to False — save() writes to exactly one tier, so a chunk saved to the file
    fallback during a Redis outage would otherwise be reported unprocessed as
    soon as Redis answers again."""
    checkpoint_file = tmp_path / "ingest_checkpoint.json"
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.exists.return_value = False  # clean miss, not an error

    with (
        patch("redis.from_url", return_value=mock_redis),
        patch("app.config.settings.redis_url", "redis://localhost:6379/0"),
    ):
        ckpt = IngestionCheckpoint(filepath=str(checkpoint_file))
        assert ckpt.redis_client is not None
        # Written directly to the local-file tier (as if Redis was down at save time).
        ckpt.data[ckpt._qualify_chunk_id("file_only_chunk")] = {"status": "success"}
        ckpt.processed_chunks.add(ckpt._qualify_chunk_id("file_only_chunk"))
        ckpt._atomic_write(ckpt.data)

        assert ckpt.is_processed("file_only_chunk") is True


def test_acquire_and_release_lock_via_redis():
    """production-audit finding IC-1: acquire_lock must use SET NX (not a
    plain SET) so a second concurrent caller for the same key is refused
    while the lease is held, and release_lock must clear it for the next
    reservation."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.set.return_value = True  # first caller: NX succeeds

    with (
        patch("redis.from_url", return_value=mock_redis),
        patch("app.config.settings.redis_url", "redis://localhost:6379/0"),
    ):
        ckpt = IngestionCheckpoint()
        assert ckpt.acquire_lock("source-1") is True
        _, kwargs = mock_redis.set.call_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex")

        mock_redis.set.return_value = False  # second caller: NX fails, already held
        assert ckpt.acquire_lock("source-1") is False

        ckpt.release_lock("source-1")
        mock_redis.delete.assert_called_once()


def test_acquire_lock_without_redis_never_blocks():
    """File-mode checkpointing is single-process, so there is no cross-process
    concurrency to guard against — acquire_lock must be a no-op success, never
    a false negative that would wrongly skip a source."""
    with (
        patch("redis.from_url", side_effect=Exception("Redis down")),
        patch("supabase.create_client", side_effect=Exception("Supabase down")),
    ):
        ckpt = IngestionCheckpoint()
        assert ckpt.redis_client is None
        assert ckpt.acquire_lock("any-source") is True
        ckpt.release_lock("any-source")  # must not raise
