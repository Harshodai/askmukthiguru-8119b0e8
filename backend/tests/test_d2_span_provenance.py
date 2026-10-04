"""D2 span-provenance remainder: chunker spans + whisperx segment-time resolver.

Covers F3-proposed (a)+(b):
  - BoundaryChunker.chunk_with_spans / split_text_with_spans return chunks
    with parallel char spans, chunk() behavior unchanged.
  - _resolve_chunk_timing_from_cache maps chunks to whisperx segment
    start/end via word overlap; unknown timing is None, never guessed.
  - Resolver output survives the _embed_and_index wire-through onto the
    Qdrant payload (length-mismatch drop already covered by the D2 tests in
    test_ingestion_pipeline.py).
  - QdrantService.ensure_timing_payload_index rejects non-timing fields and
    never raises (client mocked; live index creation is scratch-verified in
    scripts/ops/d2_span_provenance_scratch_check.py).
"""

from unittest.mock import MagicMock

import pytest

from ingest.boundary_chunker import (
    BoundaryChunker,
    ChunkBounds,
    split_text_at_boundaries,
    split_text_with_spans,
)
from ingest.pipeline import EmbedIndexConfig, IngestionPipeline, _resolve_chunk_timing_from_cache


@pytest.fixture
def mock_pipeline(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "use_adaptive_chunking", False)
    monkeypatch.setattr(settings, "use_boundary_chunker", False)
    monkeypatch.setattr(
        "ingest.pipeline.IngestionCheckpoint.acquire_lock",
        lambda self, lock_key, ttl=3600: "mock_token",
    )
    monkeypatch.setattr(
        "ingest.pipeline.IngestionCheckpoint.release_lock", lambda self, lock_key, lock_token: True
    )
    return IngestionPipeline(MagicMock(), MagicMock(), MagicMock())


def _teaching_text(repeats: int = 8) -> str:
    para = (
        "Suffering is not a fact but a perception of the mind in this moment. "
        "Awareness of the breath brings the seeker back to stillness and peace. "
        "Compassion for all beings everywhere flows from that silent seeing."
    )
    return "\n\n".join([para] * repeats)


def test_chunk_with_spans_matches_chunk():
    text = _teaching_text()
    plain = split_text_at_boundaries(text)
    chunked, spans = split_text_with_spans(text)
    assert chunked == plain
    assert len(chunked) == len(spans)
    assert all(isinstance(s, ChunkBounds) for s in spans)
    for chunk, span in zip(chunked, spans):
        assert chunk.strip()
        assert 0 <= span.start <= span.end


def test_chunk_with_spans_empty():
    assert BoundaryChunker().chunk_with_spans("") == ([], [])
    assert BoundaryChunker().chunk_with_spans("   ") == ([], [])


def test_chunk_with_spans_merge_keeps_alignment():
    # Tiny trailing chunk merges into its predecessor; spans stay parallel
    # and the merged span covers the merged text length.
    chunker = BoundaryChunker(target_size=200, max_size=400, min_size=120)
    text = "Awareness of the breath in the present moment of stillness. " * 6 + "\n\nTiny tail."
    chunked, spans = chunker.chunk_with_spans(text)
    assert chunked == chunker.chunk(text)
    assert len(chunked) == len(spans)
    for chunk, span in zip(chunked, spans):
        assert span.end - span.start == len(chunk)


def test_resolver_maps_chunks_to_segment_times():
    from services.whisper_local_service import (
        cache_whisperx_result,
        clear_cached_whisperx_result,
    )

    vid = "d2span_unit_vid"
    cache_whisperx_result(
        vid,
        {
            "segments": [
                {"text": "suffering is not a fact but a perception", "start": 0.0, "end": 4.2},
                {"text": "awareness of the breath brings stillness", "start": 4.2, "end": 9.0},
                {"text": "compassion for all beings everywhere", "start": 9.0, "end": 14.5},
            ],
            "method": "whisperx_aligned_diarized",
        },
    )
    try:
        chunks = [
            "Teaching on suffering is not a fact but a perception of mind.",
            "Unrelated filler words about nothing in particular xyzzy.",
            "Compassion for all beings everywhere flows from seeing.",
        ]
        starts, ends, asr, align = _resolve_chunk_timing_from_cache(vid, chunks)
        assert (starts[0], ends[0]) == (0.0, 4.2)
        assert starts[1] is None and ends[1] is None
        assert (starts[2], ends[2]) == (9.0, 14.5)
        assert asr == "whisperx_aligned_diarized"
        assert align is None
    finally:
        clear_cached_whisperx_result(vid)


def test_resolver_multi_segment_span():
    from services.whisper_local_service import (
        cache_whisperx_result,
        clear_cached_whisperx_result,
    )

    vid = "d2span_unit_multi"
    cache_whisperx_result(
        vid,
        {
            "segments": [
                {"text": "suffering is not a fact", "start": 0.0, "end": 2.0},
                {"text": "but a perception of mind", "start": 2.0, "end": 4.0},
            ]
        },
    )
    try:
        (starts, ends, _, _) = _resolve_chunk_timing_from_cache(
            vid, ["suffering is not a fact but a perception of mind"]
        )
        assert (starts[0], ends[0]) == (0.0, 4.0)
    finally:
        clear_cached_whisperx_result(vid)


def test_resolver_unknown_cache_is_all_none():
    chunks = ["Some teaching about stillness and the quiet mind within us all today."]
    starts, ends, asr, align = _resolve_chunk_timing_from_cache("d2span_no_such_video", chunks)
    assert starts == [None] and ends == [None]
    assert asr is None and align is None
    starts, ends, _, _ = _resolve_chunk_timing_from_cache(None, chunks)
    assert starts == [None] and ends == [None]


def test_resolver_malformed_segments_never_raise():
    from services.whisper_local_service import (
        cache_whisperx_result,
        clear_cached_whisperx_result,
    )

    vid = "d2span_unit_malformed"
    cache_whisperx_result(
        vid,
        {"segments": [{"text": "", "start": "bad", "end": None}, {"no_text": True}, None]},
    )
    try:
        starts, ends, _, _ = _resolve_chunk_timing_from_cache(vid, ["a chunk here"])
        assert starts == [None] and ends == [None]
    finally:
        clear_cached_whisperx_result(vid)


def test_resolver_output_survives_embed_wire_through(mock_pipeline):
    """Resolver arrays land on the payload via the existing D2 wire-through."""
    mock_pipeline._embedder.encode_batch = MagicMock(
        return_value={"dense": [[0.1] * 384] * 2, "sparse": [None] * 2}
    )
    mock_pipeline._qdrant.upsert_chunks = MagicMock(return_value=2)
    mock_pipeline._qdrant.check_source_exists = MagicMock(return_value=False)

    chunks = [
        "Suffering is not a fact but a perception of the mind in this very moment now.",
        "Awareness of the breath brings the seeker back to stillness and deep peace.",
    ]
    mock_pipeline._embed_and_index(
        EmbedIndexConfig(
            chunks=list(chunks),
            source_url="https://youtube.com/watch?v=d2spanwire",
            title="D2 Span Wire",
            content_type="video",
            chunk_starts=[0.0, 4.2],
            chunk_ends=[4.2, 9.0],
            asr_method="whisperx_aligned_diarized",
        )
    )
    metadatas = mock_pipeline._qdrant.upsert_chunks.call_args[0][2]
    assert [m["chunk_start"] for m in metadatas] == [0.0, 4.2]
    assert [m["chunk_end"] for m in metadatas] == [4.2, 9.0]
    assert all(m["asr_method"] == "whisperx_aligned_diarized" for m in metadatas)


def test_ensure_timing_payload_index_guards():
    from services.qdrant_service import QdrantService

    svc = QdrantService.__new__(QdrantService)  # no client: guards must fire first
    import logging

    logging.disable(logging.CRITICAL)
    try:
        assert svc.ensure_timing_payload_index("source_url") is False
        assert svc.ensure_timing_payload_index("chunk_start") is False  # no client, no raise
    finally:
        logging.disable(logging.NOTSET)


def test_ensure_timing_payload_index_creates_float_index():
    from services.qdrant_service import QdrantService

    svc = QdrantService.__new__(QdrantService)
    svc._collection = "d2_scratch_unit"
    svc._client = MagicMock()
    assert svc.ensure_timing_payload_index("chunk_start") is True
    _, kwargs = svc._client.create_payload_index.call_args
    assert kwargs["collection_name"] == "d2_scratch_unit"
    assert kwargs["field_name"] == "chunk_start"
    from qdrant_client.http.models import PayloadSchemaType

    assert kwargs["field_schema"] == PayloadSchemaType.FLOAT
