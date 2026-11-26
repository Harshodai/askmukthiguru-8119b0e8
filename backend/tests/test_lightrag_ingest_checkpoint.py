"""Safety contracts for resumable LightRAG Qdrant-to-graph ingestion."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ingest_lightrag_data.py"
SPEC = importlib.util.spec_from_file_location("ingest_lightrag_data_under_test", SCRIPT)
assert SPEC and SPEC.loader
INGEST = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = INGEST
SPEC.loader.exec_module(INGEST)


def test_source_collection_defaults_to_raw_corpus_not_serving_default(monkeypatch):
    monkeypatch.delenv("LIGHTRAG_SOURCE_COLLECTION", raising=False)
    monkeypatch.setenv("QDRANT_COLLECTION", "spiritual_wisdom_contextual")
    assert INGEST.resolve_source_collection() == "spiritual_wisdom"


def test_source_collection_can_be_overridden_explicitly(monkeypatch):
    monkeypatch.setenv("LIGHTRAG_SOURCE_COLLECTION", "spiritual_wisdom_contextual")
    assert INGEST.resolve_source_collection() == "spiritual_wisdom_contextual"


def test_empty_source_collection_is_rejected(monkeypatch):
    monkeypatch.setenv("LIGHTRAG_SOURCE_COLLECTION", "   ")
    with pytest.raises(ValueError, match="LIGHTRAG_SOURCE_COLLECTION"):
        INGEST.resolve_source_collection()


def test_legacy_cursor_only_checkpoint_is_not_trusted(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(json.dumps({"next_offset": "point-12", "processed_count": 12}))
    with pytest.raises(RuntimeError, match="Legacy/incompatible"):
        INGEST.load_checkpoint("spiritual_wisdom", 100, str(tmp_path / "lightrag"), checkpoint)


def test_checkpoint_is_bound_to_source_collection(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    counters = {
        "processed": 10,
        "success": 9,
        "skipped": 1,
        "rejected": 0,
        "failed": 0,
    }
    INGEST.save_checkpoint_atomic(
        "point-10",
        counters,
        "spiritual_wisdom",
        100,
        str(tmp_path / "lightrag"),
        checkpoint_file=checkpoint,
    )
    with pytest.raises(RuntimeError, match="source_collection"):
        INGEST.load_checkpoint(
            "spiritual_wisdom_contextual",
            100,
            str(tmp_path / "lightrag"),
            checkpoint,
        )


def test_checkpoint_is_bound_to_source_point_count_and_working_directory(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    working_dir = str(tmp_path / "lightrag")
    counters = {
        "processed": 10,
        "success": 10,
        "skipped": 0,
        "rejected": 0,
        "failed": 0,
    }
    INGEST.save_checkpoint_atomic(
        "point-10",
        counters,
        "spiritual_wisdom",
        100,
        working_dir,
        checkpoint_file=checkpoint,
    )
    with pytest.raises(RuntimeError, match="source_point_count"):
        INGEST.load_checkpoint("spiritual_wisdom", 101, working_dir, checkpoint)
    with pytest.raises(RuntimeError, match="working_dir"):
        INGEST.load_checkpoint("spiritual_wisdom", 100, str(tmp_path / "other"), checkpoint)


def test_checkpoint_round_trips_completed_state_without_restarting(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    working_dir = str(tmp_path / "lightrag")
    counters = {
        "processed": 100,
        "success": 98,
        "skipped": 1,
        "rejected": 1,
        "failed": 0,
    }
    INGEST.save_checkpoint_atomic(
        None,
        counters,
        "spiritual_wisdom",
        100,
        working_dir,
        completed=True,
        checkpoint_file=checkpoint,
    )
    offset, loaded, completed = INGEST.load_checkpoint(
        "spiritual_wisdom", 100, working_dir, checkpoint
    )
    assert offset is None
    assert loaded == counters
    assert completed is True


def test_checkpoint_counter_drift_is_rejected(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    data = {
        "schema_version": 2,
        "source_collection": "spiritual_wisdom",
        "source_point_count": 100,
        "working_dir": str((tmp_path / "lightrag").resolve()),
        "next_offset": "point-10",
        "completed": False,
        "processed_count": 10,
        "success_count": 9,
        "skipped_count": 0,
        "rejected_count": 0,
    }
    checkpoint.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="do not reconcile"):
        INGEST.load_checkpoint("spiritual_wisdom", 100, str(tmp_path / "lightrag"), checkpoint)


def test_process_lock_rejects_a_second_concurrent_run(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    with INGEST.checkpoint_process_lock(checkpoint):
        with pytest.raises(RuntimeError, match="Another LightRAG ingestion process"):
            with INGEST.checkpoint_process_lock(checkpoint):
                pass


@pytest.mark.asyncio
async def test_safe_insert_false_is_retried_before_marking_success(monkeypatch):
    monkeypatch.setattr(
        INGEST, "chunk_sentences", lambda _text: ["A sufficiently long teaching chunk."]
    )
    monkeypatch.setattr(INGEST.asyncio, "sleep", AsyncMock())
    svc = SimpleNamespace(safe_ainsert=AsyncMock(side_effect=[False, True]))
    point = SimpleNamespace(
        id="point-1",
        payload={
            "text": "A sufficiently long teaching transcript about presence and awareness.",
            "source_url": "video-1",
        },
    )
    counters = {
        "processed": 0,
        "success": 0,
        "skipped": 0,
        "rejected": 0,
        "failed": 0,
    }
    result = await INGEST.process_single_point(
        svc,
        point,
        asyncio.Semaphore(1),
        asyncio.Lock(),
        counters,
        INGEST.time.time(),
        {"rate_limit_hits": 0},
        1,
    )
    assert result == "success"
    assert svc.safe_ainsert.await_count == 2
    assert counters == {
        "processed": 1,
        "success": 1,
        "skipped": 0,
        "rejected": 0,
        "failed": 0,
    }


@pytest.mark.asyncio
async def test_persistent_safe_insert_false_is_marked_retryable_failure(monkeypatch):
    monkeypatch.setattr(
        INGEST, "chunk_sentences", lambda _text: ["A sufficiently long teaching chunk."]
    )
    monkeypatch.setattr(INGEST.asyncio, "sleep", AsyncMock())
    svc = SimpleNamespace(safe_ainsert=AsyncMock(return_value=False))
    point = SimpleNamespace(
        id="point-2",
        payload={
            "text": "A sufficiently long teaching transcript about presence and awareness.",
            "source_url": "video-2",
        },
    )
    counters = {
        "processed": 0,
        "success": 0,
        "skipped": 0,
        "rejected": 0,
        "failed": 0,
    }
    result = await INGEST.process_single_point(
        svc,
        point,
        asyncio.Semaphore(1),
        asyncio.Lock(),
        counters,
        INGEST.time.time(),
        {"rate_limit_hits": 0},
        1,
    )
    assert result == "failed"
    assert svc.safe_ainsert.await_count == 2
    assert counters == {
        "processed": 1,
        "success": 0,
        "skipped": 0,
        "rejected": 0,
        "failed": 1,
    }


def test_checkpoint_write_failure_is_not_silenced(monkeypatch, tmp_path):
    checkpoint = tmp_path / "checkpoint.json"

    def fail_replace(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(INGEST.os, "replace", fail_replace)
    counters = {
        "processed": 1,
        "success": 1,
        "skipped": 0,
        "rejected": 0,
        "failed": 0,
    }
    with pytest.raises(OSError, match="disk full"):
        INGEST.save_checkpoint_atomic(
            "point-1",
            counters,
            "spiritual_wisdom",
            1,
            str(tmp_path / "lightrag"),
            checkpoint_file=checkpoint,
        )


def test_missing_checkpoint_starts_from_zero_with_not_completed_false(tmp_path):
    offset, counters, completed = INGEST.load_checkpoint(
        "spiritual_wisdom",
        10,
        str(tmp_path / "lightrag"),
        tmp_path / "missing.json",
    )
    assert offset is None
    assert counters == {
        "processed": 0,
        "success": 0,
        "skipped": 0,
        "rejected": 0,
        "failed": 0,
    }
    assert completed is False


def test_completed_checkpoint_requires_all_source_points_accounted_for(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    data = {
        "schema_version": 2,
        "source_collection": "spiritual_wisdom",
        "source_point_count": 10,
        "working_dir": str((tmp_path / "lightrag").resolve()),
        "next_offset": None,
        "completed": True,
        "processed_count": 9,
        "success_count": 9,
        "skipped_count": 0,
        "rejected_count": 0,
    }
    checkpoint.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="marked complete"):
        INGEST.load_checkpoint("spiritual_wisdom", 10, str(tmp_path / "lightrag"), checkpoint)


def test_qdrant_write_key_is_mapped_only_inside_ingestion_process(monkeypatch):
    monkeypatch.setenv("QDRANT_WRITE_API_KEY", "operator-write-token")
    monkeypatch.setenv("QDRANT_API_KEY", "old-read-token")

    INGEST.configure_qdrant_ingest_auth()

    assert INGEST.os.environ["QDRANT_API_KEY"] == "operator-write-token"


def test_missing_qdrant_write_key_preserves_existing_client_key(monkeypatch):
    monkeypatch.delenv("QDRANT_WRITE_API_KEY", raising=False)
    monkeypatch.setenv("QDRANT_API_KEY", "existing-client-token")

    INGEST.configure_qdrant_ingest_auth()

    assert INGEST.os.environ["QDRANT_API_KEY"] == "existing-client-token"
