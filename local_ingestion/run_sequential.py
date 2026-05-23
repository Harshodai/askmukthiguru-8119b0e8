#!/usr/bin/env python3
"""
Master Sequential Ingestion Runner
==================================
Runs the heavy AI pipelines sequentially to avoid maxing out local hardware.
1. Runs `scripts/ingest_host_whisper.py` (Whisper STT - YouTube)
2. Runs `local_ingestion/ingest_book_optimized.py` (DeepSeek-R1 - PDFs)
"""

import logging
import os
import subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sequential_runner")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run_script(script_path, description):
    logger.info(f"\n{'='*70}\n🚀 STARTING {description}\n{'='*70}")

    # Run using the host python environment
    venv_python = os.path.join(BASE_DIR, ".venv_host", "bin", "python3")

    try:
        process = subprocess.Popen(
            [venv_python, script_path],
            cwd=BASE_DIR,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
        )
        process.wait()
        if process.returncode != 0:
            logger.error(f"❌ {description} failed with exit code {process.returncode}")
        else:
            logger.info(f"✅ {description} completed successfully!")

    except Exception as e:
        logger.error(f"❌ Failed to run {description}: {e}")


def main():
    logger.info("Starting Sequential Knowledge Base Ingestion...")

    youtube_script = os.path.join(BASE_DIR, "scripts", "ingest_host_whisper.py")
    book_script = os.path.join(BASE_DIR, "local_ingestion", "ingest_book_optimized.py")

    # 1. YouTube Playlists (Whisper)
    run_script(youtube_script, "PHASE 1: YouTube Playlist Ingestion (Whisper STT)")

    # 2. Book Processing (DeepSeek Proposition + GraphRAG)
    run_script(
        book_script,
        "PHASE 2: Book Ingestion (DeepSeek Proposition Splitting + Neo4j Graph Extraction)",
    )

    logger.info("\n🎉 All sequential ingestion processes complete!")


if __name__ == "__main__":
    import sys

    main()
