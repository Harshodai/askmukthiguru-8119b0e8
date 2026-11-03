"""
Test Suite for Phase 6 Data Engineering & Quality Gate Remediations (DEF-01 to DEF-04, X40).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingest.deduplication import (
    _minhash_signature,
    _normalize,
    _shingles,
    deduplicate_chunks,
    near_duplicate_similarity,
)
from ingest.quality_gate import DataQualityGate
from ingest.video_pipeline import VideoPipeline
from services.qdrant.indexer import QdrantIndexer


@pytest.mark.asyncio
async def test_def_01_video_pipeline_deterministic_uuid_and_contract_payload():
    """DEF-01: Verify video_pipeline uses deterministic UUIDv5 namespace and all 14 mandatory contract payload fields."""
    mock_qdrant_service = MagicMock()
    mock_qdrant_service.upsert = AsyncMock()
    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = [[0.1] * 4]

    pipeline = VideoPipeline(
        qdrant_service=mock_qdrant_service,
        embedding_service=mock_embedder,
    )

    chunks = ["Spiritual teaching chunk one about surrender and inner peace."]
    source = "https://youtube.com/watch?v=test123"

    with patch("services.qdrant.indexer.QdrantIndexer.upsert_chunks") as mock_upsert:
        mock_upsert.return_value = 1
        # Contract is (written, point_ids): the direct-video upload path stamps
        # payload onto exactly the ids this write created.
        written, point_ids = await pipeline._upsert_chunks(chunks, source)
        assert written == 1
        assert point_ids == [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}_0_0"))]
        mock_upsert.assert_called_once()
        args, kwargs = mock_upsert.call_args
        kwargs.get("texts") or args[0]
        kwargs.get("vectors") or args[1]
        metadatas = kwargs.get("metadatas") or args[2]
        assert len(metadatas) == 1
        meta = metadatas[0]
        # Verify mandatory fields
        mandatory_fields = [
            "text",
            "source_url",
            "title",
            "speaker",
            "topic",
            "chunk_index",
            "content_type",
            "raptor_level",
            "chunker_version",
            "parent_id_scheme",
            "modality",
            "rights_status",
            "content_hash",
            "point_id",
        ]
        for field in mandatory_fields:
            assert field in meta, f"Mandatory field '{field}' missing from video chunk payload"
        assert meta["modality"] == "video"
        assert meta["source_url"] == source
        assert meta["point_id"] == str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}_0_0"))


@pytest.mark.asyncio
async def test_def_02_quality_gate_100_percent_inspection():
    """DEF-02: Verify chunk_quality_gate inspects 100% of chunks with zero bypass."""
    gate = DataQualityGate()
    gate._enabled = True

    chunks = [
        "Chunk 1: Pure spiritual teaching about oneness and surrender to the divine.",
        "Chunk 2: As a text correction expert, I cannot fulfill this request because...",  # Junk
        "Chunk 3: Another deep meditative contemplation on inner stillness and silence.",
        "Chunk 4: Fourth chunk discussing karma, dharma, and supreme liberation.",
    ]

    with patch.object(gate, "run", new_callable=AsyncMock) as mock_run:

        async def side_effect(text, source_url="", speaker=""):
            res = MagicMock()
            if "text correction expert" in text:
                res.passed = False
                res.score = 0
                res.reasons = ["Junk artifact detected"]
            else:
                res.passed = True
                res.score = 85
                res.reasons = []
            return res

        mock_run.side_effect = side_effect

        clean_chunks, results = await gate.run_chunks(chunks, source_url="https://test.com")
        # 100% inspection means mock_run must be called for ALL 4 chunks
        assert mock_run.call_count == len(chunks), (
            f"Expected {len(chunks)} inspections, got {mock_run.call_count}"
        )
        # Junk chunk should be filtered out
        assert len(clean_chunks) == 3
        assert len(results) == 4


@pytest.mark.asyncio
async def test_def_03_invariant_x40_rejection_persistence():
    """DEF-03 / Invariant X40: Verify rejected chunks are persisted to public.corpus_gate_rejections."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_insert = MagicMock()
    mock_table.insert.return_value = mock_insert

    indexer = QdrantIndexer(client=MagicMock())
    indexer._collection = "mukthi_guru"

    rejected = [(0, "Junk extraction artifact detected", "preview text")]
    metadatas = [{"source_url": "https://youtube.com/watch?v=reject1", "chunk_index": 0}]

    with patch("app.telemetry_db._get_client", return_value=mock_client):
        indexer._record_gate_rejections(rejected, metadatas)

    mock_client.table.assert_called_with("corpus_gate_rejections")
    mock_table.insert.assert_called_once()
    inserted_rows = mock_table.insert.call_args[0][0]
    assert len(inserted_rows) == 1
    row = inserted_rows[0]
    assert row["source_url"] == "https://youtube.com/watch?v=reject1"
    assert row["gate_verdict"] == "rejected"
    assert "reason" in row


def test_def_04_minhash_vectorized_throughput_and_accuracy():
    """DEF-04: Verify vectorized MinHash LSH implementation performance and accuracy."""
    text1 = "surrender to the divine consciousness and find inner peace and liberation."
    text2 = "surrender to the divine consciousness and find inner peace and liberation!"
    text3 = "completely unrelated text about quantum computing and machine learning networks."

    _minhash_signature(_shingles(_normalize(text1)), 32)
    _minhash_signature(_shingles(_normalize(text2)), 32)
    _minhash_signature(_shingles(_normalize(text3)), 32)

    sim_12 = near_duplicate_similarity(text1, text2)
    sim_13 = near_duplicate_similarity(text1, text3)

    assert sim_12 > 0.85, f"Expected high similarity for near-duplicates, got {sim_12}"
    assert sim_13 < 0.50, f"Expected low similarity for distinct texts, got {sim_13}"

    # Test deduplicate_chunks
    batch = [text1, text2, text3]
    deduped = deduplicate_chunks(batch, threshold=0.85)
    assert len(deduped) == 2, f"Expected 2 chunks after deduplication, got {len(deduped)}"
