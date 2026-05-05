import pytest
from unittest.mock import MagicMock
from ingest.pipeline import IngestionPipeline

@pytest.fixture
def mock_pipeline():
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
