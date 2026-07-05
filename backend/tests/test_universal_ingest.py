import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ingest.pipeline import IngestionPipeline
from ingest.quality_gate import DataQualityGate, DeterministicChecker

@pytest.fixture
def mock_pipeline_deps(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "use_adaptive_chunking", False)

    qdrant = MagicMock()
    embedder = MagicMock()
    ollama = MagicMock()
    
    # Mock embedder encode_batch return
    embedder.encode_batch.return_value = {"dense": [[0.1]*1024], "sparse": [None]}
    
    # Mock ollama generate return for quality score
    ollama.generate = AsyncMock(return_value='{"score": 90, "is_spiritual": true, "reasons": ["Spiritual instruction"]}')

    return qdrant, embedder, ollama

@pytest.mark.asyncio
async def test_deterministic_checker_reel_grace():
    checker = DeterministicChecker()
    
    # 1. Normal text that is too short
    short_text = "Short spiritual text."
    passed, penalty, reasons = checker.check(short_text, source_url="https://youtube.com/watch?v=123")
    assert passed is False  # Fails standard min length (100 chars)

    # 2. Short text from Instagram Reel url should pass the deterministic checks (min_len=30, min_words=5)
    reel_text = "This is a short spiritual teaching about meditation."  # 52 chars, 8 words
    passed_reel, penalty_reel, reasons_reel = checker.check(reel_text, source_url="https://instagram.com/reel/123/")
    assert passed_reel is True  # passes with grace period
    assert penalty_reel < 50

    # 3. Short text from YouTube Shorts url
    passed_short, _, _ = checker.check(reel_text, source_url="https://youtube.com/shorts/123")
    assert passed_short is True

    # 4. Short text from TikTok url
    passed_tiktok, _, _ = checker.check(reel_text, source_url="https://tiktok.com/@user/video/123")
    assert passed_tiktok is True


@pytest.mark.asyncio
async def test_universal_ingest_delegation(mock_pipeline_deps):
    qdrant, embedder, ollama = mock_pipeline_deps
    pipeline = IngestionPipeline(qdrant, embedder, ollama)

    # Mock the actual execution methods in IngestionPipeline
    pipeline._ingest_video = AsyncMock(return_value={"status": "success", "chunks_indexed": 5})
    pipeline._ingest_video_enhanced = AsyncMock(return_value={"status": "success", "chunks_indexed": 5})
    pipeline._ingest_playlist = AsyncMock(return_value={"status": "success", "chunks_indexed": 10})
    pipeline._ingest_image = AsyncMock(return_value={"status": "success", "chunks_indexed": 1})
    pipeline._ingest_social_media_video = AsyncMock(return_value={"status": "success", "chunks_indexed": 2})

    # Test YouTube single video URL
    res = await pipeline.ingest_url("https://youtube.com/watch?v=11charvidid")
    assert pipeline._ingest_video.called
    assert res["chunks_indexed"] == 5

    # Test YouTube playlist URL
    res = await pipeline.ingest_url("https://youtube.com/playlist?list=PL123")
    assert pipeline._ingest_playlist.called

    # Test Image URL
    res = await pipeline.ingest_url("https://example.com/lotus.png")
    assert pipeline._ingest_image.called

    # Test Social Media URL (Instagram Reel)
    res = await pipeline.ingest_url("https://www.instagram.com/reel/C8P123/")
    assert pipeline._ingest_social_media_video.called
