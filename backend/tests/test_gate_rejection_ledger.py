"""Regressions for chokepoint gate rejection ledger and metrics (DE-0.5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.metrics import (
    CORPUS_GATE_REJECTIONS_PERSISTED_TOTAL,
    INGEST_QUALITY_GATE_REJECTIONS_TOTAL,
)
from services.qdrant.indexer import QdrantIndexer
from services.qdrant.utils import QdrantUtils


def test_chokepoint_reject_persists_row_and_increments_metric():
    """DE-0.5: When select_clean rejects chunks at storage chokepoint, persist row and increment metrics with layer='chokepoint'."""
    client = MagicMock()
    indexer = QdrantIndexer.__new__(QdrantIndexer)
    indexer._client = client
    indexer._collection = "governed_corpus"
    indexer._utils = QdrantUtils()

    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    inserted_rows: list[dict] = []

    def fake_insert(rows):
        inserted_rows.extend(rows)
        ret = MagicMock()
        ret.execute.return_value = MagicMock(data=rows)
        return ret

    mock_table.insert.side_effect = fake_insert

    # Get starting metric counts
    chokepoint_labels = {"reason": "artifact_detected", "tier": "chokepoint", "layer": "chokepoint"}
    initial_rejections = INGEST_QUALITY_GATE_REJECTIONS_TOTAL.labels(**chokepoint_labels)._value.get()
    initial_persisted = CORPUS_GATE_REJECTIONS_PERSISTED_TOTAL._value.get()

    artifact_chunk = "My task is to extract teachings from this transcript. Spiritual teaching here."
    source_url = "https://example.org/talk-with-artifact"

    with patch("app.telemetry_db._get_client", return_value=mock_supabase):
        upserted_count = indexer.upsert_chunks(
            texts=[artifact_chunk],
            vectors=[[0.1] * 8],
            metadatas=[{"source_url": source_url, "chunk_index": 0}],
        )

    # All chunks were rejected by select_clean
    assert upserted_count == 0
    client.upsert.assert_not_called()

    # Verify metric increment with layer="chokepoint" and tier="chokepoint"
    new_rejections = INGEST_QUALITY_GATE_REJECTIONS_TOTAL.labels(**chokepoint_labels)._value.get()
    assert new_rejections == initial_rejections + 1

    # Verify persisted metric incremented
    new_persisted = CORPUS_GATE_REJECTIONS_PERSISTED_TOTAL._value.get()
    assert new_persisted == initial_persisted + 1

    # Verify corpus_gate_rejections table insert
    mock_supabase.table.assert_called_with("corpus_gate_rejections")
    assert len(inserted_rows) == 1
    row = inserted_rows[0]
    assert row["source_url"] == source_url
    assert row["chunk_index"] == 0
    assert row["gate_layer"] == "chokepoint"
    assert row["reason"] == "artifact_detected"
    assert "My task is to" in row["matched_span"]
    assert "point_id" in row and row["point_id"]
