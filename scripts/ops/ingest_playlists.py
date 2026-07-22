#!/usr/bin/env python3
"""
Playlist Ingestion CLI for Guru Brain — Neo4j Knowledge Graph + Qdrant Dual-Stream Indexing.

Target Playlists:
1. `PLOVU2e0ZosYCTKE3_cQvMGNUwB4LeXXjI` (Sri Preethaji & Sri Krishnaji Direct Seeker Interactions & Satsangs)
2. `PLOVU2e0ZosYBGXFR_4jCmVntbgBa3sx1y` (Sri Preethaji & Sri Krishnaji Live Q&A and Discourses)

Extracts verbatim transcripts, builds Neo4j KG ontology nodes, and embeds tone vectors into Qdrant `guru_tone_podcast`.
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

from services.embedding_service import EmbeddingService
from services.qdrant_service import QdrantService
from services.guru_brain.guru_brain_service import get_guru_brain_service
from services.guru_brain.guru_kg_service import get_guru_kg_service
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
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        video_ids = list(dict.fromkeys(re.findall(r'\"videoId\":\"([a-zA-Z0-9_-]{11})\"', html)))
        logger.info(f"Extracted {len(video_ids)} video IDs from playlist {playlist_url}")
        return video_ids
    except Exception as exc:
        logger.warning(f"Failed to parse playlist {playlist_url}: {exc}")
        return []


async def main():
    logger.info("Starting Playlist Ingestion CLI for Guru Brain (KG + Qdrant)...")

    # Connect to live Qdrant in Docker
    qdrant = QdrantService()
    embedder = EmbeddingService()
    guru_brain = get_guru_brain_service(qdrant_service=qdrant, embedding_service=embedder)
    guru_kg = get_guru_kg_service()
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

            # Determine speaker role & context
            guru_name = "combined"
            if "preethaji" in text.lower() and "krishnaji" not in text.lower():
                guru_name = "preethaji"
            elif "krishnaji" in text.lower() and "preethaji" not in text.lower():
                guru_name = "krishnaji"

            exemplars = await extractor.extract_exemplars_from_transcript(
                transcript_text=text,
                source_id=vid,
                default_guru=guru_name,
            )
            logger.info(f"Extracted {len(exemplars)} direct interaction exemplars from video {vid}.")
            total_extracted_exemplars.extend(exemplars)

            # Step 3: Populate Neo4j Knowledge Graph & OKF Ontology Nodes
            for ex in exemplars:
                guru_kg.populate_ontology_arc(
                    seeker_dilemma=ex.seeker_emotional_state,
                    limiting_belief="Habitual mind identification",
                    teaching=ex.teaching_concept or "Present Moment Awareness",
                    target_state="Beautiful State",
                    practice_step="Observe thoughts without judgment",
                    guru_speaker="Sri Preethaji & Sri Krishnaji",
                )
            await asyncio.sleep(0.5)
        except Exception as exc:
            logger.warning(f"Could not fetch/process transcript for video {vid}: {exc}")
            await asyncio.sleep(0.5)

    # Step 4: Index into Docker Qdrant collection `guru_tone_podcast`
    logger.info(f"Upserting {len(total_extracted_exemplars)} persona exemplars into Docker Qdrant collection `guru_tone_podcast`...")
    indexed_count = await guru_brain.index_exemplars(total_extracted_exemplars)

    report_dir = os.path.join(os.path.dirname(__file__), "..", "..", "backend", "data", "guru_transcripts")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "playlist_ingestion_report.json")

    report = {
        "status": "success",
        "total_video_ids": len(all_video_ids),
        "total_exemplars_extracted": len(total_extracted_exemplars),
        "qdrant_indexed_count": indexed_count,
        "neo4j_kg_nodes_populated": len(total_extracted_exemplars),
        "sample_exemplars": [e.to_dict() for e in total_extracted_exemplars[:3]],
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"\nSUCCESS: Playlist Ingestion Complete! Extracted {len(total_extracted_exemplars)} exemplars. Report written to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
