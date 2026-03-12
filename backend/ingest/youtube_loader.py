"""
Mukthi Guru — YouTube Content Loader (Multi-Strategy)

Design Patterns:
  - Chain of Responsibility: 4-tier transcript fallback
    1. Manual captions via youtube-transcript-api (fastest, most accurate)
    2. faster-whisper local transcription (high accuracy, GPU-accelerated)
    3. yt-dlp subtitle download + VTT parsing (cloud-generated captions)
    4. yt-dlp auto-generated captions as raw text (last resort)
  - Adapter Pattern: Wraps youtube-transcript-api, faster-whisper, and yt-dlp
  - Concurrent Strategy: asyncio.to_thread for parallel playlist ingestion

Supports both single videos and playlists with concurrent extraction.
"""

import asyncio
import logging
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
)

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
# 4-Tier Transcript Extraction
# ============================================================

def fetch_transcript_hybrid(
    video_id: str,
    title: str = "",
    max_accuracy: bool = False,
) -> dict:
    """
    Robust 4-tier transcript fetcher.
    
    Tier 1: Manual captions via youtube-transcript-api (10 Indian languages)
    Tier 2: faster-whisper local transcription (large-v3, GPU-accelerated)
    Tier 3: yt-dlp subtitle download + VTT/SRT parsing
    Tier 4: yt-dlp auto-generated captions as raw text
    
    Each tier is tried in order. Logs the method used for debugging.
    
    Args:
        video_id: YouTube video ID
        title: Video title for metadata
        max_accuracy: If True, skip auto-captions and prefer Whisper
        
    Returns:
        Dict with 'text', 'source_url', 'method', optionally 'error'
    """
    source_url = f"https://www.youtube.com/watch?v={video_id}"
    languages = settings.transcript_languages_list
    
    # ── Tier 1: Manual Captions (youtube-transcript-api) ──
    logger.info(f"[{video_id}] Tier 1: Trying manual captions...")
    text = _tier1_manual_captions(video_id, languages)
    if text:
        logger.info(f"[{video_id}] ✅ Tier 1 success: manual captions ({len(text)} chars)")
        return {"text": text, "source_url": source_url, "title": title, "method": "manual_captions"}
    
    # ── Tier 1b: Auto-generated captions (if not max_accuracy) ──
    if not max_accuracy:
        logger.info(f"[{video_id}] Tier 1b: Trying auto-generated captions...")
        text = _tier1b_auto_captions(video_id, languages)
        if text:
            logger.info(f"[{video_id}] ✅ Tier 1b success: auto captions ({len(text)} chars)")
            return {"text": text, "source_url": source_url, "title": title, "method": "auto_captions"}
    
    # ── Tier 2: faster-whisper Transcription ──
    logger.info(f"[{video_id}] Tier 2: Trying faster-whisper transcription...")
    text = _tier2_faster_whisper(video_id)
    if text:
        logger.info(f"[{video_id}] ✅ Tier 2 success: faster-whisper ({len(text)} chars)")
        return {"text": text, "source_url": source_url, "title": title, "method": "faster_whisper"}
    
    # ── Tier 3: yt-dlp Subtitle Download + VTT Parsing ──
    logger.info(f"[{video_id}] Tier 3: Trying yt-dlp subtitle download...")
    text = _tier3_ytdlp_subtitles(video_id, languages)
    if text:
        logger.info(f"[{video_id}] ✅ Tier 3 success: yt-dlp subtitles ({len(text)} chars)")
        return {"text": text, "source_url": source_url, "title": title, "method": "ytdlp_subtitles"}
    
    # ── All tiers failed ──
    logger.error(f"[{video_id}] ❌ All 3 tiers failed for transcript extraction.")
    return {
        "text": "",
        "source_url": source_url,
        "title": title,
        "method": "failed",
        "error": "All transcript extraction methods failed",
    }


# ============================================================
# Tier 1: Manual Captions (youtube-transcript-api)
# ============================================================

def _tier1_manual_captions(video_id: str, languages: list[str]) -> Optional[str]:
    """
    Fastest and most accurate: fetch manually-created captions.
    Supports 10 Indian languages from config.
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try manually created transcripts first
        try:
            manual = transcript_list.find_manually_created_transcript(languages)
            text = " ".join([t['text'] for t in manual.fetch()])
            return text.strip() if text.strip() else None
        except Exception:
            pass
            
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        logger.debug(f"[{video_id}] Tier 1: {type(e).__name__}")
    except Exception as e:
        logger.warning(f"[{video_id}] Tier 1 error: {e}")
    
    return None


def _tier1b_auto_captions(video_id: str, languages: list[str]) -> Optional[str]:
    """
    Auto-generated YouTube captions. Lower quality but widely available.
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        try:
            auto = transcript_list.find_generated_transcript(languages)
            text = " ".join([t['text'] for t in auto.fetch()])
            return text.strip() if text.strip() else None
        except Exception:
            pass
            
    except (TranscriptsDisabled, NoTranscriptFound):
        pass
    except Exception as e:
        logger.warning(f"[{video_id}] Tier 1b error: {e}")
    
    return None


# ============================================================
# Tier 2: faster-whisper Local Transcription
# ============================================================

# Module-level Whisper model cache
_whisper_model = None
_whisper_model_name = None


def _get_faster_whisper_model():
    """Get or load the faster-whisper model (cached)."""
    global _whisper_model, _whisper_model_name
    target_model = settings.whisper_model
    
    if _whisper_model is None or _whisper_model_name != target_model:
        try:
            from faster_whisper import WhisperModel
            
            # Determine compute type based on available hardware
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                compute_type = settings.whisper_compute_type
            else:
                device = "cpu"
                compute_type = "int8"  # Use int8 on CPU for speed
            
            logger.info(f"Loading faster-whisper model: {target_model} (device={device}, compute={compute_type})")
            _whisper_model = WhisperModel(
                target_model,
                device=device,
                compute_type=compute_type,
            )
            _whisper_model_name = target_model
        except ImportError:
            logger.warning("faster-whisper not installed. Falling back to openai-whisper.")
            return _get_openai_whisper_model()
        except Exception as e:
            logger.error(f"Failed to load faster-whisper: {e}")
            return None
    
    return _whisper_model


def _get_openai_whisper_model():
    """Fallback: load openai-whisper model if faster-whisper fails."""
    global _whisper_model, _whisper_model_name
    target_model = settings.whisper_model
    
    if _whisper_model is None or _whisper_model_name != target_model:
        try:
            import whisper
            logger.info(f"Loading openai-whisper model: {target_model}")
            _whisper_model = whisper.load_model(target_model)
            _whisper_model_name = target_model
        except ImportError:
            logger.error("Neither faster-whisper nor openai-whisper is installed!")
            return None
        except Exception as e:
            logger.error(f"Failed to load openai-whisper: {e}")
            return None
    
    return _whisper_model


def _tier2_faster_whisper(video_id: str) -> Optional[str]:
    """
    Download audio and transcribe with faster-whisper (or openai-whisper fallback).
    
    Uses yt-dlp to download audio, then runs Whisper locally.
    faster-whisper is 4x faster than openai-whisper with same accuracy.
    """
    import yt_dlp
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    model = _get_faster_whisper_model()
    if model is None:
        return None

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

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            logger.error(f"[{video_id}] Audio download failed: {e}")
            return None

        # Find the downloaded file
        import glob
        audio_files = glob.glob(f"{tmp_dir}/audio*")
        if not audio_files:
            logger.error(f"[{video_id}] No audio file found after download")
            return None

        # Transcribe based on backend
        try:
            if settings.whisper_backend == "faster-whisper":
                # faster-whisper returns segments iterator
                segments, info = model.transcribe(
                    audio_files[0],
                    beam_size=5,
                    language=None,  # Auto-detect language
                    vad_filter=True,  # Voice Activity Detection for cleaner output
                )
                text = " ".join([segment.text for segment in segments])
            else:
                # openai-whisper returns dict
                result = model.transcribe(audio_files[0])
                text = result.get("text", "")
            
            return text.strip() if text.strip() else None
            
        except Exception as e:
            logger.error(f"[{video_id}] Whisper transcription failed: {e}")
            return None


# ============================================================
# Tier 3: yt-dlp Subtitle Download + VTT Parsing
# ============================================================

def _tier3_ytdlp_subtitles(video_id: str, languages: list[str]) -> Optional[str]:
    """
    Download subtitles via yt-dlp and parse VTT/SRT format.
    
    This catches cases where youtube-transcript-api fails but
    yt-dlp can still access the subtitle files directly.
    """
    import yt_dlp
    
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
        
        # Find subtitle files
        import glob
        sub_files = glob.glob(f"{tmp_dir}/subs*.vtt") + glob.glob(f"{tmp_dir}/subs*.srt")
        
        if not sub_files:
            logger.debug(f"[{video_id}] Tier 3: No subtitle files downloaded")
            return None
        
        # Parse the first available subtitle file
        text = _parse_subtitle_file(sub_files[0])
        return text.strip() if text and text.strip() else None


def _parse_subtitle_file(filepath: str) -> Optional[str]:
    """
    Parse VTT or SRT subtitle file into plain text.
    Removes timestamps, formatting tags, and duplicate lines.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Failed to read subtitle file: {e}")
        return None
    
    lines = []
    seen = set()
    
    for line in content.split('\n'):
        line = line.strip()
        
        # Skip VTT header
        if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
            continue
        
        # Skip timestamp lines (both VTT and SRT formats)
        if re.match(r'^\d{2}:\d{2}', line) or re.match(r'^\d+$', line):
            continue
        
        # Skip empty lines
        if not line:
            continue
        
        # Remove HTML/VTT formatting tags
        clean = re.sub(r'<[^>]+>', '', line)
        clean = re.sub(r'\{[^}]+\}', '', clean)  # Remove SRT formatting
        clean = clean.strip()
        
        # Deduplicate (YouTube auto-subs often repeat lines)
        if clean and clean not in seen:
            seen.add(clean)
            lines.append(clean)
    
    return " ".join(lines)


# ============================================================
# Concurrent Playlist/Channel Extraction
# ============================================================

async def fetch_transcripts_concurrent(
    video_list: list[dict],
    max_workers: Optional[int] = None,
    on_progress: Optional[callable] = None,
) -> list[dict]:
    """
    Concurrently fetch transcripts for multiple videos using asyncio.to_thread.
    
    Spawns multiple workers to process videos in parallel. Each worker
    uses the 4-tier transcript fallback strategy.
    
    Args:
        video_list: List of dicts with 'video_id', 'title', 'url'
        max_workers: Max concurrent workers (default from config)
        on_progress: Optional callback(video_index, total, result)
        
    Returns:
        List of transcript result dicts
    """
    if max_workers is None:
        max_workers = settings.transcript_concurrent_workers
    
    semaphore = asyncio.Semaphore(max_workers)
    results = []
    total = len(video_list)
    
    async def _process_video(index: int, video: dict):
        async with semaphore:
            video_id = video.get('video_id', extract_video_id(video.get('url', '')))
            title = video.get('title', 'Unknown')
            
            if not video_id:
                result = {"text": "", "method": "failed", "error": "No video ID"}
            else:
                # Run blocking transcript extraction in a thread
                result = await asyncio.to_thread(
                    fetch_transcript_hybrid,
                    video_id,
                    title,
                    False,
                )
            
            if on_progress:
                try:
                    on_progress(index, total, result)
                except Exception:
                    pass
            
            return result
    
    # Launch all tasks concurrently (bounded by semaphore)
    tasks = [_process_video(i, v) for i, v in enumerate(video_list)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle any exceptions in results
    final_results = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error(f"Video {i} failed with exception: {r}")
            final_results.append({
                "text": "",
                "method": "failed",
                "error": str(r),
            })
        else:
            final_results.append(r)
    
    # Log summary
    success = sum(1 for r in final_results if r.get("method") != "failed")
    logger.info(f"Concurrent extraction: {success}/{total} videos successful")
    
    return final_results


async def extract_channel_transcripts(channel_url: str) -> list[dict]:
    """
    Extract transcripts from all videos in a YouTube channel.
    
    Uses yt-dlp to get all video IDs, then processes concurrently.
    """
    logger.info(f"Extracting videos from channel: {channel_url}")
    videos = get_playlist_video_urls(channel_url)
    
    if not videos:
        logger.warning(f"No videos found for channel: {channel_url}")
        return []
    
    logger.info(f"Found {len(videos)} videos. Starting concurrent extraction...")
    return await fetch_transcripts_concurrent(videos)
