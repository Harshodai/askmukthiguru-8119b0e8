#!/usr/bin/env python3
"""
Mukthi Guru — Host-Side YouTube Ingestion (Whisper Local)
=========================================================
Ingests YouTube playlists using local Whisper STT on Apple Silicon.
Runs on the host machine to leverage the Apple Neural Engine/Metal.

Usage:
    python3 scripts/ingest_host_whisper.py
"""

import sys
import os
import asyncio
import time
import logging

# 1. Setup paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

os.environ["LLM_PROVIDER"] = "ollama"
os.environ["OLLAMA_MODEL"] = "deepseek-r1:7b"
os.environ["SARVAM_API_KEY"] = "none"
os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["REDIS_URL"] = "redis://:mukthiguru_redis_pass@localhost:6379/0"
os.environ["SUPABASE_URL"] = "http://localhost:54321"
os.environ["ENABLE_TRANSCRIPT_COUNCIL"] = "true"
os.environ["WHISPER_ONLY"] = "true"

# 3. Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("ingest_host")

# Ensure system tools and venv tools are in path
VENV_BIN = os.path.abspath(os.path.join(BASE_DIR, ".venv_host/bin"))
os.environ["PATH"] = f"{VENV_BIN}:/opt/homebrew/bin:/usr/local/bin:{os.environ['PATH']}"
logger.info(f"Effective PATH: {os.environ['PATH']}")
logger.info(f"VENV_BIN exists: {os.path.exists(VENV_BIN)}")
logger.info(f"yt-dlp in VENV_BIN: {os.path.exists(os.path.join(VENV_BIN, 'yt-dlp'))}")

# 4. Import app components
from app.config import settings
from app.dependencies import get_container

# ── Core Playlists ──────────────────────────────────────────────────────────
PLAYLIST_URLS = [
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCZoSlsJgsCRwAKSn9k1YuK", # Preethaji
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBGXFR_4jCmVntbgBa3sx1y", # Krishnaji
]

INTER_VIDEO_DELAY = 5

async def ingest_playlist(pipeline, playlist_url: str, results: dict):
    """Ingest a full playlist."""
    logger.info(f"Starting Playlist Ingestion: {playlist_url}")
    try:
        # Ingest URL will use YouTubeLoader which now uses whisper_local_service
        result = await pipeline.ingest_url(playlist_url, max_accuracy=True)
        
        status = result.get("status", "unknown")
        chunks = result.get("chunks_indexed", 0)
        videos_ok = result.get("metadata", {}).get("videos_processed", 0)
        videos_fail = result.get("metadata", {}).get("videos_failed", 0)

        results["playlists_done"] += 1
        results["total_chunks"] += chunks
        results["total_videos_ok"] += videos_ok
        results["total_videos_fail"] += videos_fail

        logger.info(f"✅ Playlist Complete: {playlist_url}")
        logger.info(f"   Chunks: {chunks} | Success: {videos_ok} | Fail: {videos_fail}")

    except Exception as e:
        results["total_videos_fail"] += 1
        logger.error(f"❌ Playlist Error: {playlist_url}")
        logger.error(f"   {type(e).__name__}: {e}", exc_info=True)

async def main():
    start_time = time.time()
    logger.info("=" * 70)
    logger.info("Mukthi Guru — Host-Side Knowledge Ingestion (Whisper Local)")
    logger.info("=" * 70)

    # Initialize Container (will use host-local settings)
    logger.info("Initializing Service Container...")
    container = get_container()
    pipeline = container.ingestion

    results = {
        "playlists_done": 0,
        "total_chunks": 0,
        "total_videos_ok": 0,
        "total_videos_fail": 0,
    }

    # Ingest Playlists
    for playlist_url in PLAYLIST_URLS:
        await ingest_playlist(pipeline, playlist_url, results)
        if playlist_url != PLAYLIST_URLS[-1]:
            logger.info(f"Waiting {INTER_VIDEO_DELAY}s before next playlist...")
            await asyncio.sleep(INTER_VIDEO_DELAY)

    # Summary
    elapsed = time.time() - start_time
    logger.info("=" * 70)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 70)
    logger.info(f"  Playlists: {results['playlists_done']}/{len(PLAYLIST_URLS)}")
    logger.info(f"  Videos OK: {results['total_videos_ok']}")
    logger.info(f"  Videos Fail: {results['total_videos_fail']}")
    logger.info(f"  Total Chunks: {results['total_chunks']}")
    logger.info(f"  Elapsed: {elapsed/60:.1f} minutes")
    logger.info("=" * 70)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
