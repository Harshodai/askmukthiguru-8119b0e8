"""
Unit tests for AgentReach patterns integrated into AskMukthiGuru.

Verifies:
  1. Web scraping via Jina Reader + BeautifulSoup fallback in ingest/web_scraper.py
  2. RSS feed parsing via feedparser
  3. LLM-based zero-edit transcript polisher in services/transcript_polisher.py
  4. Audio transcriber pipeline, SSRF checks, and chunking in ingest/audio_transcriber.py
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingest.audio_transcriber import (
    chunk_audio_keyframe_segments,
    compress_audio_to_mono,
    is_safe_public_url,
)
from ingest.web_scraper import parse_rss_feed, scrape_and_clean_web_article
from services.transcript_polisher import polish_transcript


def test_is_safe_public_url_security():
    """Verify SSRF validation blocks private IPs and internal metadata hosts."""
    assert is_safe_public_url("https://example.com/article") is True
    assert is_safe_public_url("https://www.youtube.com/watch?v=12345") is True

    # Blocked SSRF attempts
    assert is_safe_public_url("http://localhost:8000") is False
    assert is_safe_public_url("http://127.0.0.1/admin") is False
    assert is_safe_public_url("http://10.0.0.1/internal") is False
    assert is_safe_public_url("http://192.168.1.1/router") is False
    assert is_safe_public_url("http://metadata.google.internal") is False
    assert is_safe_public_url("ftp://example.com/file") is False


@pytest.mark.asyncio
async def test_web_scraper_jina_fallback():
    """Verify web_scraper uses Jina Reader or falls back to BeautifulSoup."""
    mock_is_safe = lambda url: True

    # Case 1: Jina fails -> BeautifulSoup fallback
    with patch("ingest.web_scraper.fetch_web_article_jina", new=AsyncMock(return_value=None)):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        async def fake_aiter_bytes(chunk_size=8192):
            yield b"<html><body><p>Spiritual wisdom article text</p></body></html>"

        mock_response.aiter_bytes = fake_aiter_bytes

        mock_client = MagicMock()
        mock_client.stream.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_client.stream.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("ingest.web_scraper.get_client", new=AsyncMock(return_value=mock_client)):
            result = await scrape_and_clean_web_article("https://example.com/wisdom", mock_is_safe)
            assert "Spiritual wisdom article text" in result

    # Case 2: Jina succeeds
    jina_content = "# Spiritual Article\n\nPure clean markdown text from Jina Reader"
    with patch("ingest.web_scraper.fetch_web_article_jina", new=AsyncMock(return_value=jina_content)):
        result = await scrape_and_clean_web_article("https://example.com/wisdom", mock_is_safe)
        assert "Pure clean markdown text from Jina Reader" in result


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_compress_and_chunk_audio(tmp_path):
    """Verify mono/16kHz compression and keyframe-segment chunking against a real ffmpeg run."""
    src = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-y", str(src)],
        check=True,
    )

    compressed = compress_audio_to_mono(src, tmp_path)
    assert compressed.exists()
    assert compressed.suffix == ".m4a"

    chunks = chunk_audio_keyframe_segments(compressed, tmp_path, segment_seconds=1)
    assert len(chunks) >= 1
    assert all(c.exists() for c in chunks)


def test_parse_rss_feed():
    """Verify RSS feed parsing using feedparser."""
    import sys

    mock_feedparser = MagicMock()
    mock_item = MagicMock()
    mock_item.title = "Discourse 1: Finding Peace"
    mock_item.link = "https://example.com/episode1"
    mock_item.published = "2026-07-23"
    mock_item.summary = "A deep discourse on peace."

    mock_feed = MagicMock()
    mock_feed.entries = [mock_item]
    mock_feedparser.parse.return_value = mock_feed

    with patch.dict(sys.modules, {"feedparser": mock_feedparser}):
        entries = parse_rss_feed("https://example.com/rss.xml", max_entries=5)
        assert len(entries) == 1
        assert entries[0]["title"] == "Discourse 1: Finding Peace"
        assert entries[0]["link"] == "https://example.com/episode1"



@pytest.mark.asyncio
async def test_transcript_polisher():
    """Verify transcript polishing via LLM service."""
    raw_text = "welcome everyone today we talk about spiritual peace and inner stillness"
    mock_response = MagicMock()
    mock_response.content = "Welcome everyone. Today, we talk about spiritual peace and inner stillness."

    mock_llm_service = MagicMock()
    mock_llm_service.generate = AsyncMock(return_value=mock_response)

    polished = await polish_transcript(raw_text, llm_service=mock_llm_service)
    assert polished == "Welcome everyone. Today, we talk about spiritual peace and inner stillness."
    mock_llm_service.generate.assert_called_once()
