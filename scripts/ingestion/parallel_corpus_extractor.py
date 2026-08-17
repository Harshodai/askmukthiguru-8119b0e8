#!/usr/bin/env python3
"""
Mukthi Guru — High-Performance Parallel Corpus Extractor
========================================================================
Extracts and packages transcripts across all 20 YouTube playlists in parallel
into the immutable corpus directory (scripts/ingestion/corpus/<video_id>/).

Features:
1. Multi-threaded worker pool (4–8 concurrent workers) for fast caption fetching.
2. Faster-Whisper ASR fallback for videos without captions.
3. Clean prose formatting in transcript.md (0 timestamp clutter for clean Qdrant vector retrieval).
4. Lossless timestamp intervals in canonical_segments.json.
5. Reversible phonetic doctrine terms correction ledger.
6. Complete artifact_manifest.json with SHA-256 integrity hashes.
7. Atomic, resumable progress tracking (scripts/ingestion/parallel_run_progress.json).
8. Live logging to scripts/ingestion/parallel_corpus_run.log.

Usage:
  # Normal foreground execution:
  backend/.venv/bin/python scripts/ingestion/parallel_corpus_extractor.py --workers 6

  # Daemon execution with caffeinate (prevents Mac sleep while running):
  caffeinate -dimsu backend/.venv/bin/python scripts/ingestion/parallel_corpus_extractor.py --workers 6 &
"""

from __future__ import annotations

import argparse
import concurrent.futures
import html
import json
import logging
import os
import random
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Load sibling modules
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

from scripts.ingestion.corpus_engine import (
    CanonicalSegment,
    CorpusEngine,
    SpeakerEvidence,
    compute_sha256,
)

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    import httpx
except ImportError:
    httpx = None

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False


# Logging configuration
LOG_FILE = SCRIPT_DIR / "parallel_corpus_run.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("corpus_extractor")

PROGRESS_FILE = SCRIPT_DIR / "parallel_run_progress.json"

DEFAULT_LANGUAGES = ["en", "hi", "te", "kn", "ta", "mr"]


def resolve_node_path() -> str:
    """Resolve Node.js executable path from NODE_PATH env or PATH."""
    env_node = os.environ.get("NODE_PATH")
    if env_node:
        env_node_path = Path(env_node)
        if env_node_path.is_dir():
            candidate = env_node_path / "node"
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        elif env_node_path.is_file() and os.access(env_node_path, os.X_OK):
            return str(env_node_path)

    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(path_dir) / "node"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    raise FileNotFoundError("Node.js executable not found. Set NODE_PATH or ensure 'node' is on PATH.")


NODE_PATH = resolve_node_path()

# 20 Canonical Ekam Playlists
PLAYLIST_URLS = [
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDt1cdrKnT1AZs4UHpFU5wo",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAVXIxzJLscsY7bdpB8vhxU",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCZoSlsJgsCRwAKSn9k1YuK",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDmh7p1PgnP-_tgUYqyXPtL",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCTBAlMLmObAThmuHcXNEOX",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYA7uSMmmEKwe0Obgz1d1jRc",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYC595WV7FBH289VgWl3b7ag",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYD-DlHYhKWl0emMFdZ1RVRS",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYASfJzL48hq1SCn2R-hgzc0",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBSc9RMV9VRiVmHaMH-O39W",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDEhRkk3-4HfMC4779U5iDU",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBGXFR_4jCmVntbgBa3sx1y",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYASkt24BpnguWFJxbVH9msA",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAmto9MigKY42WaYh3VA9WX",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCAolwoj_qQuhhFdUiwhfpB",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBf8aBXcB4fvJBBHB4qY4Id",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAnKphMrZs9FnKHLvDp5mz9",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBi5t50biQKPGiGVy_tl5x5",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDO8R1tqQyP8K1U0jFqVv2q",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCQhD7VnKx7tZ1lQ5Z4qUqP",
]


def strip_noise(text: str) -> str:
    """Strip bracketed noise and annotations."""
    if not text:
        return ""
    patterns = [
        r"\[Music\]", r"\[Applause\]", r"\[Laughter\]", r"\[Cheering\]", r"\[.*?\]",
        r"\((?:music|applause|laughter|cheering|background noise)\)",
        r"\d{1,2}:\d{2}(:\d{2})?", r"♪.*?♪", r"<[^>]+>",
    ]
    for p in patterns:
        text = re.sub(p, "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def clean_dialogue_and_disfluencies(text: str) -> str:
    """Clean conversational filler words, stutters, and capitalization for pristine RAG retrieval."""
    if not text:
        return ""
    # 1. Strip bracketed noise
    text = strip_noise(text)
    
    # 2. Strip standalone speech filler particles (uh, um, er, ah)
    text = re.sub(r"\b(?:uh|um|er|ah)\b", "", text, flags=re.IGNORECASE)
    
    # 3. Clean stuttered immediate word repetitions ("to to" -> "to", "the the" -> "the")
    text = re.sub(r"\b([a-zA-Z]{2,})\s+\1\b", r"\1", text, flags=re.IGNORECASE)
    
    # 4. Capitalize sentence beginnings after punctuation
    text = re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    
    # 5. Normalize spaces
    return re.sub(r"\s+", " ", text).strip()


def extract_speaker(title: str, description: str = "", uploader: str = "") -> str:
    combined = f"{title} {description} {uploader}".lower()
    has_preethaji = bool(re.search(r"(?:preethaji|prithaji|sri preetha|preetha ji)", combined))
    has_krishnaji = bool(re.search(r"(?:krishnaji|sri krishna|krishna ji)", combined))
    if has_preethaji and has_krishnaji:
        return "Sri Preethaji & Sri Krishnaji"
    if has_preethaji:
        return "Sri Preethaji"
    if has_krishnaji:
        return "Sri Krishnaji"
    return "Sri Preethaji & Sri Krishnaji"


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_discovered": 0,
        "processed": 0,
        "skipped": 0,
        "succeeded": 0,
        "needs_review": 0,
        "failed": 0,
        "completed_videos": {},
        "failed_videos": {},
    }


def save_progress(state: dict) -> None:
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    tmp = PROGRESS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(PROGRESS_FILE)


def discover_playlist_videos(
    playlist_url: str,
    cookies_from_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> list[dict]:
    """Extract flat video metadata list from a YouTube playlist with anti-bot arguments."""
    if yt_dlp is None:
        return []
    ydl_opts: dict[str, Any] = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["default", "-android_sdkless"]}},
    }
    if cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_from_browser, None, None, None)
    elif cookies_file and Path(cookies_file).exists():
        ydl_opts["cookiefile"] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            entries = info.get("entries") or []
            videos = []
            for e in entries:
                if not e:
                    continue
                vid = e.get("id") or e.get("url")
                if vid and len(vid) == 11:
                    videos.append({
                        "video_id": vid,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "title": e.get("title", ""),
                        "uploader": e.get("uploader", "Ekam / O&O Academy"),
                        "duration_seconds": e.get("duration", 0.0),
                    })
            return videos
    except Exception as exc:
        logger.warning(f"Error expanding playlist {playlist_url}: {exc}")
        return []


class VideoProcessor:
    def __init__(
        self,
        corpus_engine: CorpusEngine,
        whisper_model_size: str = "small",
        cookies_from_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
        delay_min: float = 2.0,
        delay_max: float = 4.5,
    ):
        self.engine = corpus_engine
        self.whisper_model_size = whisper_model_size
        self._whisper_model = None
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file
        self.delay_min = delay_min
        self.delay_max = delay_max

    def get_whisper_model(self):
        if self._whisper_model is None and FASTER_WHISPER_AVAILABLE:
            logger.info(f"Loading faster-whisper model ({self.whisper_model_size}) with int8 quantization on Apple Silicon...")
            # int8 compute_type on Apple Silicon delivers 3x faster inference with 50% lower RAM
            self._whisper_model = WhisperModel(
                self.whisper_model_size,
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
            )
        return self._whisper_model

    def process_single_video(self, video: dict, enable_whisper_fallback: bool = True) -> tuple[bool, str, Optional[str]]:
        video_id = video["video_id"]
        v_dir = self.engine.get_video_dir(video_id)
        
        # Check if already processed
        if (v_dir / "artifact_manifest.json").exists():
            try:
                manifest_data = json.loads((v_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
                return True, manifest_data.get("final_quality_state", "trusted"), manifest_data.get("manifest_hash")
            except Exception:
                pass

        title = video.get("title") or video_id
        speaker = video.get("speaker") or extract_speaker(title, "", video.get("uploader", ""))
        uploader = video.get("uploader") or "Ekam / O&O Academy"
        url = video.get("url") or f"https://www.youtube.com/watch?v={video_id}"

        # Human-paced randomized delay before network call
        time.sleep(random.uniform(self.delay_min, self.delay_max))

        # ── Tier 1: youtube-transcript-api ────────────────────────────
        if YouTubeTranscriptApi is not None:
            try:
                api = YouTubeTranscriptApi()
                t_list = None
                for attempt in range(3):
                    try:
                        t_list = api.list(video_id)
                        break
                    except Exception as e:
                        if "429" in str(e) or "Too Many Requests" in str(e):
                            if attempt == 2:
                                raise
                            time.sleep(10 * (attempt + 1))
                        else:
                            raise
                
                snippets = None
                source_tier = None
                lang_used = "en"

                try:
                    manual = t_list.find_manually_created_transcript(DEFAULT_LANGUAGES)
                    snippets = manual.fetch()
                    source_tier = "manual_api"
                    lang_used = getattr(manual, "language_code", "en")
                except Exception:
                    try:
                        auto = t_list.find_generated_transcript(DEFAULT_LANGUAGES)
                        snippets = auto.fetch()
                        source_tier = "auto_api"
                        lang_used = getattr(auto, "language_code", "en")
                    except Exception:
                        pass

                if snippets and source_tier:
                    raw_content = json.dumps([
                        {"start": getattr(s, "start", s.get("start", 0)), "duration": getattr(s, "duration", s.get("duration", 0)), "text": getattr(s, "text", s.get("text", ""))}
                        for s in snippets
                    ], indent=2)
                    raw_path, raw_hash = self.engine.save_raw_source(
                        video_id=video_id, tier=source_tier, language=lang_used, filename="captions.json", content=raw_content
                    )
                    
                    segments = []
                    for idx, s in enumerate(snippets):
                        st = float(getattr(s, "start", s.get("start", 0)))
                        dur = float(getattr(s, "duration", s.get("duration", 2)))
                        raw_t = getattr(s, "text", s.get("text", ""))
                        clean_t = clean_dialogue_and_disfluencies(html.unescape(raw_t))
                        if not clean_t:
                            continue
                        segments.append(CanonicalSegment(
                            segment_id=f"seg_{idx:04d}",
                            start=round(st, 2),
                            end=round(st + dur, 2),
                            text=clean_t,
                            source_tier=source_tier,
                            language=lang_used,
                            confidence=None,
                            confidence_kind="caption_source",
                            speaker_evidence=SpeakerEvidence(
                                channel_or_publisher=uploader,
                                metadata_attribution=speaker,
                                speaker_identity_source="metadata",
                                speaker_role="teacher",
                                speaker_role_source="metadata",
                            ),
                            is_non_speech=False,
                        ))

                    if segments:
                        manifest = self.engine.process_and_package_video(
                            video_info=video,
                            segments=segments,
                            raw_source_path=raw_path,
                            raw_source_hash=raw_hash,
                            duration_seconds=segments[-1].end if segments else 0.0,
                        )
                        return True, manifest.quality_state, manifest.manifest_hash
            except Exception as e:
                logger.debug(f"[{video_id}] youtube-transcript-api failed: {e}")

        # ── Tier 2: yt-dlp Subtitle Scraping ──────────────────────────
        if yt_dlp is not None:
            with tempfile.TemporaryDirectory() as tmp_dir:
                ydl_opts = {
                    "skip_download": True,
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    "subtitleslangs": DEFAULT_LANGUAGES,
                    "subtitlesformat": "vtt/srt/best",
                    "outtmpl": f"{tmp_dir}/subs",
                    "js_runtimes": {"node": {"path": NODE_PATH}},
                    "quiet": True,
                    "no_warnings": True,
                    "sleep_interval_requests": 2.0,
                    "sleep_interval": 5.0,
                    "max_sleep_interval": 15.0,
                    "extractor_retries": 3,
                }
                if self.cookies_from_browser:
                    ydl_opts["cookiesfrombrowser"] = (self.cookies_from_browser, None, None, None)
                elif self.cookies_file and Path(self.cookies_file).exists():
                    ydl_opts["cookiefile"] = self.cookies_file

                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                    sub_files = list(Path(tmp_dir).glob("subs*.vtt")) + list(Path(tmp_dir).glob("subs*.srt"))
                    if sub_files:
                        sub_file = sub_files[0]
                        sub_content = sub_file.read_text(encoding="utf-8", errors="replace")
                        raw_path, raw_hash = self.engine.save_raw_source(
                            video_id=video_id, tier="ytdlp_subs", language="en", filename=sub_file.name, content=sub_content
                        )
                        # Parse cues
                        segments = []
                        seg_idx = 0
                        for line in sub_content.splitlines():
                            if "-->" in line:
                                m = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*-->\s*(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)", line)
                                if m:
                                    parts_s = m.group(1).replace(",", ".").split(":")
                                    sec_s = float(parts_s[-1]) + float(parts_s[-2]) * 60 + (float(parts_s[-3]) * 3600 if len(parts_s) == 3 else 0)
                                    parts_e = m.group(2).replace(",", ".").split(":")
                                    sec_e = float(parts_e[-1]) + float(parts_e[-2]) * 60 + (float(parts_e[-3]) * 3600 if len(parts_e) == 3 else 0)
                                    segments.append(CanonicalSegment(
                                        segment_id=f"seg_{seg_idx:04d}",
                                        start=round(sec_s, 2),
                                        end=round(max(sec_s + 0.5, sec_e), 2),
                                        text="",
                                        source_tier="ytdlp_subs",
                                        language="en",
                                        speaker_evidence=SpeakerEvidence(metadata_attribution=speaker),
                                    ))
                                    seg_idx += 1
                        clean_lines = [clean_dialogue_and_disfluencies(l) for l in sub_content.splitlines() if l and not ("-->" in l) and not l.startswith("WEBVTT")]
                        if clean_lines and segments:
                            chunk_size = max(1, len(clean_lines) // len(segments))
                            for i, seg in enumerate(segments):
                                seg.text = " ".join(clean_lines[i * chunk_size : (i + 1) * chunk_size]).strip()
                            valid_segs = [s for s in segments if s.text]
                            if valid_segs:
                                manifest = self.engine.process_and_package_video(
                                    video_info=video,
                                    segments=valid_segs,
                                    raw_source_path=raw_path,
                                    raw_source_hash=raw_hash,
                                    duration_seconds=valid_segs[-1].end,
                                )
                                return True, manifest.quality_state, manifest.manifest_hash
                except Exception as e:
                    logger.debug(f"[{video_id}] yt-dlp subtitle scrape failed: {e}")

        # ── Tier 3: Local Faster-Whisper ASR Fallback ──────────────────
        if enable_whisper_fallback and FASTER_WHISPER_AVAILABLE and yt_dlp is not None:
            with tempfile.TemporaryDirectory() as tmp_dir:
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": f"{tmp_dir}/audio.%(ext)s",
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}],
                    "js_runtimes": {"node": {"path": NODE_PATH}},
                    "quiet": True,
                    "no_warnings": True,
                    "downloader_args": {"ffmpeg_i": ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]},
                    "sleep_interval_requests": 2.0,
                    "sleep_interval": 5.0,
                    "max_sleep_interval": 15.0,
                    "extractor_retries": 3,
                }
                if self.cookies_from_browser:
                    ydl_opts["cookiesfrombrowser"] = (self.cookies_from_browser, None, None, None)
                elif self.cookies_file and Path(self.cookies_file).exists():
                    ydl_opts["cookiefile"] = self.cookies_file
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                    audio_files = list(Path(tmp_dir).glob("audio*"))
                    if audio_files:
                        target_audio = str(audio_files[0])
                        model = self.get_whisper_model()
                        # VAD filtering skips silent meditation intervals & background music, eliminating hallucinations
                        whisper_segs, info = model.transcribe(
                            target_audio,
                            beam_size=5,
                            vad_filter=True,
                            vad_parameters=dict(min_silence_duration_ms=500),
                        )
                        
                        raw_asr_data = []
                        segments = []
                        for idx, s in enumerate(whisper_segs):
                            clean_t = clean_dialogue_and_disfluencies(s.text)
                            if not clean_t:
                                continue
                            raw_asr_data.append({
                                "segment_id": f"seg_{idx:04d}",
                                "start": round(s.start, 2),
                                "end": round(s.end, 2),
                                "text": clean_t,
                                "avg_logprob": s.avg_logprob,
                                "no_speech_prob": s.no_speech_prob,
                            })
                            segments.append(CanonicalSegment(
                                segment_id=f"seg_{idx:04d}",
                                start=round(s.start, 2),
                                end=round(s.end, 2),
                                text=clean_t,
                                source_tier="local_whisper_audio",
                                language=info.language or "en",
                                confidence=None,
                                confidence_kind="asr_model",
                                speaker_evidence=SpeakerEvidence(
                                    channel_or_publisher=uploader,
                                    metadata_attribution=speaker,
                                    speaker_identity_source="metadata",
                                    speaker_role="teacher",
                                    speaker_role_source="metadata",
                                ),
                                is_non_speech=False,
                            ))

                        if segments:
                            raw_path, raw_hash = self.engine.save_raw_source(
                                video_id=video_id,
                                tier="local_whisper_audio",
                                language=info.language or "en",
                                filename="whisper_segments.json",
                                content=json.dumps(raw_asr_data, indent=2),
                            )
                            manifest = self.engine.process_and_package_video(
                                video_info=video,
                                segments=segments,
                                raw_source_path=raw_path,
                                raw_source_hash=raw_hash,
                                duration_seconds=segments[-1].end,
                            )
                            return True, manifest.quality_state, manifest.manifest_hash
                except Exception as e:
                    logger.warning(f"[{video_id}] Faster-Whisper ASR failed: {e}")

        return False, "dead_lettered", None


def run_parallel_extraction(
    workers: int = 2,
    limit_per_playlist: Optional[int] = None,
    whisper_model: str = "small",
    enable_whisper: bool = True,
    cookies_from_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
    delay_min: float = 2.0,
    delay_max: float = 4.5,
) -> None:
    engine = CorpusEngine()
    processor = VideoProcessor(
        corpus_engine=engine,
        whisper_model_size=whisper_model,
        cookies_from_browser=cookies_from_browser,
        cookies_file=cookies_file,
        delay_min=delay_min,
        delay_max=delay_max,
    )
    progress = load_progress()

    logger.info("=" * 70)
    logger.info("🚀 STARTING MUKTHI GURU PARALLEL CORPUS EXTRACTION")
    logger.info(f"   Concurrent Workers:   {workers}")
    logger.info(f"   Playlists:            {len(PLAYLIST_URLS)}")
    logger.info(f"   Human Delay:          {delay_min}s - {delay_max}s per request")
    logger.info(f"   Browser Cookies:      {cookies_from_browser or cookies_file or 'None'}")
    logger.info(f"   Whisper ASR:          {'Enabled (' + whisper_model + ')' if enable_whisper else 'Disabled'}")
    logger.info(f"   Progress File:        {PROGRESS_FILE}")
    logger.info(f"   Log File:             {LOG_FILE}")
    logger.info("=" * 70)

    # 1. Expand all 20 playlists to discover all videos
    logger.info("🔍 Step 1: Discovering all videos across 20 playlists...")
    all_videos: dict[str, dict] = {}
    for p_idx, p_url in enumerate(PLAYLIST_URLS, 1):
        vids = discover_playlist_videos(
            p_url,
            cookies_from_browser=cookies_from_browser,
            cookies_file=cookies_file,
        )
        if limit_per_playlist:
            vids = vids[:limit_per_playlist]
        logger.info(f"  [Playlist {p_idx:02d}/{len(PLAYLIST_URLS)}] Discovered {len(vids)} videos: {p_url}")
        for v in vids:
            all_videos[v["video_id"]] = v

    total_count = len(all_videos)
    progress["total_discovered"] = total_count
    save_progress(progress)
    logger.info(f"✨ Step 1 Complete: Total Unique Videos Discovered = {total_count}")

    # 2. Filter videos needing processing (already completed in corpus dir are skipped)
    video_list = list(all_videos.values())
    unprocessed = [
        v for v in video_list
        if not (engine.get_video_dir(v["video_id"]) / "artifact_manifest.json").exists()
    ]
    completed_already = total_count - len(unprocessed)
    logger.info(f"📊 Queued for processing: {len(unprocessed)} videos ({completed_already} already completed & skipped).")

    if not unprocessed:
        logger.info("🎉 All videos are already packaged and verified in the corpus!")
        return

    # 3. Parallel Processing Pool
    logger.info(f"⚡ Step 2: Executing parallel worker pool with {workers} threads...")
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_vid = {
            executor.submit(processor.process_single_video, vid_info, enable_whisper): vid_info
            for vid_info in unprocessed
        }

        done_count = 0
        for future in concurrent.futures.as_completed(future_to_vid):
            vid_info = future_to_vid[future]
            v_id = vid_info["video_id"]
            done_count += 1
            try:
                ok, state, m_hash = future.result()
                if ok:
                    progress["completed_videos"][v_id] = {
                        "title": vid_info.get("title", ""),
                        "state": state,
                        "manifest_hash": m_hash,
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }
                    progress["processed"] += 1
                    if state in ["trusted", "trusted_after_review"]:
                        progress["succeeded"] += 1
                    else:
                        progress["needs_review"] += 1
                    logger.info(f"[{done_count}/{len(unprocessed)}] ✅ {v_id} -> {state} ({m_hash[:8] if m_hash else ''}...) | {(vid_info.get('title') or v_id)[:40]}")
                else:
                    progress["failed_videos"][v_id] = {
                        "title": vid_info.get("title") or "",
                        "reason": state,
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                    }
                    progress["failed"] += 1
                    logger.warning(f"[{done_count}/{len(unprocessed)}] ❌ {v_id} -> Failed ({state}) | {(vid_info.get('title') or v_id)[:40]}")
            except Exception as exc:
                progress["failed"] += 1
                progress["failed_videos"][v_id] = {"error": str(exc)}
                logger.error(f"[{done_count}/{len(unprocessed)}] 💥 {v_id} Exception: {exc}")

            # Periodically checkpoint progress
            if done_count % 5 == 0 or done_count == len(unprocessed):
                save_progress(progress)
                elapsed = time.time() - start_time
                rate = done_count / max(1.0, elapsed)
                remaining = len(unprocessed) - done_count
                eta_mins = (remaining / max(0.01, rate)) / 60
                logger.info(f"⏳ Progress: {done_count}/{len(unprocessed)} ({done_count/len(unprocessed)*100:.1f}%) | Speed: {rate*60:.1f} vids/min | ETA: ~{eta_mins:.1f} mins")

    save_progress(progress)
    total_elapsed = (time.time() - start_time) / 60
    logger.info("=" * 70)
    logger.info("🎉 PARALLEL CORPUS EXTRACTION RUN FINISHED!")
    logger.info(f"   Total Videos:    {total_count}")
    logger.info(f"   Processed:       {progress['processed']}")
    logger.info(f"   Needs Review:    {progress['needs_review']}")
    logger.info(f"   Failed:          {progress['failed']}")
    logger.info(f"   Total Time:      {total_elapsed:.1f} minutes")
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Parallel YouTube Corpus Extractor")
    parser.add_argument("--workers", type=int, default=2, help="Number of concurrent threads (default: 2)")
    parser.add_argument("--limit-per-playlist", type=int, default=None, help="Max videos per playlist")
    parser.add_argument("--whisper-model", default="small", help="Whisper model: tiny, base, small, medium, large-v3")
    parser.add_argument("--disable-whisper", action="store_true", help="Disable local ASR fallback")
    parser.add_argument("--cookies-from-browser", default=None, help="Browser to read cookies from (e.g. chrome, brave, safari)")
    parser.add_argument("--cookies", default=None, help="Path to cookies.txt file")
    parser.add_argument("--delay-min", type=float, default=2.0, help="Min human delay in seconds (default: 2.0)")
    parser.add_argument("--delay-max", type=float, default=4.5, help="Max human delay in seconds (default: 4.5)")
    args = parser.parse_args()

    run_parallel_extraction(
        workers=args.workers,
        limit_per_playlist=args.limit_per_playlist,
        whisper_model=args.whisper_model,
        enable_whisper=not args.disable_whisper,
        cookies_from_browser=args.cookies_from_browser,
        cookies_file=args.cookies,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
    )


if __name__ == "__main__":
    main()
