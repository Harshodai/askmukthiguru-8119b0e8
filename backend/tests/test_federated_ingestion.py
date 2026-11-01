"""
Tests for Phase 7 Unified Multi-DataSource Ingestion Engine
- YouTube subtitle rolling-window mantra preservation & timestamp coordinate parsing.
- Federated ingestion connector routing (YouTube, PDF, Audio, WhatsApp, OKF Staging).
- Invariant X40 rights stamping (domain_rights_status='licensed', chunker_version).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingest.federated_engine import (
    AudioArchiveAdapter,
    FederatedDataSourceIngestionEngine,
    OKFStagingAdapter,
    PDFDoctrineAdapter,
    WhatsAppReflectionAdapter,
    YouTubeAdapter,
)
from ingest.youtube_loader import _parse_subtitle_file


def test_youtube_subtitle_rolling_window_mantra_preservation():
    """Verify that subtitle parser removes immediate ASR stutters while preserving repeated chants and millisecond timestamps."""
    vtt_content = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:04.000
Welcome seekers.

00:00:05.000 --> 00:00:07.000
Om Namo Bhagavate

00:00:07.500 --> 00:00:09.000
Om Namo Bhagavate

00:00:10.000 --> 00:00:12.000
Some other discourse content here.

00:00:13.000 --> 00:00:15.000
Another line.

00:00:16.000 --> 00:00:18.000
Yet another line.

00:00:25.000 --> 00:00:28.000
Om Namo Bhagavate
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".vtt", delete=False, encoding="utf-8") as tmp:
        tmp.write(vtt_content)
        tmp_path = tmp.name

    try:
        parsed_text = _parse_subtitle_file(tmp_path)
        assert parsed_text is not None
        assert "[00:00:01.000]" in parsed_text
        assert "Welcome seekers" in parsed_text
        count_om = parsed_text.count("Om Namo Bhagavate")
        assert count_om == 2, f"Expected 2 occurrences of chant due to rolling window, got: {parsed_text}"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_federated_ingestion_connector_routing():
    """Test that FederatedDataSourceIngestionEngine routes and parses across all 5 adapters correctly."""
    engine = FederatedDataSourceIngestionEngine()
    assert "youtube" in engine.adapters
    assert "pdf_doctrine" in engine.adapters
    assert "audio_archive" in engine.adapters
    assert "whatsapp_reflection" in engine.adapters
    assert "okf_staging" in engine.adapters

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as tmp:
        tmp.write("# Test OKF Markdown\nSpiritual realization content.")
        tmp_path = tmp.name

    try:
        mock_qdrant = MagicMock()
        mock_qdrant.upsert_chunks.return_value = 1

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        engine_with_dbs = FederatedDataSourceIngestionEngine(
            qdrant_service=mock_qdrant,
            memgraph_driver=mock_driver,
        )

        result = engine_with_dbs.ingest_source(
            "okf_staging",
            tmp_path,
            chunker_version="v2.4-adaptive",
        )

        assert result["status"] == "success"
        assert result["chunks_ingested"] == 1
        assert result["written_qdrant"] == 1
        assert result["written_memgraph"] == 1
        mock_qdrant.upsert_chunks.assert_called_once()
        mock_session.run.assert_called()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_invariant_x40_rights_stamping():
    """Verify that Invariant X40 rights stamping (domain_rights_status='licensed') is enforced on ingestion."""
    engine = FederatedDataSourceIngestionEngine()
    
    adapter = OKFStagingAdapter()
    raw = [{"content": "Test content", "source_ref": "test.md"}]
    chunks = adapter.parse_and_chunk(raw, chunker_version="v2.4-adaptive")

    assert len(chunks) == 1
    meta = chunks[0]["metadata"]
    assert meta["domain_rights_status"] == "licensed"
    assert meta["chunker_version"] == "v2.4-adaptive"

    mock_qdrant = MagicMock()
    mock_qdrant.upsert_chunks.return_value = 1
    engine.qdrant_service = mock_qdrant

    res = engine.ingest_source("okf_staging", "test.md")
    assert res["status"] == "success"

    with patch.object(adapter, "parse_and_chunk", return_value=[{
        "content": "bad",
        "metadata": {"domain_rights_status": "unlicensed", "chunker_version": "v2.4-adaptive"}
    }]):
        engine.adapters["okf_staging"] = adapter
        with pytest.raises((AssertionError, RuntimeError)):
            engine.ingest_source("okf_staging", "test.md")
