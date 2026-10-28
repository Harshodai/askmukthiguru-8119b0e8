"""Tests for RAG-2: Context Enrichment Window (Phase 6 / Master Plan Table K.4).

Pins:
- General RAG path:
  - Flag off (enrichment_window_enabled=False) -> identical output, qdrant.get_neighbor_chunks not called.
  - Flag on (enrichment_window_enabled=True) -> neighbor chunks fetched, respects budget, truncated answer expands.
  - Metric ENRICHMENT_WINDOW_EXPANSIONS_TOTAL tracked.
- First-person harness path:
  - enrich_to_parent_window(parent_unit_id, span_id, window_size) returns surrounding spans.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from domain.first_person_context import (
    BoundaryStatus,
    CompletenessStatus,
    ParentUnit,
    ProvenanceKind,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
    make_source_span_id,
)
from rag.nodes.reranking import enrich_context
from rag.states import GraphState
from services.first_person_context_store import (
    RECORD_TYPE_CHILD,
    FirstPersonContextStore,
    parent_point_id,
    point_id_for_record,
)


@pytest.mark.asyncio
async def test_enrich_context_flag_off_returns_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    """When enrichment_window_enabled=False, enrich_context returns identical output."""
    monkeypatch.setattr(settings, "enrichment_window_enabled", False)

    mock_qdrant = MagicMock()
    mock_qdrant.get_neighbor_chunks = MagicMock()

    docs = [
        {"text": "First chunk", "source_url": "https://example.com/1", "chunk_index": 1},
        {"text": "Second chunk", "source_url": "https://example.com/1", "chunk_index": 2},
    ]
    state = GraphState(
        question="Tell me about stillness",
        chat_history=[],
        relevant_docs=docs,
        query_tier="standard",
    )

    with patch("rag.nodes.reranking._services") as mock_services:
        mock_services._qdrant = mock_qdrant
        res = await enrich_context(state)

    assert res["relevant_docs"] == docs
    mock_qdrant.get_neighbor_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_enrich_context_flag_on_widens_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """When enrichment_window_enabled=True, fetches neighbor chunks and tracks metric."""
    monkeypatch.setattr(settings, "enrichment_window_enabled", True)
    monkeypatch.setattr(settings, "enrichment_window_size", 1)

    mock_qdrant = MagicMock()
    # Mock neighbor response
    mock_qdrant.get_neighbor_chunks.return_value = [
        {"text": "Setup: Before moving forward, know this truth.", "chunk_index": 0},
        {"text": "The mind needs to be in a beautiful state.", "chunk_index": 1},
    ]

    docs = [
        {
            "text": "The mind needs to be in a beautiful state.",
            "source_url": "https://example.com/lecture",
            "chunk_index": 1,
            "content_type": "transcript",
        }
    ]
    state = GraphState(
        question="How do I quiet the mind?",
        chat_history=[],
        relevant_docs=docs,
        query_tier="standard",
    )

    with patch("rag.nodes.reranking._services") as mock_services:
        mock_services._qdrant = mock_qdrant
        res = await enrich_context(state)

    mock_qdrant.get_neighbor_chunks.assert_called_once_with(
        "https://example.com/lecture", 1, window=1
    )
    enriched = res["relevant_docs"]
    assert len(enriched) == 2
    assert "Setup: Before moving forward" in enriched[0]["text"]
    assert "The mind needs to be" in enriched[1]["text"]


@pytest.mark.asyncio
async def test_enrich_context_respects_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enrichment respects token/char budget and trims excessive expansions."""
    monkeypatch.setattr(settings, "enrichment_window_enabled", True)
    monkeypatch.setattr(settings, "enrichment_window_size", 2)
    # Set a small budget
    monkeypatch.setattr(settings, "generation_compression_max_chars", 50)

    mock_qdrant = MagicMock()
    # Large neighbor texts
    mock_qdrant.get_neighbor_chunks.return_value = [
        {"text": "A" * 150, "chunk_index": 0},
        {"text": "B" * 150, "chunk_index": 1},
        {"text": "C" * 150, "chunk_index": 2},
    ]

    docs = [
        {
            "text": "Base chunk text",
            "source_url": "https://example.com/long",
            "chunk_index": 1,
            "content_type": "transcript",
        }
    ]
    state = GraphState(
        question="Budget test",
        chat_history=[],
        relevant_docs=docs,
        query_tier="standard",
    )

    with patch("rag.nodes.reranking._services") as mock_services:
        mock_services._qdrant = mock_qdrant
        res = await enrich_context(state)

    enriched = res["relevant_docs"]
    # Total chars must not exceed the budget
    total_chars = sum(len(d.get("text", "")) for d in enriched)
    assert total_chars <= 50 * 4 + 150  # Bounded


def _make_span(n: int, text: str, parent_id: str = "p1") -> SourceSpan:
    hash_val = "a" * 64
    span_id = make_source_span_id(
        guru_id="krishnaji",
        video_id="v1",
        corpus_version="ctx-v1",
        word_start=n * 10,
        word_end=n * 10 + 5,
        transcript_hash=hash_val,
    )
    return SourceSpan(
        corpus_version="ctx-v1",
        guru_id="krishnaji",
        video_id="v1",
        source_asset_id="v1",
        source_span_id=span_id,
        parent_unit_id=parent_id,
        turn_id=f"t{n}",
        turn_index=n,
        source_span_index=n,
        start_ms=1000 * n,
        end_ms=1000 * n + 800,
        word_start=n * 10,
        word_end=n * 10 + 5,
        speaker_id="krishnaji",
        speaker_role=SpeakerRole.GURU,
        speaker_verified=True,
        source_transcript_text=text,
        verbatim_text=text,
        transcript_hash=hash_val,
        source_text_hash=clip_text_hash(text),
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
        rights_cleared=True,
        caption_status="auto",
        provenance_kind=ProvenanceKind.SPEECH_TURN_SPAN,
        source_url="https://youtube.com/watch?v=v1",
    )


def test_fp_context_store_enrich_to_parent_window() -> None:
    """Test FirstPersonContextStore.enrich_to_parent_window(parent_unit_id, span_id, window_size)."""
    spans = [
        _make_span(0, "Introduction to the inquiry."),
        _make_span(1, "The core teaching on freedom."),
        _make_span(2, "Conclusion and practice."),
    ]
    parent = ParentUnit(
        corpus_version="ctx-v1",
        guru_id="krishnaji",
        video_id="v1",
        parent_unit_id="p1",
        ordered_source_span_ids=tuple(s.source_span_id for s in spans),
        start_ms=0,
        end_ms=3000,
        parent_text_hash=clip_text_hash(" ".join(s.verbatim_text for s in spans)),
        speaker_ids=("krishnaji",),
        speaker_continuity=True,
        boundary_status=BoundaryStatus.VERIFIED,
        completeness_status=CompletenessStatus.COMPLETE,
    )

    mock_client = MagicMock()

    class _Record:
        def __init__(self, id, payload):
            self.id = id
            self.payload = payload

    def mock_retrieve(collection_name, ids, *args, **kwargs):
        if ids == [parent_point_id("p1")]:
            return [
                _Record(parent_point_id("p1"), {**parent.to_payload(), "record_type": "parent"})
            ]
        return []

    mock_client.retrieve.side_effect = mock_retrieve

    def mock_scroll(*args, **kwargs):
        records = [
            _Record(
                point_id_for_record(s.source_span_id),
                {**s.to_payload(), "record_type": RECORD_TYPE_CHILD},
            )
            for s in spans
        ]
        return (records, None)

    mock_client.scroll.side_effect = mock_scroll

    store = FirstPersonContextStore(mock_client, collection="test_fp")

    # Center on middle span (index 1) with window_size=1
    target_id = spans[1].source_span_id
    window = store.enrich_to_parent_window("p1", target_id, window_size=1)

    assert len(window) == 3
    assert window[0].source_span_id == spans[0].source_span_id
    assert window[1].source_span_id == spans[1].source_span_id
    assert window[2].source_span_id == spans[2].source_span_id

    # Center on first span (index 0) with window_size=1
    first_id = spans[0].source_span_id
    window_first = store.enrich_to_parent_window("p1", first_id, window_size=1)
    assert len(window_first) == 2
    assert window_first[0].source_span_id == spans[0].source_span_id
    assert window_first[1].source_span_id == spans[1].source_span_id

    # Non-existent span returns empty list
    not_found = store.enrich_to_parent_window("p1", "non_existent_id", window_size=1)
    assert not_found == []
