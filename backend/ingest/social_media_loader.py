"""
Mukthi Guru — Social Media & Direct Video Loader

Design Patterns:
  - Strategy Pattern: yt-dlp for any URL yt-dlp supports (Instagram, TikTok, Twitter/X, direct MP4)
  - Adapter Pattern: Normalizes diverse video sources into {text, source_url, title, method}
  - Ponytail: graceful degradation — no exception propagates to caller; errors returned in result dict

Supports:
  - Instagram Reels, Posts, Stories
  - TikTok videos
  - Twitter/X videos
  - Direct video files (MP4, MOV, AVI, WEBM)
  - Any yt-dlp-supported platform

Flow: URL → yt-dlp audio extract → faster-whisper transcription → {text}
"""

import logging
import os
import re
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# Patterns for social media / direct video URL detection
SOCIAL_MEDIA_PATTERNS = [
    re.compile(r"instagram\.com/(reel|p|tv)/", re.IGNORECASE),
    re.compile(r"tiktok\.com/", re.IGNORECASE),
    re.compile(r"twitter\.com/.+/status/", re.IGNORECASE),
    re.compile(r"x\.com/.+/status/", re.IGNORECASE),
]

DIRECT_VIDEO_PATTERN = re.compile(
    r"\.(mp4|mov|avi|webm|mkv|flv|wmv|m4v)(\?.*)?$",
    re.IGNORECASE,
)


def is_social_media_url(url: str) -> bool:
    """Return True if the URL points to a social media video or direct video file."""
    for pattern in SOCIAL_MEDIA_PATTERNS:
        if pattern.search(url):
            return True
    return bool(DIRECT_VIDEO_PATTERN.search(url))


def _get_cookie_opts() -> dict:
    """Reuse existing cookie helper for authentication (same as youtube_loader.py)."""
    try:
        from services.cookie_helper import ensure_cookies_file
        cookie_path = ensure_cookies_file()
        if cookie_path and os.path.exists(cookie_path):
            return {"cookiefile": cookie_path}
    except Exception as e:
        logger.debug(f"cookie_helper unavailable: {e}")

    # Fallback: try cookies.txt in project root
    possible = [
        os.path.join(os.getcwd(), "cookies.txt"),
        "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/cookies.txt",
    ]
    for path in possible:
        if os.path.exists(path):
            return {"cookiefile": path}

    # Last resort: pull from Chrome
    return {"cookiesfrombrowser": ("chrome",)}


async def ingest_social_media(
    url: str,
    whisper_service: Optional[object] = None,
) -> dict:
    """
    Download audio from a social media or direct video URL and transcribe with Whisper.

    Args:
        url: Instagram/TikTok/Twitter/direct video URL
        whisper_service: Optional pre-initialized WhisperLocalService (for DI)

    Returns:
        Dict with keys: text, source_url, title, content_type, method, duration_seconds
        On failure: error key is set, text is empty string.
    """
    import asyncio
    import concurrent.futures

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_outtmpl = os.path.join(tmpdir, "audio.%(ext)s")
        result_info = {}

        # Step 1: Download audio via yt-dlp
        def _download_audio() -> dict:
            try:
                import yt_dlp  # type: ignore
                cookie_opts = _get_cookie_opts()
                ydl_opts = {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "wav",
                            "preferredquality": "0",
                        }
                    ],
                    "outtmpl": audio_outtmpl,
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": False,
                    **cookie_opts,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return {
                        "title": info.get("title") or info.get("id", ""),
                        "duration": info.get("duration") or 0,
                        "uploader": info.get("uploader") or info.get("channel") or "Unknown",
                    }
            except Exception as e:
                logger.warning(f"yt-dlp download failed for {url}: {e}")
                return {"error": str(e)}

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result_info = await loop.run_in_executor(pool, _download_audio)

        if "error" in result_info:
            return {
                "text": "",
                "source_url": url,
                "title": "",
                "content_type": "social_video",
                "method": "yt_dlp_failed",
                "error": result_info["error"],
            }

        # Find the downloaded audio file
        audio_file = None
        for fname in os.listdir(tmpdir):
            if fname.startswith("audio."):
                audio_file = os.path.join(tmpdir, fname)
                break

        if not audio_file or not os.path.exists(audio_file):
            return {
                "text": "",
                "source_url": url,
                "title": result_info.get("title", ""),
                "content_type": "social_video",
                "method": "no_audio_file",
                "error": "Audio extraction produced no file",
            }

        # Step 2: Transcribe with Whisper
        def _transcribe(af: str) -> str:
            nonlocal whisper_service
            try:
                if whisper_service is None:
                    from services.whisper_local_service import WhisperLocalService
                    whisper_service = WhisperLocalService()
                result = whisper_service.transcribe(af)
                if isinstance(result, dict):
                    return result.get("text", "")
                return str(result)
            except Exception as e:
                logger.warning(f"WhisperLocalService failed ({e}), trying faster-whisper directly")
                try:
                    from faster_whisper import WhisperModel  # type: ignore
                    model = WhisperModel("large-v3", device="cpu", compute_type="int8")
                    segments, _ = model.transcribe(af)
                    return " ".join(seg.text for seg in segments)
                except Exception as e2:
                    logger.error(f"faster-whisper direct transcription failed: {e2}")
                    raise

        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                transcript = await loop.run_in_executor(pool, _transcribe, audio_file)
        except Exception as e:
            return {
                "text": "",
                "source_url": url,
                "title": result_info.get("title", ""),
                "content_type": "social_video",
                "method": "whisper_failed",
                "error": str(e),
            }

    return {
        "text": transcript.strip(),
        "source_url": url,
        "title": result_info.get("title", ""),
        "speaker": result_info.get("uploader", "Unknown"),
        "content_type": "social_video",
        "method": "yt_dlp_whisper",
        "duration_seconds": result_info.get("duration", 0),
    }


if __name__ == "__main__":
    import asyncio

    async def _test():
        # Smoke test - will fail gracefully without cookies
        result = await ingest_social_media("https://www.instagram.com/reel/test123/")
        print(f"Result keys: {list(result.keys())}")
        print(f"Method: {result.get('method')}")
        print(f"Error: {result.get('error', 'none')}")

    asyncio.run(_test())
