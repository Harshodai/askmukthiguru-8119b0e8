"""
Mukthi Guru — YouTube Content Loader

Design Patterns:
  - Chain of Responsibility: 3-tier transcript fallback
    1. Official manual captions (fastest, most accurate)
    2. Whisper tiny transcription (fallback, slower)
    3. Auto-generated captions (last resort, lower quality)
  - Adapter Pattern: Wraps youtube-transcript-api and yt-dlp

Handles both single videos and playlists.
"""

import logging
import tempfile
from typing import Optional

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
)

from app.config import settings

logger = logging.getLogger(__name__)


def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats."""
    import re

    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11})(?:\?|&|$)',
        r'(?:youtu\.be/)([0-9A-Za-z_-]{11})',
        r'(?:embed/)([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def is_playlist_url(url: str) -> bool:
    """Check if URL is a YouTube playlist."""
    return "list=" in url


def get_playlist_video_urls(playlist_url: str) -> list[dict]:
    """
    Extract all video URLs from a YouTube playlist using yt-dlp.
    
    Returns list of dicts with 'url', 'title', 'video_id'.
    Uses flat extraction (no download) for speed.
    """
    import yt_dlp

    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'no_warnings': True,
    }

    videos = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            result = ydl.extract_info(playlist_url, download=False)
        except Exception as e:
            logger.error(f"Failed to extract playlist info: {e}")
            return []
        
        if result and 'entries' in result:
            for entry in result['entries']:
                if entry:
                    try:
                        videos.append({
                            'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                            'title': entry.get('title', 'Unknown'),
                            'video_id': entry.get('id', ''),
                        })
                    except Exception as e:
                        logger.warning(f"Skipping playlist entry: {e}")

    logger.info(f"Playlist: found {len(videos)} videos")
    return videos


def fetch_transcript_hybrid(video_id: str, title: str = "") -> dict:
    """
    3-tier fallback transcript fetcher.
    
    Chain of Responsibility:
    1. Manual captions (human-created, highest quality)
    2. Whisper tiny (local transcription, good quality)  
    3. Auto-generated captions (YouTube ML, acceptable quality)
    
    Args:
        video_id: YouTube video ID
        title: Video title for metadata
        
    Returns:
        Dict with 'text', 'source_url', 'title', 'method', 'content_type'
    """
    source_url = f"https://www.youtube.com/watch?v={video_id}"
    
    # === Tier 1: Manual captions ===
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try manual captions first (any language)
        try:
            manual = transcript_list.find_manually_created_transcript(['en', 'hi', 'te'])
            segments = manual.fetch()
            text = " ".join(seg.text for seg in segments)
            logger.info(f"[{video_id}] Tier 1: Manual captions ({manual.language})")
            return {
                "text": text,
                "source_url": source_url,
                "title": title,
                "method": "manual_captions",
                "content_type": "video",
            }
        except NoTranscriptFound:
            pass

    except (TranscriptsDisabled, Exception) as e:
        logger.debug(f"[{video_id}] Tier 1 failed: {e}")

    # === Tier 2: Whisper tiny transcription ===
    try:
        text = _transcribe_with_whisper(video_id)
        if text:
            logger.info(f"[{video_id}] Tier 2: Whisper transcription")
            return {
                "text": text,
                "source_url": source_url,
                "title": title,
                "method": "whisper",
                "content_type": "video",
            }
    except Exception as e:
        logger.debug(f"[{video_id}] Tier 2 failed: {e}")

    # === Tier 3: Auto-generated captions ===
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        auto = transcript_list.find_generated_transcript(['en'])
        segments = auto.fetch()
        text = " ".join(seg.text for seg in segments)
        logger.info(f"[{video_id}] Tier 3: Auto-generated captions")
        return {
            "text": text,
            "source_url": source_url,
            "title": title,
            "method": "auto_captions",
            "content_type": "video",
        }
    except Exception as e:
        logger.warning(f"[{video_id}] All transcript methods failed: {e}")
        return {
            "text": "",
            "source_url": source_url,
            "title": title,
            "method": "failed",
            "content_type": "video",
            "error": str(e),
        }


# Module-level Whisper model cache to avoid reloading on each call
_whisper_model = None
_whisper_model_name = None


def _get_whisper_model():
    """Get or load the Whisper model (cached)."""
    global _whisper_model, _whisper_model_name
    target_model = settings.whisper_model
    if _whisper_model is None or _whisper_model_name != target_model:
        import whisper
        logger.info(f"Loading Whisper model: {target_model}")
        _whisper_model = whisper.load_model(target_model)
        _whisper_model_name = target_model
    return _whisper_model


def _transcribe_with_whisper(video_id: str) -> Optional[str]:
    """
    Download audio and transcribe with Whisper tiny.
    
    Only used as fallback (Tier 2). Downloads audio via yt-dlp,
    runs Whisper tiny on CPU. Model is cached across calls.
    """
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = f"{tmp_dir}/audio"
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
            }],
            'quiet': True,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded file
        import glob
        audio_files = glob.glob(f"{tmp_dir}/audio*")
        if not audio_files:
            return None

        # Transcribe with cached Whisper model
        model = _get_whisper_model()
        result = model.transcribe(audio_files[0])

        return result.get("text", "")
