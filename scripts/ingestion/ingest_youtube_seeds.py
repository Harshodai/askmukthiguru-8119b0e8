#!/usr/bin/env python3
"""
Mukthi Guru — YouTube Playlist Ingestion Script
=================================================
Ingests two core YouTube playlists into the Qdrant knowledge base
via the IngestionPipeline. Uses playlist URL extraction → per-video
transcript fetching → chunking → embedding → Qdrant upsert.

Includes staggered delays between videos to mitigate YouTube API
rate-limiting (429 errors).

Usage (run inside Docker backend container):
    python3 scripts/ingest_youtube_seeds.py

Or from host:
    docker exec mukthiguru-backend python3 scripts/ingest_youtube_seeds.py
"""

import sys
import os
import asyncio
import time

# Add backend to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.dependencies import get_container

# ── Core Playlists ──────────────────────────────────────────────────────────
# These are the two primary teaching playlists to ingest.
PLAYLIST_URLS = [
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCZoSlsJgsCRwAKSn9k1YuK",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBGXFR_4jCmVntbgBa3sx1y",
]

# Original 4 core video IDs (keep as individual fallbacks)
CORE_VIDEO_IDS = [
    "69IrsSXeBTg",  # Soul Sync
    "igSp4H0OWLE",  # Serene Mind
    "TqxxCYnAxo8",  # Beautiful State
    "O-6f5wQXSu8",  # Daily Reflection
]

# Delay between videos to avoid YouTube 429 rate-limiting (seconds)
INTER_VIDEO_DELAY = 5


async def ingest_playlist(pipeline, playlist_url: str, results: dict):
    """Ingest a full playlist, tracking results and errors."""
    print(f"\n{'='*70}")
    print(f"[Playlist] Starting: {playlist_url}")
    print(f"{'='*70}")

    try:
        result = await pipeline.ingest_url(playlist_url, max_accuracy=True)
        status = result.get("status", "unknown")
        chunks = result.get("chunks_indexed", 0)
        videos_ok = result.get("metadata", {}).get("videos_processed", 0)
        videos_fail = result.get("metadata", {}).get("videos_failed", 0)

        results["playlists_done"] += 1
        results["total_chunks"] += chunks
        results["total_videos_ok"] += videos_ok
        results["total_videos_fail"] += videos_fail

        print(f"\n[Playlist] ✅ Complete: {playlist_url}")
        print(f"  Status: {status}")
        print(f"  Chunks Indexed: {chunks}")
        print(f"  Videos Processed: {videos_ok}")
        print(f"  Videos Failed: {videos_fail}")

    except Exception as e:
        results["total_videos_fail"] += 1
        print(f"\n[Playlist] ❌ Error: {playlist_url}")
        print(f"  {type(e).__name__}: {e}")


async def ingest_individual_video(pipeline, video_id: str, results: dict):
    """Ingest a single video by ID."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"\n[Video] Ingesting: {url}")

    try:
        result = await pipeline.ingest_url(url, max_accuracy=True)
        status = result.get("status", "unknown")
        chunks = result.get("chunks_indexed", 0)
        title = result.get("metadata", {}).get("title", "Unknown")

        results["total_chunks"] += chunks
        results["total_videos_ok"] += 1

        print(f"  ✅ {title}")
        print(f"  Status: {status} | Chunks: {chunks}")

    except Exception as e:
        results["total_videos_fail"] += 1
        print(f"  ❌ Error: {type(e).__name__}: {e}")


async def main():
    start_time = time.time()

    print("=" * 70)
    print("Mukthi Guru — YouTube Knowledge Base Ingestion")
    print("=" * 70)

    # Set environment defaults
    os.environ.setdefault("LLM_PROVIDER", "ollama")

    print("\nInitializing Service Container...")
    container = get_container()
    pipeline = container.ingestion

    results = {
        "playlists_done": 0,
        "total_chunks": 0,
        "total_videos_ok": 0,
        "total_videos_fail": 0,
    }

    # Phase 1: Ingest the two playlists (these handle rate-limiting internally)
    print(f"\n📋 Phase 1: Ingesting {len(PLAYLIST_URLS)} playlists...")
    for playlist_url in PLAYLIST_URLS:
        await ingest_playlist(pipeline, playlist_url, results)
        # Delay between playlists
        if playlist_url != PLAYLIST_URLS[-1]:
            print(f"\n⏳ Waiting {INTER_VIDEO_DELAY}s before next playlist...")
            await asyncio.sleep(INTER_VIDEO_DELAY)

    # Phase 2: Ingest individual core videos (if not already covered by playlists)
    print(f"\n📋 Phase 2: Ingesting {len(CORE_VIDEO_IDS)} core individual videos...")
    for vid_id in CORE_VIDEO_IDS:
        await ingest_individual_video(pipeline, vid_id, results)
        await asyncio.sleep(INTER_VIDEO_DELAY)

    # Summary
    elapsed = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"INGESTION COMPLETE")
    print(f"{'='*70}")
    print(f"  Playlists processed: {results['playlists_done']}/{len(PLAYLIST_URLS)}")
    print(f"  Videos succeeded:    {results['total_videos_ok']}")
    print(f"  Videos failed:       {results['total_videos_fail']}")
    print(f"  Total chunks:        {results['total_chunks']}")
    print(f"  Elapsed time:        {elapsed/60:.1f} minutes")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
