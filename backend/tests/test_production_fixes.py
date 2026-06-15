from unittest.mock import MagicMock, AsyncMock
import pytest
import asyncio
import hashlib
from app.config import settings
from ingest.pipeline import IngestionPipeline, IngestionCheckpoint
from app.pipeline import PipelineCoordinator
from app.pipeline.result import PipelineResult

def test_cache_config_settings():
    assert settings.semantic_cache_similarity == 0.92
    assert settings.semantic_cache_ttl == 604800
    assert settings.guardrails_llm_enabled is False

@pytest.mark.asyncio
async def test_proactive_serene_mind_dict_return(monkeypatch):
    container = MagicMock()
    container.serene_mind = None
    container.user_profile = MagicMock()
    
    coordinator = PipelineCoordinator(container)
    assessment = MagicMock()
    chat_body = MagicMock()
    state = {}
    
    result = await coordinator._maybe_trigger_proactive_serene_mind(
        assessment, "test-user", chat_body, state
    )
    assert isinstance(result, dict)
    assert result == {"triggered": False}

@pytest.mark.asyncio
async def test_ingestion_deduplication(tmp_path, monkeypatch):
    checkpoint_file = tmp_path / "ingest_checkpoint.json"
    
    # Mock IngestionCheckpoint load/save path
    def mock_init(self, filepath=checkpoint_file):
        from pathlib import Path
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(exist_ok=True)
        self.processed_chunks = self._load()
    
    monkeypatch.setattr(IngestionCheckpoint, "__init__", mock_init)
    
    qdrant = MagicMock()
    embedder = MagicMock()
    ollama = MagicMock()
    pipeline = IngestionPipeline(qdrant, embedder, ollama)
    
    pipeline._split_text = MagicMock(return_value=["chunk1", "chunk2"])
    pipeline._augment_chunks = AsyncMock(return_value=["aug1", "aug2"])
    pipeline._embed_and_index = MagicMock(return_value=2)
    pipeline._raptor.build_tree = AsyncMock(return_value=1)
    
    text = "Hello world! This is a test spiritual teaching."
    
    res1 = await pipeline.ingest_raw_text(text, "url1", "title1")
    assert res1["status"] == "success"
    assert res1["chunks_indexed"] > 0
    
    res2 = await pipeline.ingest_raw_text(text, "url1", "title1")
    assert res2["status"] == "success"
    assert res2["chunks_indexed"] == 0
    assert "already processed" in res2["message"]

def test_hierarchical_split_sentence_boundaries():
    qdrant = MagicMock()
    embedder = MagicMock()
    ollama = MagicMock()
    
    import numpy as np
    embedder.encode = MagicMock(return_value=[np.array([0.1]*128) for _ in range(3)])
    
    pipeline = IngestionPipeline(qdrant, embedder, ollama)
    
    text = "This is first sentence. This is second sentence. This is third sentence."
    child_texts, child_metadatas = pipeline._hierarchical_split(text, title="Test Title")
    
    assert len(child_texts) > 0
    for child in child_texts:
        assert "[Source: Test Title]" in child
        actual_text = child.split("]\n", 1)[1]
        assert actual_text.endswith(".") or actual_text.endswith("!") or actual_text.endswith("?")
