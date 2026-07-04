from unittest.mock import MagicMock

import pytest

from ingest.pipeline import IngestionPipeline


@pytest.fixture
def mock_pipeline(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "use_adaptive_chunking", False)
    qdrant = MagicMock()
    embedder = MagicMock()
    ollama = MagicMock()
    return IngestionPipeline(qdrant, embedder, ollama)


def test_split_text_with_contextual_headers(mock_pipeline):
    text = "This is a long spiritual teaching about mindfulness and presence in the current moment."
    title = "Mindfulness 101"
    speaker = "Sri Krishnaji"
    topic = "Meditation"

    # Mock settings.rag_chunk_size to be small for testing
    mock_pipeline._splitter._chunk_size = 50
    mock_pipeline._splitter._chunk_overlap = 0

    chunks = mock_pipeline._split_text(text, title=title, speaker=speaker, topic=topic)

    assert len(chunks) > 1
    for chunk in chunks:
        assert "[Source: Mindfulness 101 | Speaker: Sri Krishnaji | Topic: Meditation]" in chunk
        assert "\n" in chunk


def test_split_text_minimal_metadata(mock_pipeline):
    text = "This is a long spiritual teaching about mindfulness and presence."
    title = "Mindfulness 101"

    # Mock settings.rag_chunk_size
    mock_pipeline._splitter._chunk_size = 50

    chunks = mock_pipeline._split_text(text, title=title)

    assert len(chunks) > 0
    for chunk in chunks:
        assert "[Source: Mindfulness 101]" in chunk
        assert "Speaker:" not in chunk
        assert "Topic:" not in chunk


def test_embed_and_index_teacher_tagging(mock_pipeline):
    # Mock embedding and Qdrant services
    mock_pipeline._embedder.encode_batch = MagicMock(return_value={"dense": [[0.1]*384], "sparse": [None]})
    mock_pipeline._qdrant.upsert_chunks = MagicMock(return_value=1)
    mock_pipeline._qdrant.check_source_exists = MagicMock(return_value=False)

    # 1. Test Sadhguru keyword classification
    mock_pipeline._embed_and_index(
        chunks=["Mindfulness and yoga by Jaggi Vasudev."],
        source_url="http://example.com/some-video",
        title="Isha Kriya Yoga",
        content_type="video",
        speaker="Sadhguru",
        tags=["meditation"]
    )

    called_args = mock_pipeline._qdrant.upsert_chunks.call_args[0]
    metadata_list = called_args[2]
    assert any("teacher:sadhguru" in m["tags"] for m in metadata_list)
    assert any("meditation" in m["tags"] for m in metadata_list)

    # 2. Test Sri Amma Bhagavan keyword classification
    mock_pipeline._embed_and_index(
        chunks=["Oneness meditation and Deeksha from Kalki."],
        source_url="http://example.com/oneness",
        title="Golden Age Movement",
        content_type="video",
        speaker="Unknown",
        tags=["grace"]
    )

    called_args = mock_pipeline._qdrant.upsert_chunks.call_args[0]
    metadata_list = called_args[2]
    assert any("teacher:amma_bhagavan" in m["tags"] for m in metadata_list)

    # 3. Test ISKCON keyword classification
    mock_pipeline._embed_and_index(
        chunks=["Reading from Bhagavad Gita in ISKCON temple."],
        source_url="http://example.com/gita",
        title="Teachings of Prabhupada",
        content_type="video",
        speaker="Prabhupada",
        tags=["devotion"]
    )

    called_args = mock_pipeline._qdrant.upsert_chunks.call_args[0]
    metadata_list = called_args[2]
    assert any("teacher:iskcon" in m["tags"] for m in metadata_list)
