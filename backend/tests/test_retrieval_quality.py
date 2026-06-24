"""
Unit tests for retrieval-quality improvements.

Covers:
- Boundary-aware chunking
- Lightweight near-duplicate detection
- Qdrant metadata filter helpers
- Retrieval score-delta cutoffs and deduplication helpers
- Transcript cleaner normalization
"""

from unittest.mock import MagicMock

import pytest


class TestBoundaryChunker:
    def test_respects_sentence_boundaries(self):
        from ingest.boundary_chunker import BoundaryChunker

        text = (
            "First sentence about meditation. Second sentence about mindfulness. "
            "Third sentence about presence. Fourth sentence about awareness."
        )
        chunker = BoundaryChunker(target_size=80, max_size=120)
        chunks = chunker.chunk(text)

        assert len(chunks) > 0
        for chunk in chunks:
            # No chunk should end mid-word (boundary-aware splitting keeps whole sentences)
            assert chunk.strip().endswith((".", "!", "?")) or len(chunk.strip()) < 80

    def test_overlap_is_whole_sentences(self):
        from ingest.boundary_chunker import BoundaryChunker

        text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
        chunker = BoundaryChunker(target_size=40, overlap_sentences=1, max_size=60)
        chunks = chunker.chunk(text)

        if len(chunks) > 1:
            # Overlapping sentence should appear in two consecutive chunks
            overlap = set(chunks[0].split(". ")) & set(chunks[1].split(". "))
            assert overlap, "Expected at least one overlapping whole sentence"

    def test_chunk_with_contextual_headers(self):
        from ingest.boundary_chunker import chunk_with_contextual_headers

        text = "First sentence. Second sentence. Third sentence."
        chunks = chunk_with_contextual_headers(
            text, title="Teaching", speaker="Sri Krishnaji", topic="Meditation"
        )

        assert len(chunks) > 0
        for chunk in chunks:
            assert "[Source: Teaching | Speaker: Sri Krishnaji | Topic: Meditation]" in chunk
            assert "First sentence" in chunk or "Second sentence" in chunk or "Third sentence" in chunk


class TestDeduplication:
    def test_deduplicate_chunks_removes_near_duplicates(self):
        from ingest.deduplication import deduplicate_chunks

        chunks = [
            "The beautiful state is a state of calm and joy.",
            "The beautiful state is a state of calm and joy.",  # duplicate
            "Surrender leads to letting go of control.",
            "The beautiful state is a state of calm.",  # near-duplicate
        ]
        result = deduplicate_chunks(chunks, threshold=0.85)
        assert len(result) < len(chunks)
        assert "The beautiful state is a state of calm and joy." in result
        assert "Surrender leads to letting go of control." in result

    def test_deduplicate_by_payload_preserves_metadata(self):
        from ingest.deduplication import deduplicate_by_payload

        chunks = ["chunk A", "chunk A", "chunk B"]
        metas = [{"id": 1}, {"id": 2}, {"id": 3}]
        out_chunks, out_metas = deduplicate_by_payload(chunks, metas, threshold=0.99)
        assert len(out_chunks) == 2
        assert len(out_metas) == 2
        assert out_metas[0]["id"] == 1

    def test_deduplicate_retrieved_docs_keeps_first(self):
        from ingest.deduplication import deduplicate_retrieved_docs

        docs = [
            {"text": "The beautiful state is a state of calm and joy.", "score": 0.9},
            {"text": "The beautiful state is a state of calm and joy", "score": 0.8},
            {"text": "Surrender leads to letting go of control.", "score": 0.7},
        ]
        result = deduplicate_retrieved_docs(docs, threshold=0.85)
        assert result[0] == docs[0]
        assert len(result) == 2
        assert result[1]["text"] == "Surrender leads to letting go of control."


class TestQdrantMetadataFilters:
    def test_build_source_url_filter(self):
        from services.qdrant_service import QdrantService

        f = QdrantService.build_source_url_filter("https://example.com/video")
        assert f.must[0].key == "source_url"
        assert f.must[0].match.value == "https://example.com/video"

    def test_build_tags_filter_multiple(self):
        from services.qdrant_service import QdrantService

        f = QdrantService.build_tags_filter(["meditation", "surrender"])
        assert f.must[0].key == "tags"
        assert set(f.must[0].match.any) == {"meditation", "surrender"}

    def test_build_metadata_filter_combines_conditions(self):
        from services.qdrant_service import QdrantService

        f = QdrantService.build_metadata_filter(
            source_type="video",
            language="en",
            tags=["meditation"],
            raptor_level=0,
        )
        keys = {c.key for c in f.must}
        assert keys == {"source_type", "language", "tags", "raptor_level"}


class TestRetrievalCutoffHelpers:
    def test_score_delta_cutoff(self):
        from rag.nodes.retrieval import _apply_score_delta_cutoff

        docs = [
            {"text": "A", "score": 0.9},
            {"text": "B", "score": 0.5},
            {"text": "C", "score": 0.3},
        ]
        result = _apply_score_delta_cutoff(docs, score_key="score", min_ratio=0.5)
        assert len(result) == 2
        assert result[0]["text"] == "A"
        assert result[1]["text"] == "B"

    def test_score_delta_cutoff_disabled_when_no_docs(self):
        from rag.nodes.retrieval import _apply_score_delta_cutoff

        assert _apply_score_delta_cutoff([]) == []


class TestCleanerImprovements:
    def test_removes_repeated_timestamps(self):
        from ingest.cleaner import clean_transcript

        text = "1:23 1:23 Welcome to the teaching. 2:45 2:45 Let us begin."
        cleaned = clean_transcript(text)
        # Timestamps are stripped entirely by the noise-pattern step
        assert "1:23" not in cleaned
        assert "2:45" not in cleaned
        assert "Welcome to the teaching" in cleaned
        assert "Let us begin" in cleaned

    def test_removes_music_captions(self):
        from ingest.cleaner import clean_transcript

        text = "[Music] Welcome everyone. Background music playing. [Applause] Thank you."
        cleaned = clean_transcript(text)
        assert "[Music]" not in cleaned
        assert "Background music" not in cleaned
        assert "Welcome everyone" in cleaned
        assert "Thank you" in cleaned

    def test_normalizes_spiritual_terms(self):
        from ingest.cleaner import normalize_spiritual_terms

        text = "preethaji and krishna ji spoke about dhyan and the 4 sacred secrets"
        normalized = normalize_spiritual_terms(text)
        assert "sri preethaji" in normalized
        assert "sri krishnaji" in normalized
        assert "meditation" in normalized
        assert "four sacred secrets" in normalized


@pytest.mark.asyncio
async def test_raptor_parent_chunk_summarization(monkeypatch):
    """RAPTOR parent-chunk summarization uses the injected LLM."""
    from ingest.raptor import RaptorIndexer

    from unittest.mock import AsyncMock

    mock_embedder = MagicMock()
    mock_llm = MagicMock()
    mock_llm.summarize = AsyncMock(return_value="Brief summary")
    mock_qdrant = MagicMock()

    indexer = RaptorIndexer(mock_embedder, mock_llm, mock_qdrant)
    chunks = [
        {"text": "A long teaching about meditation and mindfulness practices."},
        {"text": "Another teaching about surrender and letting go."},
    ]

    result = await indexer.summarize_parent_chunks(chunks)

    assert len(result) == 2
    assert all("summary" in c for c in result)
    assert result[0]["summary"] == "Brief summary"
    assert result[1]["summary"] == "Brief summary"
    assert mock_llm.summarize.call_count == 2
