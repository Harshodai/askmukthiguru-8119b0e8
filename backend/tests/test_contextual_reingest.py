"""Unit tests for contextual re-ingestion engine and task wiring."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "deepseek-v4-flash:cloud")
os.environ.setdefault("OLLAMA_CLASSIFY_MODEL", "deepseek-v4-flash:cloud")
os.environ.setdefault("SARVAM_API_KEY", "placeholder")


@pytest.fixture
def engine(tmp_path, monkeypatch):
    from ingest.contextual_reingest import ContextualReingestEngine

    # Inject mocks through the engine constructor
    qdrant = MagicMock()
    qdrant.scroll.return_value = ([], None)

    embedder = MagicMock()
    embedder.encode_batch.return_value = {
        "dense": [[0.1] * 1024, [0.2] * 1024],
        "sparse": [None, None],
    }

    contextualizer = MagicMock()
    contextualizer.service = MagicMock()

    state_file = tmp_path / "ingestion_state.json"

    return ContextualReingestEngine(
        source_collection="spiritual_wisdom",
        target_collection="spiritual_wisdom_contextual",
        qdrant_client=qdrant,
        embedding_service=embedder,
        contextualizer=contextualizer,
        state_file=state_file,
    )


@pytest.fixture
def sample_payloads():
    return [
        {
            "text": "First paragraph of a teaching.",
            "source_url": "http://example.com/video",
            "title": "Teaching One",
            "speaker": "Sri Krishnaji",
            "topic": "Presence",
            "content_type": "video",
            "source_type": "youtube",
            "language": "en",
            "tags": ["meditation"],
            "chunk_index": 0,
            "raptor_level": 0,
            "authority_tier": "primary",
        },
        {
            "text": "Second paragraph continues the teaching.",
            "source_url": "http://example.com/video",
            "title": "Teaching One",
            "speaker": "Sri Krishnaji",
            "topic": "Presence",
            "content_type": "video",
            "source_type": "youtube",
            "language": "en",
            "tags": ["meditation"],
            "chunk_index": 1,
            "raptor_level": 0,
            "authority_tier": "primary",
        },
    ]


@pytest.mark.asyncio
async def test_dry_run(engine, sample_payloads, monkeypatch):
    from unittest.mock import AsyncMock

    # Prepare scroll results
    records = [
        MagicMock(id=f"id-{i}", payload=p)
        for i, p in enumerate(sample_payloads)
    ]
    engine._client().scroll.return_value = (records, None)

    # Monkey-patch rechunk and contextualize for determinism
    monkeypatch.setattr(
        engine,
        "_rechunk",
        lambda full_text, payloads: ["Chunk A", "Chunk B"],
    )
    service_mock = MagicMock()
    service_mock.enrich_chunks = AsyncMock(return_value=["Ctx A", "Ctx B"])

    def _make_service(*args, **kwargs):
        return service_mock

    monkeypatch.setattr(
        "ingest.contextual_reingest.ContextualChunkingService",
        _make_service,
    )

    result = await engine.dry_run(limit=1)

    assert result["dry_run"] is True
    assert result["target_collection"] == "spiritual_wisdom_contextual"
    assert result["sources_previewed"] == 1
    assert result["total_new_chunks"] == 2
    assert result["previews"][0]["new_chunk_count"] == 2


@pytest.mark.asyncio
async def test_reingest_writes_points(engine, sample_payloads, monkeypatch, tmp_path):
    from qdrant_client.http.models import PointStruct

    records = [
        MagicMock(id=f"id-{i}", payload=p)
        for i, p in enumerate(sample_payloads)
    ]
    engine._client().scroll.return_value = (records, None)

    monkeypatch.setattr(
        engine,
        "_rechunk",
        lambda full_text, payloads: ["Chunk A", "Chunk B"],
    )

    service_mock = MagicMock()
    service_mock.enrich_chunks = AsyncMock(return_value=["Ctx A", "Ctx B"])

    def _make_service(*args, **kwargs):
        return service_mock

    monkeypatch.setattr(
        "ingest.contextual_reingest.ContextualChunkingService",
        _make_service,
    )

    # Mock target manager
    target_manager = MagicMock()
    target_manager.client = engine._client()
    engine._target_manager = target_manager
    engine._ensure_target_collection = MagicMock()

    result = await engine.reingest(source_url="http://example.com/video")

    assert result["status"] == "ok"
    assert result["chunks_written"] == 2
    assert result["sources_processed"] == 1

    upsert_call = engine._client().upsert.call_args
    assert upsert_call[1]["collection_name"] == "spiritual_wisdom_contextual"
    points = upsert_call[1]["points"]
    assert len(points) == 2
    assert all(isinstance(p, PointStruct) for p in points)
    for p in points:
        assert p.payload["source_version"] == 2
        assert p.payload["chunk_type"] == "contextual"
        assert "parent_chunk_id" in p.payload
        assert "ingested_at" in p.payload
        assert "authority_tier" in p.payload
        assert "dense" in p.vector


@pytest.mark.asyncio
async def test_reingest_skips_already_processed(engine, sample_payloads, monkeypatch):
    state_file = Path(engine._state_file)
    state_file.write_text(
        json.dumps({"contextual_reingest_processed_sources": ["http://example.com/video"]}),
        encoding="utf-8",
    )

    # Force re-read state
    engine._state = engine._load_state()

    records = [
        MagicMock(id=f"id-{i}", payload=p)
        for i, p in enumerate(sample_payloads)
    ]
    engine._client().scroll.return_value = (records, None)

    result = await engine.reingest()

    assert result["sources_processed"] == 0
    assert result["skipped"] == 1


def test_reconstruct_full_text_strips_old_header():
    from ingest.contextual_reingest import ContextualReingestEngine

    payloads = [
        {
            "text": "[Source: Old | Speaker: X]\n\nReal first chunk.",
            "chunk_index": 0,
        },
        {
            "text": "Second chunk.",
            "chunk_index": 1,
        },
    ]
    text = ContextualReingestEngine._reconstruct_full_text(payloads)
    assert "[Source: Old" not in text
    assert "Real first chunk." in text
    assert "Second chunk." in text


def test_task_registration():
    from tasks.contextual_reingest_task import contextual_reingest, contextual_reingest_dry_run

    assert contextual_reingest.name == "tasks.contextual_reingest_task.contextual_reingest"
    assert contextual_reingest_dry_run.name == "tasks.contextual_reingest_task.contextual_reingest_dry_run"
    assert contextual_reingest.queue == "ingestion"
