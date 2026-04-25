"""
Mukthi Guru — YouTube Content Loader (Multi-Strategy + Transcript Council)

Design Patterns:
  - Chain of Responsibility: 3-tier transcript fallback (v1.x API)
    1. Manual captions via youtube-transcript-api v1.x
    2. Auto-generated captions via youtube-transcript-api v1.x
    3. yt-dlp subtitle download + VTT parsing (fallback when API rate-limited)
  - Council Pattern: Sarvam Saaras v3 STT runs in parallel for quality comparison
  - Adapter Pattern: Wraps youtube-transcript-api v1.x, Sarvam STT, and yt-dlp

Transcript Council (per video, when enable_transcript_council=True):
  - Fetches captions via Tier 1/2 above
  - ALSO downloads audio and runs Sarvam Batch STT
  - Scores both results on quality heuristics
  - Ingests the best result (or merges both if both are long and close in quality)

Supports both single videos and playlists with sequential extraction (rate-limit safe).
"""

import asyncio
import logging
import re
import tempfile
import time
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ============================================================
# URL Utilities
# ============================================================

def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11})(?:\?|&|$)',
        r'(?:youtu\.be/)([0-9A-Za-z_-]{11})',
        r'(?:embed/)([0-9A-Za-z_-]{11})',
        r'(?:shorts/)([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def is_playlist_url(url: str) -> bool:
    """Check if URL is a YouTube playlist."""
    return "list=" in url


def is_channel_url(url: str) -> bool:
    """Check if URL is a YouTube channel."""
    channel_patterns = [
        r'youtube\.com/@',
        r'youtube\.com/channel/',
        r'youtube\.com/c/',
        r'youtube\.com/user/',
    ]
    return any(re.search(p, url) for p in channel_patterns)


# ============================================================
# Playlist / Channel Extraction
# ============================================================

def get_playlist_video_urls(playlist_url: str) -> list[dict]:
    """
    Extract all video URLs from a YouTube playlist or channel using yt-dlp.

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
            logger.error(f"Failed to extract playlist/channel info: {e}")
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

    logger.info(f"Playlist/Channel: found {len(videos)} videos")
    return videos


# ============================================================
# Tier 1 & 2: YouTube Transcript API v1.x
# ============================================================

def _fetch_youtube_captions(video_id: str, languages: list[str], allow_auto: bool = True) -> Optional[str]:
    """
    Fetch captions using youtube-transcript-api v1.x instance-based API.

    Tries manual captions first, then auto-generated.
    The v1.x API uses instance methods (not static), which fixes the
    XML parsing bug present in v0.6.3.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import (
            TranscriptsDisabled,
            NoTranscriptFound,
        )
    except ImportError:
        logger.error("youtube-transcript-api not installed")
        return None

    api = YouTubeTranscriptApi()
    max_retries = 3

    for attempt in range(max_retries):
        try:
            transcript_list = api.list(video_id)

            # Try manual captions first (highest quality)
            try:
                manual = transcript_list.find_manually_created_transcript(languages)
                fetched = manual.fetch()
                text = " ".join([s.text for s in fetched])
                if text.strip():
                    logger.info(f"[{video_id}] ✅ Manual captions: {len(text)} chars")
                    return text.strip()
            except Exception:
                pass

            # Try auto-generated captions
            if allow_auto:
                try:
                    auto = transcript_list.find_generated_transcript(languages)
                    fetched = auto.fetch()
                    text = " ".join([s.text for s in fetched])
                    if text.strip():
                        logger.info(f"[{video_id}] ✅ Auto captions: {len(text)} chars")
                        return text.strip()
                except Exception:
                    pass

            # No transcripts found for requested languages
            logger.debug(f"[{video_id}] No captions for languages: {languages}")
            return None

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Too Many Requests" in err_str:
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                logger.warning(f"[{video_id}] Rate limited. Retry {attempt+1}/{max_retries} in {wait}s")
                time.sleep(wait)
                continue
            # TranscriptsDisabled, NoTranscriptFound, or other permanent errors
            logger.debug(f"[{video_id}] YouTube captions unavailable: {type(e).__name__}")
            return None

    return None


# ============================================================
# Tier 3: yt-dlp Subtitle Download + VTT Parsing
# ============================================================

def _tier3_ytdlp_subtitles(video_id: str, languages: list[str]) -> Optional[str]:
    """
    Download subtitles via yt-dlp and parse VTT/SRT format.

    Used as fallback when youtube-transcript-api is rate-limited.
    yt-dlp uses a different HTTP path and is less likely to 429.
    """
    import yt_dlp
    import glob

    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': languages,
            'subtitlesformat': 'vtt/srt/best',
            'outtmpl': f"{tmp_dir}/subs",
            'quiet': True,
            'no_warnings': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            logger.warning(f"[{video_id}] Tier 3 yt-dlp download failed: {e}")
            return None

        sub_files = glob.glob(f"{tmp_dir}/subs*.vtt") + glob.glob(f"{tmp_dir}/subs*.srt")

        if not sub_files:
            logger.debug(f"[{video_id}] Tier 3: No subtitle files downloaded")
            return None

        text = _parse_subtitle_file(sub_files[0])
        if text and text.strip():
            logger.info(f"[{video_id}] ✅ Tier 3 yt-dlp subtitles: {len(text)} chars")
            return text.strip()
        return None


def _parse_subtitle_file(filepath: str) -> Optional[str]:
    """Parse VTT or SRT subtitle file into plain text. Removes timestamps and duplicates."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Failed to read subtitle file: {e}")
        return None

    lines = []
    seen = set()

    for line in content.split('\n'):
        # Skip VTT header, timestamps, and empty lines
        if line.startswith('WEBVTT') or line.startswith('NOTE'):
            continue
        if re.match(r'^\d+$', line.strip()):  # SRT sequence number
            continue
        if '-->' in line:  # Timestamp line
            continue
        if not line.strip():
            continue

        clean = re.sub(r'<[^>]+>', '', line)      # Remove HTML tags
        clean = re.sub(r'\{[^}]+\}', '', clean)   # Remove SRT formatting
        clean = clean.strip()

        if clean and clean not in seen:
            seen.add(clean)
            lines.append(clean)

    return " ".join(lines)


# ============================================================
# Main Transcript Fetcher + Council Logic
# ============================================================

def fetch_transcript_hybrid(
    video_id: str,
    title: str = "",
    max_accuracy: bool = False,
) -> dict:
    """
    Robust transcript fetcher with optional Transcript Council.

    Without council (enable_transcript_council=False):
      Tier 1: Manual captions (youtube-transcript-api v1.x)
      Tier 2: Auto-generated captions (youtube-transcript-api v1.x)
      Tier 3: yt-dlp subtitle download + VTT parsing (fallback)

    With council (enable_transcript_council=True, default):
      - Runs Tier 1/2 for YouTube captions
      - ALSO downloads audio and runs Sarvam Saaras v3 Batch STT
      - Scores both, picks winner (or merges if both are long/comparable)

    Args:
        video_id: YouTube video ID
        title: Video title for logging
        max_accuracy: If True, skip auto-captions (manual only before council)

    Returns:
        Dict with 'text', 'source_url', 'title', 'method', optionally 'error'
        and 'council' info (youtube_score, sarvam_score, winner)
    """
    source_url = f"https://www.youtube.com/watch?v={video_id}"
    languages = settings.transcript_languages_list

    # ── Step 1: YouTube Captions (Tier 1 + Tier 2) ──
    youtube_text = None

    logger.info(f"[{video_id}] Fetching YouTube captions...")
    youtube_text = _fetch_youtube_captions(
        video_id, languages,
        allow_auto=(not max_accuracy)
    )

    # Tier 3 fallback: yt-dlp if YouTube API failed
    if not youtube_text:
        logger.info(f"[{video_id}] Tier 3: Trying yt-dlp subtitle download...")
        youtube_text = _tier3_ytdlp_subtitles(video_id, languages)

    # ── Step 2: Council — Sarvam STT ──
    if settings.enable_transcript_council:
        logger.info(f"[{video_id}] Council: Running Sarvam Saaras v3 STT...")
        sarvam_text = _run_sarvam_stt(video_id)

        from services.sarvam_stt_service import council_pick_best
        council_result = council_pick_best(youtube_text, sarvam_text, video_id)

        chosen_text = council_result["text"]
        method = f"council_{council_result['method']}"
        council_info = {
            "youtube_score": council_result["youtube_score"],
            "sarvam_score": council_result["sarvam_score"],
            "winner": council_result["winner"],
        }

        if not chosen_text:
            logger.error(f"[{video_id}] ❌ Council: Both sources failed.")
            return {
                "text": "", "source_url": source_url, "title": title,
                "method": "failed", "error": "All transcript extraction methods failed",
                "council": council_info,
            }

        logger.info(
            f"[{video_id}] ✅ Council complete: {method} "
            f"(YT={council_result['youtube_score']:.2f}, SV={council_result['sarvam_score']:.2f})"
        )
        return {
            "text": chosen_text, "source_url": source_url, "title": title,
            "method": method, "council": council_info,
        }

    # ── No council: use YouTube only ──
    if youtube_text:
        return {"text": youtube_text, "source_url": source_url, "title": title, "method": "youtube_captions"}

    logger.error(f"[{video_id}] ❌ All transcript extraction methods failed.")
    return {
        "text": "", "source_url": source_url, "title": title,
        "method": "failed", "error": "All transcript extraction methods failed",
    }


def _run_sarvam_stt(video_id: str) -> Optional[str]:
    """Download audio and transcribe via Sarvam STT. Returns text or None."""
    try:
        from services.sarvam_stt_service import download_audio, transcribe_with_sarvam

        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = download_audio(video_id, tmp_dir)
            if not audio_path:
                logger.warning(f"[{video_id}] Sarvam STT: audio download failed")
                return None

            return transcribe_with_sarvam(video_id, audio_path)
    except Exception as e:
        logger.error(f"[{video_id}] Sarvam STT error: {e}")
        return None


# ============================================================
# Concurrent Playlist Extraction (Sequential, Rate-Limit Safe)
# ============================================================

async def fetch_transcripts_concurrent(
    video_list: list[dict],
    max_workers: Optional[int] = None,
    on_progress: Optional[callable] = None,
) -> list[dict]:
    """
    Fetch transcripts for multiple videos sequentially to avoid YouTube 429 rate limits.

    Despite the name (kept for API compatibility), this processes one video at a time
    with a 2-second delay between requests. The Transcript Council adds Sarvam STT
    per video, which runs after each YouTube caption fetch.

    Args:
        video_list: List of dicts with 'video_id', 'title', 'url'
        max_workers: Ignored — kept for API compat. Always sequential.
        on_progress: Optional callback(video_index, total, result)

    Returns:
        List of transcript result dicts
    """
    results = []
    total = len(video_list)

    for i, video in enumerate(video_list):
        video_id = video.get('video_id', extract_video_id(video.get('url', '')))
        title = video.get('title', 'Unknown')

        if not video_id:
            result = {"text": "", "method": "failed", "error": "No video ID"}
        else:
            result = await asyncio.to_thread(
                fetch_transcript_hybrid,
                video_id,
                title,
                False,  # allow auto-captions
            )

        results.append(result)

        if on_progress:
            try:
                on_progress(i, total, result)
            except Exception:
                pass

        # Rate-limit delay between videos
        if i < total - 1:
            await asyncio.sleep(2)

    success = sum(1 for r in results if r.get("method") != "failed")
    logger.info(f"Extraction complete: {success}/{total} videos successful")

    return results


async def extract_channel_transcripts(channel_url: str) -> list[dict]:
    """Extract transcripts from all videos in a YouTube channel."""
    logger.info(f"Extracting videos from channel: {channel_url}")
    videos = get_playlist_video_urls(channel_url)

    if not videos:
        logger.warning(f"No videos found for channel: {channel_url}")
        return []

    logger.info(f"Found {len(videos)} videos. Starting extraction...")
    return await fetch_transcripts_concurrent(videos)
