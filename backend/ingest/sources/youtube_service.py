"""
YouTube ingestion orchestration — 4-tier transcript fallback chain.

Tiers (applied in order):
  1. fetch_transcript_hybrid — watch page scrape → yt-dlp → youtube-transcript-api → Whisper council
  2. fetch_transcript_supadata — managed API fallback (Supadata)

This is a thin orchestration shell. All actual transcript fetching logic
lives in the existing functions in youtube_loader.py and supadata.py.
"""

import logging
from typing import Optional

from ingest.sources.supadata import fetch_transcript_supadata
from ingest.youtube_loader import extract_video_id, fetch_transcript_hybrid

logger = logging.getLogger(__name__)


class YouTubeIngestionService:
    """Orchestrates the multi-tier YouTube transcript fallback chain."""

    def can_handle(self, url: str) -> bool:
        return "youtube.com" in url or "youtu.be" in url

    def get_source_id(self, url: str) -> str:
        vid = extract_video_id(url)
        return vid or url

    @staticmethod
    def all_strategies_exhausted(video_id: str) -> dict:
        return {
            "error": "All transcript strategies exhausted",
            "video_id": video_id,
        }

    def extract_transcript(
        self,
        video_id: str,
        language: str = "en",
        max_accuracy: bool = False,
    ) -> dict:
        """Try 4-tier fallback chain, return first successful transcript.

        Tier 1: fetch_transcript_hybrid — watch page → yt-dlp → API → Whisper council
        Tier 2: Supadata managed API
        Tier 3: Audio download → ffmpeg → STT → polish

        Returns result dict from whichever tier succeeds, or
        all_strategies_exhausted dict when all fail.
        """
        tier1 = self._try_tier1(video_id, max_accuracy)
        if tier1 is not None:
            return tier1

        tier2 = self._try_tier2(video_id, language)
        if tier2 is not None:
            return tier2

        tier3 = self._try_audio_transcribe_fallback(video_id)
        if tier3 is not None:
            return tier3

        return self.all_strategies_exhausted(video_id)

    def _try_tier1(self, video_id: str, max_accuracy: bool) -> Optional[dict]:
        try:
            result = fetch_transcript_hybrid(video_id, max_accuracy=max_accuracy)
            if result and not result.get("error"):
                logger.info(
                    "[%s] Tier 1 (hybrid) succeeded: method=%s",
                    video_id,
                    result.get("method"),
                )
                return result
        except Exception as e:
            logger.warning("[%s] Tier 1 (hybrid) failed: %s", video_id, e)
        return None

    def _try_tier2(self, video_id: str, language: str) -> Optional[dict]:
        try:
            result = fetch_transcript_supadata(video_id, language)
            if result:
                logger.info("[%s] Tier 2 (Supadata) succeeded", video_id)
                return result
        except Exception as e:
            logger.warning("[%s] Tier 2 (Supadata) failed: %s", video_id, e)
        return None

    def _try_audio_transcribe_fallback(self, video_id: str) -> Optional[dict]:
        """Tier 3: Download audio, downsample with ffmpeg, transcribe & polish via LLM."""
        try:
            from ingest.audio_transcriber import (
                compress_audio_to_mono,
                download_audio_stream,
                is_safe_public_url,
                transcribe_and_preprocess_audio,
            )
            url = f"https://www.youtube.com/watch?v={video_id}"
            if not is_safe_public_url(url):
                return None
            import tempfile
            from pathlib import Path
            with tempfile.TemporaryDirectory(prefix="mukthi-yt-audio-") as tmp_str:
                work_dir = Path(tmp_str)
                downloaded = download_audio_stream(url, work_dir)
                compressed = compress_audio_to_mono(downloaded, work_dir)
                transcribed = transcribe_and_preprocess_audio(
                    str(compressed), output_dir=work_dir, should_polish=True
                )
                if transcribed and not transcribed.startswith("[Transcript for"):
                    return {"text": transcribed, "method": "audio_transcribe_fallback", "video_id": video_id}
            return None
        except Exception as e:
            logger.warning("[%s] Audio transcribe fallback error: %s", video_id, e)
        return None



if __name__ == "__main__":
    svc = YouTubeIngestionService()

    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert svc.can_handle(test_url), "can_handle: youtube.com"
    assert svc.can_handle("https://youtu.be/dQw4w9WgXcQ"), "can_handle: youtu.be"
    assert not svc.can_handle("https://example.com"), "can_handle: non-youtube"
    assert not svc.can_handle(""), "can_handle: empty"

    assert svc.get_source_id(test_url) == "dQw4w9WgXcQ", "get_source_id: watch URL"
    assert svc.get_source_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ", "get_source_id: short URL"
    assert svc.get_source_id("garbage") == "garbage", "get_source_id: fallback to input"

    exhausted = YouTubeIngestionService.all_strategies_exhausted("dQw4w9WgXcQ")
    assert exhausted["error"] == "All transcript strategies exhausted"
    assert exhausted["video_id"] == "dQw4w9WgXcQ"

    print("All self-checks passed")
