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
import sys
import time
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import neo4j as _neo4j_lib

# Bootstrap backend import path
BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from ingest.handlers.checkpoint import IngestionCheckpoint
from ingest.pipeline import IngestionPipeline, _okf_extract_for_video
from app.config import settings
from services.embedding_service import EmbeddingService
from services.openrouter_service import OpenRouterService
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
    """Resolves inputs from text files, video directories, or direct URLs.

    De-duplicates the resulting list (order-preserving) — production-audit
    finding IC-4: an input list with the same URL entered twice was dispatched
    as two concurrent workers for the same source with no de-dup, on top of
    the outer checkpoint here already being a disjoint, non-atomic keyspace
    from the pipeline's own idempotency gate (a separate, deeper issue this
    script alone can't close — see IngestionCheckpoint.acquire_lock in
    ingest/handlers/checkpoint.py for the pipeline-side mitigation).
    """
    if single_url:
        return [single_url.strip()]
    if not input_path:
        return []

    p = Path(input_path)
    if p.is_file():
        if p.suffix in {".txt", ".json", ".csv"}:
            lines = p.read_text(encoding="utf-8").splitlines()
            raw = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
        else:
            raw = [str(p)]
    else:
        video_exts = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"}
        raw = [str(f) for f in p.rglob("*") if f.suffix.lower() in video_exts]

    seen: set[str] = set()
    deduped = []
    for item in raw:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


async def bulk_ingest_async(
    sources: list[str],
    *,
    workers: int = 2,
    batch_size: int = 25,
    dry_run: bool = False,
    max_accuracy: bool = True,
    enable_okf: bool = True,
) -> dict[str, Any]:
    """Master asynchronous bulk ingestion orchestrator."""
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
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

    # Ensure local Supabase host fallback
    if not os.environ.get("SUPABASE_URL"):
        os.environ["SUPABASE_URL"] = "http://localhost:54321"

    # Quantized ML backends: ONNX INT8 for BGE-M3 (4x lower RAM, 2x faster CPU encode)
    os.environ.setdefault("EMBEDDING_BACKEND", "onnx_int8")
    os.environ.setdefault("RERANKER_BACKEND", "onnx_int8")

    # Ingestion throughput optimization: elevate RPM limit for bulk operations
    rpm_limit = int(os.environ.get("OPENROUTER_RPM_LIMIT", "120"))

    # Instantiate services
    qdrant_svc = QdrantService()
    embedder_svc = EmbeddingService()
    llm_provider = (
        getattr(settings, "llm_provider", None) or os.environ.get("LLM_PROVIDER", "openrouter")
    ).lower()
    if llm_provider in ("sarvam", "sarvam_cloud"):
        from services.sarvam_service import SarvamCloudService

        llm_svc = SarvamCloudService()
        logger.info("Using SarvamCloudService as LLM provider for ingestion")
    elif llm_provider == "ollama":
        from services.ollama_service import OllamaService

        llm_svc = OllamaService()
        logger.info("Using OllamaService as LLM provider for ingestion")
    else:
        llm_svc = OpenRouterService()
        llm_svc._rpm_limit = rpm_limit
        logger.info("Using OpenRouterService as LLM provider for ingestion")

    # --- Neo4j driver (for ontology/entity writes via write_extraction_to_neo4j) ---
    _neo4j_driver = None
    try:
        neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        neo4j_pass = os.environ.get("NEO4J_PASSWORD", "mukthiguru_neo4j_pass")
        _neo4j_driver = _neo4j_lib.GraphDatabase.driver(
            neo4j_uri, auth=("neo4j", neo4j_pass)
        )
        logger.info("Neo4j driver connected for ontology writes")
    except Exception as _e:
        logger.warning("Neo4j unavailable — graph writes disabled: %s", _e)

    # --- LightRAG service (dual-level graph+vector index) ---
    _lightrag_svc = None
    try:
        from services.lightrag_service import LightRAGService
        _lightrag_svc = LightRAGService()
        logger.info("LightRAG service ready for ingestion")
    except Exception as _e:
        logger.warning("LightRAG unavailable — KG layer skipped: %s", _e)

    pipeline = IngestionPipeline(
        qdrant_service=qdrant_svc,
        embedding_service=embedder_svc,
        ollama_service=llm_svc,
        neo4j_driver=_neo4j_driver,
        lightrag_service=_lightrag_svc,
    )

    # Lower RAPTOR cluster_size: default 8 skips short discourses (3-5 chunks)
    if hasattr(pipeline, '_raptor') and pipeline._raptor is not None:
        pipeline._raptor._cluster_size = 3
        logger.info("RAPTOR cluster_size -> 3 (enables short-video tree build)")

    # 2026-09-05: a small local Ollama model (e.g. qwen2.5:1.5b) is fine for
    # transcript correction but unreliable as a quality JUDGE — live-observed
    # rejecting genuine doctrine as "gibberish" at a 0% pass rate. Swap ONLY
    # the audit LLM to Sarvam Cloud when AUDIT_LLM_PROVIDER=sarvam_cloud is
    # set, leaving correction (the bulk of the token volume) on the free
    # local model. DataQualityGate/self._auditor is a plain post-construction
    # attribute (ingest/pipeline.py), same pattern as the RAPTOR override above.
    if os.environ.get("AUDIT_LLM_PROVIDER", "").strip().lower() in ("sarvam_cloud", "sarvam"):
        try:
            from services.sarvam_service import SarvamCloudService
            from ingest.quality_gate import DataQualityGate

            sarvam_svc = SarvamCloudService()
            pipeline._auditor = DataQualityGate(
                llm_service=sarvam_svc,
                quality_threshold=getattr(pipeline._auditor, "_threshold", 65),
                enabled=True,
            )
            logger.info("Quality-gate audit LLM -> Sarvam Cloud (correction stays on local Ollama)")
        except Exception as _e:
            logger.warning(f"Could not switch audit LLM to Sarvam Cloud, keeping local: {_e}")

    semaphore = asyncio.Semaphore(workers)
    stats = {"succeeded": 0, "skipped": 0, "failed": 0, "okf_queued": 0}

    # Discover unprocessed sources for this batch
    batch_tasks_args = []
    for idx, src in enumerate(sources, 1):
        if checkpoint.is_processed(src):
            stats["skipped"] += 1
            logger.info(
                "  [%d/%d] ⏭ Skipping already processed source: %s", idx, len(sources), src
            )
            continue
        # production-audit finding IC-4: this outer checkpoint's keyspace (raw
        # source URL) is disjoint from the pipeline's own internal idempotency
        # checkpoint (content-hash keyed), so this reservation only protects
        # against a SECOND bulk_ingest_video.py invocation racing this one on
        # the same source URL — not a full fix for the deeper keyspace split
        # (which would need threading a shared checkpoint instance through the
        # pipeline, a larger refactor). TTL-bound, not explicitly released —
        # see the ingest_raw_text comment in ingest/pipeline.py for why.
        if not checkpoint.acquire_lock(src):
            stats["skipped"] += 1
            logger.info(
                "  [%d/%d] ⏭ Skipping source already claimed by another run: %s", idx, len(sources), src
            )
            continue
        batch_tasks_args.append((src, idx))
        if len(batch_tasks_args) >= batch_size:
            break

    if not batch_tasks_args:
        logger.info("🎉 All %d sources are already processed and checkpointed!", len(sources))
        return {"status": "complete", "stats": stats, "results": []}

    logger.info("📦 Scheduled batch of %d unprocessed sources (out of %d total)", len(batch_tasks_args), len(sources))

    async def ingest_one(src: str, idx: int) -> dict[str, Any]:
        async with semaphore:
            start_t = time.time()
            logger.info("  [%d/%d] ▶ Ingesting source: %s", idx, len(sources), src)

            try:
                if src.startswith("http://") or src.startswith("https://"):
                    res = await pipeline.ingest_url(
                        src,
                        max_accuracy=max_accuracy,
                        on_progress=lambda msg, pct: logger.debug(
                            "   [%s] (%3.0f%%) %s", src, pct * 100, msg
                        ),
                    )
                else:
                    res = await pipeline.ingest_file(
                        src,
                        max_accuracy=max_accuracy,
                        on_progress=lambda msg, pct: logger.debug(
                            "   [%s] (%3.0f%%) %s", src, pct * 100, msg
                        ),
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
                        idx,
                        len(sources),
                        elapsed,
                        chunks,
                        summaries,
                        src,
                    )

                    # Trigger OKF 5-Node Transformation Arc extraction
                    if enable_okf:
                        video_id = None
                        src_host = (urlparse(src).hostname or "").lower() if src else ""
                        if src_host in ("youtube.com", "youtu.be", "www.youtube.com") or src_host.endswith(".youtube.com"):
                            from ingest.youtube_loader import extract_video_id

                            video_id = extract_video_id(src)

                        if video_id:
                            try:
                                okf_task = asyncio.create_task(_okf_extract_for_video(video_id))
                                okf_tasks.append(okf_task)
                                stats["okf_queued"] += 1
                                logger.info(
                                    "         └─ OKF 5-Node Arc extraction queued for video: %s",
                                    video_id,
                                )
                            except Exception as okf_err:
                                logger.warning("         └─ OKF dispatch note: %s", okf_err)

                    return {"source": src, "status": "success", "chunks": chunks, "summaries": summaries}
                else:
                    stats["failed"] += 1
                    msg = res.get("message", "Unknown error")
                    logger.error(
                        "  [%d/%d] ❌ Rejected/Failed (%0.1fs): %s — %s",
                        idx,
                        len(sources),
                        elapsed,
                        msg,
                        src,
                    )
                    await asyncio.to_thread(
                        checkpoint.save, src, {"status": "failed", "error": str(msg)}
                    )
                    return {"source": src, "status": "failed", "error": msg}

            except Exception as e:
                stats["failed"] += 1
                elapsed = time.time() - start_t
                logger.error(
                    "  [%d/%d] ❌ Error (%0.1fs): %s — %s", idx, len(sources), elapsed, e, src
                )
                await asyncio.to_thread(
                    checkpoint.save, src, {"status": "error", "error": str(e)}
                )
                return {"source": src, "status": "error", "error": str(e)}
            finally:
                import gc
                gc.collect()

    tasks = [ingest_one(src, idx) for src, idx in batch_tasks_args]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    if okf_tasks:
        okf_results = await asyncio.gather(*okf_tasks, return_exceptions=True)
        okf_ok = sum(1 for r in okf_results if not isinstance(r, Exception))
        logger.info("   OKF Completed: %d / %d", okf_ok, len(okf_tasks))

    logger.info("=================================================================")
    logger.info("🏁 BATCH COMPLETED — RECYCLING MEMORY")
    logger.info("   Succeeded in Batch : %d", stats["succeeded"])
    logger.info("   Skipped in Scan    : %d", stats["skipped"])
    logger.info("   Failed/Filtered    : %d", stats["failed"])
    logger.info("   OKF Queued         : %d", stats["okf_queued"])
    logger.info("=================================================================")

    return {
        "status": "complete",
        "stats": stats,
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SOTA Bulk Asynchronous Video & Document Ingestion"
    )
    parser.add_argument("--input", help="Directory or text file containing URLs/files")
    parser.add_argument("--url", help="Single video or article URL to ingest")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent workers")
    parser.add_argument("--batch-size", type=int, default=25, help="Batch size before memory recycling")
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
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            enable_okf=not args.disable_okf,
        )
    )
