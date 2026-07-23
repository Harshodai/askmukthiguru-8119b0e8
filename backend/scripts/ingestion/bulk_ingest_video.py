"""
Mukthi Guru — SOTA Bulk Asynchronous Video & URL Ingestion Pipeline (bulk_ingest_async)

Integrates 7-Layer Production Ingestion Stack:
  1. SSRF Safety Validation & URL Resolution
  2. Transcript Council & Native Zero-Edit LLM Polisher
  3. Contextual Boundary Chunking (Sentence-Aligned + Anthropic Context Headers)
  4. BAAI/bge-m3 Dense & Sparse Hybrid Vector Indexing (Qdrant)
  5. RAPTOR Hierarchical Tree Clustering & Summarization
  6. LightRAG Entity & Relationship Knowledge Graph Extraction (Neo4j)
  7. OKF (Ontological Knowledge Framework) 5-Node Transformation Arc Extraction

Usage:
    python3 -m scripts.ingestion.bulk_ingest_video --input /path/to/urls_or_videos.txt --workers 2
    python3 -m scripts.ingestion.bulk_ingest_video --url https://www.youtube.com/watch?v=Rusm0REkN8c
    python3 -m scripts.ingestion.bulk_ingest_video --input /path/to/urls.txt --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Bootstrap backend import path
BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from ingest.handlers.checkpoint import IngestionCheckpoint
from ingest.pipeline import IngestionPipeline, _okf_extract_for_video
from services.embedding_service import EmbeddingService
from services.multi_provider_llm import MultiProviderLLMService
from services.ollama_service import OllamaService
from services.qdrant_service import QdrantService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bulk_ingest_async")

# Local-file path used only when neither Redis nor Supabase is configured —
# see IngestionCheckpoint's own tiered fallback.
STATE_FILE = Path(__file__).parent / "bulk_ingest_state.json"


def discover_inputs(input_path: Optional[str], single_url: Optional[str]) -> list[str]:
    """Resolves inputs from text files, video directories, or direct URLs."""
    if single_url:
        return [single_url.strip()]
    if not input_path:
        return []

    p = Path(input_path)
    if p.is_file():
        if p.suffix in {".txt", ".json", ".csv"}:
            lines = p.read_text(encoding="utf-8").splitlines()
            return [line.strip() for line in lines if line.strip() and not line.startswith("#")]
        return [str(p)]

    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"}
    return [str(f) for f in p.rglob("*") if f.suffix.lower() in video_exts]


async def bulk_ingest_async(
    sources: list[str],
    *,
    workers: int = 2,
    dry_run: bool = False,
    max_accuracy: bool = True,
    enable_okf: bool = True,
) -> dict[str, Any]:
    """Master asynchronous bulk ingestion orchestrator."""
    if not sources:
        logger.warning("No valid sources provided for ingestion.")
        return {"status": "empty", "processed": 0, "failed": 0}

    logger.info("=================================================================")
    logger.info("🚀 STARTING BULK ASYNCHRONOUS INGESTION PIPELINE (SOTA 2026)")
    logger.info("   Total Sources   : %d", len(sources))
    logger.info("   Workers         : %d", workers)
    logger.info("   Dry Run         : %s", dry_run)
    logger.info("   Max Accuracy    : %s (Contextual + RAPTOR + LightRAG)", max_accuracy)
    logger.info("   OKF Extraction  : %s (5-Node Transformation Arcs)", enable_okf)
    logger.info("=================================================================")

    if dry_run:
        for idx, src in enumerate(sources, 1):
            logger.info("  [dry-run %d/%d] Would ingest: %s", idx, len(sources), src)
        return {"status": "dry_run", "total": len(sources)}

    checkpoint = IngestionCheckpoint(filepath=str(STATE_FILE))
    okf_tasks: list[asyncio.Task] = []

    # Instantiate services
    qdrant_svc = QdrantService()
    embedder_svc = EmbeddingService()
    llm_svc = OllamaService()

    pipeline = IngestionPipeline(
        qdrant_service=qdrant_svc,
        embedding_service=embedder_svc,
        ollama_service=llm_svc,
    )

    semaphore = asyncio.Semaphore(workers)
    stats = {"succeeded": 0, "skipped": 0, "failed": 0, "okf_queued": 0}

    async def ingest_one(src: str, idx: int) -> dict[str, Any]:
        async with semaphore:
            if await asyncio.to_thread(checkpoint.is_processed, src):
                logger.info("  [%d/%d] ⏭ Skipping already processed source: %s", idx, len(sources), src)
                stats["skipped"] += 1
                return {"source": src, "status": "skipped"}

            start_t = time.time()
            logger.info("  [%d/%d] ▶ Ingesting source: %s", idx, len(sources), src)

            try:
                if src.startswith("http://") or src.startswith("https://"):
                    res = await pipeline.ingest_url(
                        src,
                        max_accuracy=max_accuracy,
                        on_progress=lambda msg, pct: logger.debug("   [%s] (%3.0f%%) %s", src, pct * 100, msg),
                    )
                else:
                    res = await pipeline.ingest_file(
                        src,
                        max_accuracy=max_accuracy,
                        on_progress=lambda msg, pct: logger.debug("   [%s] (%3.0f%%) %s", src, pct * 100, msg),
                    )

                status = res.get("status", "unknown")
                elapsed = time.time() - start_t

                if status == "success":
                    stats["succeeded"] += 1
                    await asyncio.to_thread(checkpoint.save, src)


                    chunks = res.get("chunks_indexed", 0)
                    summaries = res.get("summaries_created", 0)
                    logger.info(
                        "  [%d/%d] ✅ Success (%0.1fs) — Chunks: %d, RAPTOR Summaries: %d — %s",
                        idx, len(sources), elapsed, chunks, summaries, src
                    )

                    # Trigger OKF 5-Node Transformation Arc extraction
                    if enable_okf:
                        video_id = None
                        if "youtube.com" in src or "youtu.be" in src:
                            from ingest.youtube_loader import extract_video_id
                            video_id = extract_video_id(src)
                        
                        if video_id:
                            try:
                                okf_task = asyncio.create_task(_okf_extract_for_video(video_id))
                                okf_tasks.append(okf_task)
                                stats["okf_queued"] += 1
                                logger.info("         └─ OKF 5-Node Arc extraction queued for video: %s", video_id)
                            except Exception as okf_err:
                                logger.warning("         └─ OKF dispatch note: %s", okf_err)

                    return {"source": src, "status": "success", "result": res}
                else:
                    stats["failed"] += 1
                    msg = res.get("message", "Unknown error")
                    logger.error("  [%d/%d] ❌ Rejected/Failed (%0.1fs): %s — %s", idx, len(sources), elapsed, msg, src)
                    return {"source": src, "status": "failed", "error": msg}

            except Exception as e:
                stats["failed"] += 1
                elapsed = time.time() - start_t
                logger.error("  [%d/%d] ❌ Error (%0.1fs): %s — %s", idx, len(sources), elapsed, e, src)
                return {"source": src, "status": "error", "error": str(e)}

    tasks = [ingest_one(src, idx) for idx, src in enumerate(sources, 1)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    if okf_tasks:
        okf_results = await asyncio.gather(*okf_tasks, return_exceptions=True)
        okf_ok = sum(1 for r in okf_results if not isinstance(r, Exception))
        logger.info("   OKF Completed: %d / %d", okf_ok, len(okf_tasks))

    logger.info("=================================================================")
    logger.info("🎉 BULK INGESTION RUN COMPLETED!")
    logger.info("   Succeeded : %d", stats["succeeded"])
    logger.info("   Skipped   : %d", stats["skipped"])
    logger.info("   Failed    : %d", stats["failed"])
    logger.info("   OKF Queued: %d", stats["okf_queued"])
    logger.info("=================================================================")

    return {
        "status": "complete",
        "stats": stats,
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SOTA Bulk Asynchronous Video & Document Ingestion")
    parser.add_argument("--input", help="Directory or text file containing URLs/files")
    parser.add_argument("--url", help="Single video or article URL to ingest")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent workers")
    parser.add_argument("--dry-run", action="store_true", help="List sources without ingesting")
    parser.add_argument("--disable-okf", action="store_true", help="Disable OKF extraction")
    args = parser.parse_args()

    sources = discover_inputs(args.input, args.url)
    if not sources:
        print("Error: Please provide --input <file_or_dir> or --url <url>")
        sys.exit(1)

    asyncio.run(
        bulk_ingest_async(
            sources,
            workers=args.workers,
            dry_run=args.dry_run,
            enable_okf=not args.disable_okf,
        )
    )
