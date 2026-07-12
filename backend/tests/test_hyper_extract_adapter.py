"""
Unit tests for backend/ingest/hyper_extract_adapter.py.

Covers:
  - Empty input handling
  - Short text below minimum length
  - Section detection on structured transcripts
  - Entity extraction on known spiritual terms
  - Relationship extraction
  - Pipeline integration: config flag disables enrichment
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingest.hyper_extract_adapter import (
    DEFAULT_MIN_TEXT_LENGTH,
    enrich_text,
    is_eligible,
)
from ingest.pipeline import IngestionPipeline

SAMPLE_TRANSCRIPT = """
Introduction

Welcome to this satsang with Sri Preethaji and Sri Krishnaji.

The Power of Observation

Sri Krishnaji teaches that observation dissolves the ego. When you observe the mind without judgment, suffering begins to lose its grip.

Sri Preethaji guides us into the Beautiful State through breath and intention. Breath becomes the bridge from suffering to peace.

The Practice

Sit quietly. Bring your attention to the breath. Let every inhale expand awareness and every exhale release tension. This simple practice restores joy.
"""


@pytest.fixture
def mock_pipeline(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "use_adaptive_chunking", False)
    monkeypatch.setattr(settings, "use_hyper_extract_enrichment", False)
    qdrant = MagicMock()
    embedder = MagicMock()
    ollama = MagicMock()
    pipeline = IngestionPipeline(qdrant, embedder, ollama)
    pipeline._raptor.build_tree = AsyncMock(return_value=0)
    return pipeline


def test_empty_input_returns_empty_structure():
    result = enrich_text("")
    assert result == {
        "sections": [],
        "atomic_facts": [],
        "entities": [],
        "relationships": [],
    }


def test_whitespace_only_input_returns_empty_structure():
    result = enrich_text("   \n\n  ")
    assert result["sections"] == []
    assert result["atomic_facts"] == []
    assert result["entities"] == []
    assert result["relationships"] == []


def test_short_text_below_minimum_returns_empty_structure():
    result = enrich_text("This is too short.", min_text_length=50)
    assert result["sections"] == []
    assert result["atomic_facts"] == []
    assert result["entities"] == []
    assert result["relationships"] == []


def test_short_transcript_with_default_minimum_returns_some_facts():
    text = (
        "Sri Krishnaji teaches that observation dissolves the ego and brings peace. "
        "When the mind observes without judgment, the patterns that create suffering begin to loosen. "
        "This practice is available to everyone who is willing to look inward with sincerity and patience."
    )
    result = enrich_text(text)
    assert len(result["atomic_facts"]) >= 1
    assert any("Sri Krishnaji" in fact for fact in result["atomic_facts"])


def test_section_detection_finds_headers():
    result = enrich_text(SAMPLE_TRANSCRIPT)
    titles = [section["title"] for section in result["sections"]]
    assert "Introduction" in titles
    assert "Power Of Observation" in titles
    assert "Practice" in titles


@pytest.mark.asyncio
async def test_entity_extraction_knows_spiritual_terms(mock_pipeline, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "use_hyper_extract_enrichment", True)

    text = (
        "Sri Preethaji and Sri Krishnaji teach that breath leads to the Beautiful State. "
        "Observation of the ego dissolves suffering and restores joy. "
        "Through regular practice, the seeker moves from a contracted state into openness and peace."
    )

    result = mock_pipeline._enrich_text(text)

    assert result is not None
    entities = {entity.lower() for entity in result["entities"]}
    assert "sri preethaji" in entities
    assert "sri krishnaji" in entities
    assert "beautiful state" in entities
    assert "ego" in entities
    assert "suffering" in entities


@pytest.mark.asyncio
async def test_relationship_extraction_links_entities(mock_pipeline, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "use_hyper_extract_enrichment", True)

    text = (
        "Sri Krishnaji teaches that breath dissolves the ego and creates peace. "
        "When attention rests on the breath, the mind becomes still and the heart opens to joy. "
        "This simple practice is available to anyone who chooses to observe the mind with patience."
    )
    result = mock_pipeline._enrich_text(text)

    assert result is not None
    assert len(result["relationships"]) >= 1
    relationships = {(s.lower(), r, t.lower()) for s, r, t in result["relationships"]}
    assert any("sri krishnaji" in (source, target) for source, _, target in relationships)


@pytest.mark.asyncio
async def test_optional_flag_disables_enrichment(mock_pipeline, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "use_hyper_extract_enrichment", False)

    text = (
        "Sri Krishnaji teaches that observation dissolves the ego and brings peace. "
        "This simple teaching can transform the way we relate to our own minds and daily experience."
    )
    result = mock_pipeline._enrich_text(text)
    assert result is None


def test_is_eligible_respects_minimum_length():
    assert is_eligible("Short.", min_length=10) is False
    assert is_eligible("This text is long enough to be eligible.", min_length=10) is True
    assert is_eligible("", min_length=1) is False


def test_empty_and_short_text_returns_empty_enrichment():
    assert is_eligible("") is False
    assert is_eligible("Too short.") is False

    short_text = "A short sentence about breath that is below the default minimum length threshold."
    assert len(short_text) < DEFAULT_MIN_TEXT_LENGTH
    result = enrich_text(short_text)
    assert result == {
        "sections": [],
        "atomic_facts": [],
        "entities": [],
        "relationships": [],
    }


@pytest.mark.asyncio
async def test_ingest_raw_text_includes_hyper_extract_when_enabled(
    mock_pipeline, monkeypatch
):
    from app.config import settings
    from ingest.pipeline import IngestionCheckpoint

    monkeypatch.setattr(settings, "use_hyper_extract_enrichment", True)
    monkeypatch.setattr(IngestionCheckpoint, "is_processed", lambda self, chunk_id: False)
    monkeypatch.setattr(IngestionCheckpoint, "save", lambda self, chunk_id: None)
    mock_pipeline._qdrant.upsert_chunks.return_value = 1
    mock_pipeline._qdrant.check_source_exists.return_value = False
    mock_pipeline._embedder.encode_batch.return_value = {"dense": [[0.0]], "sparse": [{}]}

    text = (
        "Sri Preethaji guides seekers into the Beautiful State through breath and intention. "
        "Sri Krishnaji teaches that breath observation dissolves suffering and restores inner peace. "
        "This integrated practice helps every seeker move from confusion into clarity and stillness."
    )

    with patch.object(
        mock_pipeline, "_augment_chunks", return_value=[text]
    ):
        result = await mock_pipeline.ingest_raw_text(
            text=text,
            source_url="test://spiritual-teaching",
            title="Teaching",
            content_type="document",
        )

    assert result["status"] == "success"
    assert result["hyper_extract"] is not None
    assert "Sri Preethaji" in result["hyper_extract"]["entities"]
    assert "Sri Krishnaji" in result["hyper_extract"]["entities"]


@pytest.mark.asyncio
async def test_ingest_raw_text_omits_hyper_extract_when_disabled(
    mock_pipeline, monkeypatch
):
    from app.config import settings
    from ingest.pipeline import IngestionCheckpoint

    monkeypatch.setattr(settings, "use_hyper_extract_enrichment", False)
    monkeypatch.setattr(IngestionCheckpoint, "is_processed", lambda self, chunk_id: False)
    monkeypatch.setattr(IngestionCheckpoint, "save", lambda self, chunk_id: None)
    mock_pipeline._qdrant.upsert_chunks.return_value = 1
    mock_pipeline._qdrant.check_source_exists.return_value = False
    mock_pipeline._embedder.encode_batch.return_value = {"dense": [[0.0]], "sparse": [{}]}

    text = (
        "Sri Preethaji guides seekers into the Beautiful State through breath and intention. "
        "Sri Krishnaji teaches that breath observation dissolves suffering and restores inner peace. "
        "This integrated practice helps every seeker move from confusion into clarity and stillness."
    )

    with patch.object(
        mock_pipeline, "_augment_chunks", return_value=[text]
    ):
        result = await mock_pipeline.ingest_raw_text(
            text=text,
            source_url="test://spiritual-teaching",
            title="Teaching",
            content_type="document",
        )

    assert result["status"] == "success"
    assert result.get("hyper_extract") is None
