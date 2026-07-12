from unittest.mock import patch

import pytest

from ingest.youtube_loader import fetch_transcripts_concurrent


@pytest.mark.asyncio
async def test_fetch_transcripts_concurrent_exception_safety():
    video_list = [
        {"url": "https://www.youtube.com/watch?v=video111111", "title": "Video 1"},
        {"url": "https://www.youtube.com/watch?v=video222222", "title": "Video 2"},
    ]

    # Mock fetch_transcript_hybrid: raise exception for video111111, succeed for video222222
    def mock_fetch_hybrid(video_id, title, allow_auto, speaker, topic):
        if video_id == "video111111":
            raise RuntimeError("YouTube API error")
        return {"text": f"Transcript for {title}", "method": "youtube_captions"}

    with patch("ingest.youtube_loader.fetch_transcript_hybrid", side_effect=mock_fetch_hybrid), \
         patch("app.config.settings.ingestion_concurrency", 2):
        
        results = await fetch_transcripts_concurrent(video_list)
        
        assert len(results) == 2
        
        # First video should be recorded as a failure and not raise an exception
        assert results[0]["method"] == "failed"
        assert "YouTube API error" in results[0]["error"]
        
        # Second video should succeed
        assert results[1]["method"] == "youtube_captions"
        assert results[1]["text"] == "Transcript for Video 2"
