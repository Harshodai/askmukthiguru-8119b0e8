#!/usr/bin/env python3
"""
Ingestion CLI for Guru Brain — `guru_tone_podcast` collection.

Processes video transcripts of Sri Krishnaji and Sri Preethaji:
1. `UlOt31lBhLY`: Marie Forleo Interview (Marie Forleo = Interviewer, Sri Krishnaji & Sri Preethaji = Gurus)
2. `BMJrDu-folk`: Discourse by Sri Preethaji on Living in the Present Moment

Applies multi-speaker attribution, extracts persona exemplars, and indexes them into Qdrant `guru_tone_podcast`.
"""

import asyncio
import json
import logging
import os
import sys

# Load backend/.env before importing app.config
env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env")
if os.path.exists(env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        pass

# Fallback LLM provider if sarvam_api_key is missing
provider = os.getenv("LLM_PROVIDER", "sarvam_cloud")
if not os.getenv("SARVAM_API_KEY") and (not provider or provider == "sarvam_cloud"):
    os.environ["LLM_PROVIDER"] = "nim"

# Ensure backend path is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from services.guru_brain.guru_brain_service import get_guru_brain_service
from services.guru_brain.tone_extractor import PersonaToneExemplar, ToneExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_guru_tone_podcast")

TRANSCRIPT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "backend", "data", "guru_transcripts")


async def main():
    logger.info("Starting Guru Brain Podcast Ingestion CLI...")
    extractor = ToneExtractor()
    guru_brain = get_guru_brain_service()

    total_exemplars = []

    # File 1: BMJrDu-folk (Sri Preethaji)
    file1_path = os.path.join(TRANSCRIPT_DIR, "BMJrDu-folk.txt")
    if os.path.exists(file1_path):
        logger.info(f"Processing Sri Preethaji Discourse ({file1_path})...")
        with open(file1_path) as f:
            text1 = f.read()
        exemplars1 = await extractor.extract_exemplars_from_transcript(
            transcript_text=text1,
            source_id="BMJrDu-folk",
            default_guru="preethaji",
        )
        logger.info(f"Extracted {len(exemplars1)} persona exemplars for Sri Preethaji from BMJrDu-folk.")
        total_exemplars.extend(exemplars1)
    else:
        logger.warning(f"File not found: {file1_path}")

    # File 2: UlOt31lBhLY (Marie Forleo Interview with Sri Krishnaji and Sri Preethaji)
    file2_path = os.path.join(TRANSCRIPT_DIR, "UlOt31lBhLY.txt")
    if os.path.exists(file2_path):
        logger.info(f"Processing Marie Forleo Interview ({file2_path})...")
        with open(file2_path) as f:
            text2 = f.read()
        exemplars2 = await extractor.extract_exemplars_from_transcript(
            transcript_text=text2,
            source_id="UlOt31lBhLY",
            default_guru="combined",
        )
        logger.info(f"Extracted {len(exemplars2)} persona exemplars from Marie Forleo interview.")
        total_exemplars.extend(exemplars2)
    else:
        logger.warning(f"File not found: {file2_path}")

    # Index into GuruBrainService (Qdrant + Memory Fallback)
    logger.info(f"Indexing total {len(total_exemplars)} exemplars into `guru_tone_podcast` collection...")
    indexed_count = await guru_brain.index_exemplars(total_exemplars)

    # Save summary report
    report = {
        "status": "success",
        "total_extracted": len(total_exemplars),
        "indexed_count": indexed_count,
        "collection_name": "guru_tone_podcast",
        "sources": [
            {"id": "BMJrDu-folk", "guru": "preethaji", "title": "Living in the Present Moment"},
            {"id": "UlOt31lBhLY", "guru": "krishnaji & preethaji", "title": "Marie Forleo Interview - The Four Sacred Secrets"},
        ],
        "sample_exemplars": [e.to_dict() for e in total_exemplars[:3]],
    }

    report_path = os.path.join(TRANSCRIPT_DIR, "ingestion_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"SUCCESS: Guru Brain Podcast Ingestion Complete! Report saved to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
