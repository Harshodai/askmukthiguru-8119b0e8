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
import os
import re
import tempfile
import time
from collections.abc import Callable
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _get_cookies_opts() -> dict:
    """Get yt-dlp cookie options. Falls back to Chrome cookies if cookies.txt is not found."""
    import os

    try:
        from services.cookie_helper import ensure_cookies_file

        cookie_path = ensure_cookies_file()
        if cookie_path and os.path.exists(cookie_path):
            return {"cookiefile": cookie_path}
    except Exception as e:
        logger.warning(f"Failed to use automated cookie_helper in youtube_loader: {e}")

    possible_paths = [
        os.path.join(os.getcwd(), "cookies.txt"),
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "cookies.txt",
        ),
        "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/cookies.txt",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return {"cookiefile": path}
    # Fallback to direct Chrome cookie extraction
    return {"cookiesfrombrowser": ("chrome",)}


def _get_js_runtime_opts() -> dict:
    """
    Return yt-dlp Python API options for JavaScript runtime support.

    Required to solve YouTube's nsig (n-parameter) signature challenge.
    Without this, yt-dlp cannot decode download URLs and returns
    'Requested format is not available'.
    """
    import shutil

    node_path = "/opt/homebrew/bin/node"
    if not os.path.exists(node_path):
        node_path = shutil.which("node")

    opts = {
        "remote_components": ["ejs:github"],
    }
    if node_path:
        opts["js_runtimes"] = {"node": {"path": node_path}}
        logger.debug(f"JS runtime: node={node_path}")
    else:
        logger.warning("JS runtime: node not found — nsig challenge may fail")
    return opts


# ============================================================
# URL Utilities
# ============================================================


def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:v=|/)([0-9A-Za-z_-]{11})(?:\?|&|$)",
        r"(?:youtu\.be/)([0-9A-Za-z_-]{11})",
        r"(?:embed/)([0-9A-Za-z_-]{11})",
        r"(?:shorts/)([0-9A-Za-z_-]{11})",
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
        r"youtube\.com/@",
        r"youtube\.com/channel/",
        r"youtube\.com/c/",
        r"youtube\.com/user/",
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
        "quiet": True,
        "extract_flat": True,
        "no_warnings": True,
    }
    ydl_opts.update(_get_cookies_opts())
    # extract_flat=True doesn't need signature solving, but add JS opts for
    # age-restricted / region-locked playlists that need full info extraction
    ydl_opts.update(_get_js_runtime_opts())

    videos = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            result = ydl.extract_info(playlist_url, download=False)
        except Exception as e:
            logger.error(f"Failed to extract playlist/channel info: {e}")
            return []

        if result and "entries" in result:
            for entry in result["entries"]:
                if entry:
                    try:
                        videos.append(
                            {
                                "url": f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                                "title": entry.get("title", "Unknown"),
                                "video_id": entry.get("id", ""),
                                "speaker": entry.get("uploader")
                                or entry.get("channel")
                                or "Unknown",
                                "topic": (
                                    entry.get("categories") or entry.get("tags") or ["Spiritual"]
                                )[0]
                                if (entry.get("categories") or entry.get("tags"))
                                else "Spiritual",
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Skipping playlist entry: {e}")

    logger.info(f"Playlist/Channel: found {len(videos)} videos")
    return videos


# ============================================================
# Tier 1 & 2: YouTube Transcript API v1.x
# ============================================================


def _fetch_youtube_captions(
    video_id: str, languages: list[str], allow_auto: bool = True
) -> Optional[str]:
    """
    Fetch captions using youtube-transcript-api v1.x instance-based API.

    Tries manual captions first, then auto-generated.
    The v1.x API uses instance methods (not static), which fixes the
    XML parsing bug present in v0.6.3.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
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
                logger.warning(
                    f"[{video_id}] Rate limited. Retry {attempt + 1}/{max_retries} in {wait}s"
                )
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
    import glob

    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"

    def run_download():
        with tempfile.TemporaryDirectory() as tmp_dir:
            ydl_opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": languages,
                "subtitlesformat": "vtt/srt/best",
                "outtmpl": f"{tmp_dir}/subs",
                "quiet": True,
                "no_warnings": True,
            }
            ydl_opts.update(_get_cookies_opts())
            # Fix: solve YouTube nsig challenge so format URLs are valid
            ydl_opts.update(_get_js_runtime_opts())

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            sub_files = glob.glob(f"{tmp_dir}/subs*.vtt") + glob.glob(f"{tmp_dir}/subs*.srt")
            if sub_files:
                return _parse_subtitle_file(sub_files[0])
            return None

    try:
        text = run_download()
        if text and text.strip():
            logger.info(f"[{video_id}] ✅ Tier 3 yt-dlp subtitles: {len(text)} chars")
            return text.strip()

        # If failed, refresh cookies once and retry
        logger.warning(
            f"[{video_id}] Tier 3 yt-dlp download failed or yielded no files. Refreshing cookies and retrying..."
        )
        try:
            from services.cookie_helper import ensure_cookies_file

            ensure_cookies_file(force_refresh=True)
        except Exception as e:
            logger.warning(f"Failed to refresh cookies: {e}")

        text = run_download()
        if text and text.strip():
            logger.info(f"[{video_id}] ✅ Tier 3 yt-dlp subtitles (retry): {len(text)} chars")
            return text.strip()

        return None
    except Exception as e:
        logger.warning(f"[{video_id}] Tier 3 yt-dlp download failed: {e}")
        return None


def _parse_subtitle_file(filepath: str) -> Optional[str]:
    """Parse VTT or SRT subtitle file into plain text. Removes timestamps and duplicates."""
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Failed to read subtitle file: {e}")
        return None

    lines = []
    seen = set()

    for line in content.split("\n"):
        # Skip VTT header, timestamps, and empty lines
        if line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if re.match(r"^\d+$", line.strip()):  # SRT sequence number
            continue
        if "-->" in line:  # Timestamp line
            continue
        if not line.strip():
            continue

        clean = re.sub(r"<[^>]+>", "", line)  # Remove HTML tags
        clean = re.sub(r"\{[^}]+\}", "", clean)  # Remove SRT formatting
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
    speaker: str = "Unknown",
    topic: str = "Spiritual",
) -> dict:
    """
    Robust transcript fetcher with optional Transcript Council.

    Tries 3 distinct tiers:
    1. Direct API manual captions
    2. Direct API auto-generated captions
    3. Final fallback: yt-dlp subtitle download (VTT)

    If Transcript Council is enabled:
    - ALSO runs local Whisper large-v3-turbo STT
    - Compares Quality (using punctuations, lengths)
    - Returns the best transcript (winner)

    Returns:
        Dict with 'text', 'source_url', 'title', 'speaker', 'topic', 'method', optionally 'error'
        and 'council' info (youtube_score, sarvam_score, winner)
    """
    import json

    source_url = f"https://www.youtube.com/watch?v={video_id}"
    languages = settings.transcript_languages_list

    # ── Step 0: Check Pre-extracted Transcripts (Tier 0) ──
    # Check transcripts/transcripts.json
    transcripts_json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "transcripts",
        "transcripts.json",
    )
    if os.path.exists(transcripts_json_path):
        try:
            with open(transcripts_json_path, encoding="utf-8") as f:
                data = json.load(f)
                if video_id in data and data[video_id].get("captions"):
                    logger.info(f"[{video_id}] Found pre-extracted transcript in transcripts.json!")
                    return {
                        "text": data[video_id]["captions"],
                        "source_url": source_url,
                        "title": data[video_id].get("title")
                        or data[video_id].get("videoId")
                        or title,
                        "speaker": data[video_id].get("channelName", "Unknown"),
                        "topic": topic,
                        "language": data[video_id].get("language_code"),
                        "method": "pre_extracted_json",
                    }
        except Exception as e:
            logger.warning(f"[{video_id}] Error reading transcripts.json: {e}")

    # Check transcripts/{video_id}.md
    transcript_md_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "transcripts",
        f"{video_id}.md",
    )
    if os.path.exists(transcript_md_path):
        try:
            with open(transcript_md_path, encoding="utf-8") as f:
                content = f.read()
                if "## Transcript" in content:
                    parts = content.split("## Transcript")
                    transcript_text = parts[1].strip()
                    if transcript_text:
                        logger.info(
                            f"[{video_id}] Found pre-extracted transcript in {video_id}.md!"
                        )
                        # extract title if possible
                        parsed_title = title
                        parsed_speaker = ""
                        parsed_language = ""
                        for line in content.split("\n"):
                            if line.startswith("# "):
                                parsed_title = line[2:].strip()
                            elif line.startswith("**Channel:**"):
                                parsed_speaker = line.split("**Channel:**", 1)[1].strip().strip("`")
                            elif line.startswith("**Language:**"):
                                parsed_language = line.split("**Language:**", 1)[1].strip().strip("`")
                        return {
                            "text": transcript_text,
                            "source_url": source_url,
                            "title": parsed_title or title,
                            "speaker": parsed_speaker or speaker,
                            "topic": topic,
                            "language": parsed_language or None,
                            "method": "pre_extracted_md",
                        }
        except Exception as e:
            logger.warning(f"[{video_id}] Error reading {video_id}.md: {e}")

    # ── Step 1: YouTube Captions (Tier 1 + Tier 2) ──
    youtube_text = None

    if os.environ.get("WHISPER_ONLY", "false").lower() == "true":
        logger.info(f"[{video_id}] WHISPER_ONLY mode: skipping YouTube captions")
    else:
        logger.info(f"[{video_id}] Fetching YouTube captions...")
        youtube_text = _fetch_youtube_captions(video_id, languages, allow_auto=(not max_accuracy))

        # Tier 3 fallback: yt-dlp if YouTube API failed
        if not youtube_text:
            logger.info(f"[{video_id}] Tier 3: Trying yt-dlp subtitle download...")
            youtube_text = _tier3_ytdlp_subtitles(video_id, languages)

    # ── Step 2: Council / Whisper Fallback ──
    if (
        settings.enable_transcript_council
        or os.environ.get("WHISPER_ONLY", "false").lower() == "true"
    ):
        logger.info(f"[{video_id}] Running local Whisper large-v3-turbo STT...")
        whisper_text = _run_whisper_stt(video_id)

        # Fallback: if Whisper STT fails (e.g. audio download blocked) and we skipped YouTube captions,
        # fetch YouTube captions now so we don't fail the ingestion entirely.
        if not whisper_text and os.environ.get("WHISPER_ONLY", "false").lower() == "true":
            logger.warning(
                f"[{video_id}] ⚠️ Local Whisper STT failed/blocked. "
                f"Falling back to YouTube captions API..."
            )
            youtube_text = _fetch_youtube_captions(video_id, languages, allow_auto=True)
            if not youtube_text:
                logger.info(
                    f"[{video_id}] Tier 3: Trying yt-dlp subtitle download as final fallback..."
                )
                youtube_text = _tier3_ytdlp_subtitles(video_id, languages)

        from services.whisper_local_service import council_pick_best

        council_result = council_pick_best(youtube_text, whisper_text, video_id)

        chosen_text = council_result["text"]
        method = f"council_{council_result['method']}"
        council_info = {
            "youtube_score": council_result["youtube_score"],
            "whisper_score": council_result.get("whisper_score", 0.0),
            "winner": council_result["winner"],
        }

        if not chosen_text:
            logger.error(f"[{video_id}] ❌ Council: Both sources failed.")
            return {
                "text": "",
                "source_url": source_url,
                "title": title,
                "speaker": speaker,
                "topic": topic,
                "language": None,
                "method": "failed",
                "error": "All transcript extraction methods failed",
                "council": council_info,
            }

        logger.info(
            f"[{video_id}] ✅ Council complete: {method} "
            f"(YT={council_result['youtube_score']:.2f}, WH={council_result.get('whisper_score', 0.0):.2f})"
        )
        return {
            "text": chosen_text,
            "source_url": source_url,
            "title": title,
            "speaker": speaker,
            "topic": topic,
            "language": None,
            "method": method,
            "council": council_info,
        }

    # ── No council: use YouTube only ──
    if youtube_text:
        return {
            "text": youtube_text,
            "source_url": source_url,
            "title": title,
            "speaker": speaker,
            "topic": topic,
            "language": None,
            "method": "youtube_captions",
        }

    logger.error(f"[{video_id}] ❌ All transcript extraction methods failed.")
    return {
        "text": "",
        "source_url": source_url,
        "title": title,
        "speaker": speaker,
        "topic": topic,
        "language": None,
        "method": "failed",
        "error": "All transcript extraction methods failed",
    }


def _run_whisper_stt(video_id: str) -> Optional[str]:
    """Download audio and transcribe via local Whisper STT. Returns text or None."""
    try:
        from services.whisper_local_service import download_audio, transcribe_with_whisper

        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = download_audio(video_id, tmp_dir)
            if not audio_path:
                logger.warning(f"[{video_id}] Whisper STT: audio download failed")
                return None

            return transcribe_with_whisper(video_id, audio_path)
    except Exception as e:
        logger.error(f"[{video_id}] Whisper STT error: {e}")
        return None


# ============================================================
# Concurrent Playlist Extraction (Sequential, Rate-Limit Safe)
# ============================================================


async def fetch_transcripts_concurrent(
    video_list: list[dict],
    max_workers: Optional[int] = None,
    on_progress: Optional[Callable] = None,
) -> list[dict]:
    """
    Fetch transcripts for multiple videos concurrently to speed up playlist extraction,
    using an asyncio.Semaphore to bound concurrency and prevent rate limits.

    Args:
        video_list: List of dicts with 'video_id', 'title', 'url'
        max_workers: Max concurrent requests. Default is settings.ingestion_concurrency (5)
        on_progress: Optional callback(video_index, total, result)

    Returns:
        List of transcript result dicts
    """
    from app.config import settings
    limit = getattr(settings, "transcript_concurrent_workers", 1)
    concurrency = max_workers or getattr(settings, "ingestion_concurrency", 5)
    concurrency = min(concurrency, limit)
    semaphore = asyncio.Semaphore(concurrency)
    total = len(video_list)
    results = [None] * total

    async def fetch_single_video(index: int, video: dict):
        video_id = video.get("video_id", extract_video_id(video.get("url", "")))
        title = video.get("title", "Unknown")

        if not video_id:
            res = {"text": "", "method": "failed", "error": "No video ID"}
        else:
            try:
                async with semaphore:
                    res = await asyncio.to_thread(
                        fetch_transcript_hybrid,
                        video_id,
                        title,
                        False,  # allow auto-captions
                        video.get("speaker", "Unknown"),
                        video.get("topic", "Spiritual"),
                    )
            except Exception as e:
                logger.error(f"Error fetching transcript for {video_id}: {e}", exc_info=True)
                res = {"text": "", "method": "failed", "error": str(e)}
        results[index] = res
        if on_progress:
            try:
                on_progress(index, total, res)
            except Exception:
                pass

    tasks = [fetch_single_video(i, video) for i, video in enumerate(video_list)]
    await asyncio.gather(*tasks)

    success = sum(1 for r in results if r and r.get("method") != "failed")
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
