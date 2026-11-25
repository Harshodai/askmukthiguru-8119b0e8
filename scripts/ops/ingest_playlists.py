#!/usr/bin/env python3
"""
Legacy Playlist Transcript Candidate Preview — read-only, no knowledge-store writes.

Target Playlists:
1. `PLOVU2e0ZosYCTKE3_cQvMGNUwB4LeXXjI` (Sri Preethaji & Sri Krishnaji Direct Seeker Interactions & Satsangs)
2. `PLOVU2e0ZosYBGXFR_4jCmVntbgBa3sx1y` (Sri Preethaji & Sri Krishnaji Live Q&A and Discourses)

Extracts untrusted transcript-derived candidate exemplars for human review only. This legacy path does not establish rights clearance or speaker identity, so it cannot write tone vectors to Qdrant or ontology records to Memgraph.
"""

import asyncio
import json
import logging
import os
import re
import sys
import urllib.request

# Load env before imports
env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env")
if os.path.exists(env_path):
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except ImportError:
        pass

provider = os.getenv("LLM_PROVIDER", "sarvam_cloud")
if not os.getenv("SARVAM_API_KEY") and (not provider or provider == "sarvam_cloud"):
    os.environ["LLM_PROVIDER"] = "nim"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from youtube_transcript_api import YouTubeTranscriptApi

from services.guru_brain.tone_extractor import ToneExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_playlists")

PLAYLIST_URLS = [
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCTKE3_cQvMGNUwB4LeXXjI",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBGXFR_4jCmVntbgBa3sx1y",
]

# Additional curated direct Q&A videos from Sri Preethaji & Sri Krishnaji if playlist parsing is limited
KNOWN_DIRECT_QA_VIDEOS = [
    "UlOt31lBhLY",
    "BMJrDu-folk",
    "gWp83h7VwY0",
    "r4HnJ_1bW4E",
    "T8c8q9Z7mKg",
    "k9r8b1mX2w0",
    "p8w2j9L3k1Y",
]


def extract_playlist_video_ids(playlist_url: str) -> list[str]:
    """Extract all video IDs from a YouTube playlist URL."""
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    req = urllib.request.Request(playlist_url, headers=headers)
    try:
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")  # nosec B310 -- hardcoded youtube.com playlist URLs from PLAYLIST_URLS
        video_ids = list(dict.fromkeys(re.findall(r"\"videoId\":\"([a-zA-Z0-9_-]{11})\"", html)))
        logger.info(f"Extracted {len(video_ids)} video IDs from playlist {playlist_url}")
        return video_ids
    except Exception as exc:
        logger.warning(f"Failed to parse playlist {playlist_url}: {exc}")
        return []


async def main():
    logger.info(
        "Starting legacy playlist candidate preview (NO QDRANT OR MEMGRAPH WRITES)..."
    )
    extractor = ToneExtractor()

    # Step 1: Discover all video IDs across playlists
    all_video_ids = list(KNOWN_DIRECT_QA_VIDEOS)
    for pl in PLAYLIST_URLS:
        vids = extract_playlist_video_ids(pl)
        all_video_ids.extend(vids)

    # Deduplicate video IDs
    all_video_ids = list(dict.fromkeys(all_video_ids))
    logger.info(f"Total target videos for transcript ingestion: {len(all_video_ids)}")

    total_extracted_exemplars = []

    # Step 2: Fetch transcripts & extract persona exemplars for each video
    api = YouTubeTranscriptApi()
    for vid in all_video_ids:
        try:
            logger.info(f"Fetching transcript for video ID: {vid}...")
            fetched = api.fetch(vid)
            text = " ".join([getattr(s, "text", str(s)) for s in fetched])

            if not text or len(text) < 100:
                await asyncio.sleep(0.5)
                continue

            # Mentioning a teacher's name in transcript text is not speaker
            # attribution. Preserve uncertainty; this produces review candidates only.
            exemplars = await extractor.extract_exemplars_from_transcript(
                transcript_text=text,
                source_id=vid,
                default_guru="unknown",
            )
            logger.info(
                f"Extracted {len(exemplars)} direct interaction exemplars from video {vid}."
            )
            total_extracted_exemplars.extend(exemplars)

            # No knowledge-store mutation: this legacy extractor has no signed
            # source-rights evidence or independent speaker-attribution packet.
            await asyncio.sleep(0.5)
        except Exception as exc:
            logger.warning(f"Could not fetch/process transcript for video {vid}: {exc}")
            await asyncio.sleep(0.5)

    # Candidate extraction is not an approved ingestion decision.
    indexed_count = 0

    report_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "backend", "data", "guru_transcripts"
    )
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "playlist_ingestion_report.json")

    report = {
        "status": "dry_run_candidates_only",
        "promotion_eligible": False,
        "reason": "missing_source_rights_and_independent_speaker_certification",
        "total_video_ids": len(all_video_ids),
        "total_candidate_exemplars": len(total_extracted_exemplars),
        "qdrant_indexed_count": indexed_count,
        "neo4j_kg_nodes_populated": 0,
        "knowledge_store_writes": 0,
        "sample_candidates": [e.to_dict() for e in total_extracted_exemplars[:3]],
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(
        "\nCandidate preview complete: candidates=%d, Qdrant writes=0, Memgraph writes=0, report=%s",
        len(total_extracted_exemplars),
        report_path,
    )


if __name__ == "__main__":
    asyncio.run(main())
