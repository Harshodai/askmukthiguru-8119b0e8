#!/usr/bin/env python3
"""
Contextual Retrieval Reprocessor
=================================
Enriches existing Qdrant chunks with Anthropic-style contextual headers
WITHOUT re-ingesting source documents.

Algorithm
---------
1. Scroll all points from the `spiritual_wisdom` collection (raptor_level=0 only).
2. Group points by source_url.
3. For each source, reconstruct the "full document" by concatenating sorted chunks.
4. Call ContextualChunkingService to generate situating context for each chunk.
5. Upsert the updated payload back to Qdrant (text field only — no re-embedding).

Usage
-----
    cd /path/to/backend
    python scripts/ops/reprocess_contextual.py [--dry-run] [--source-url <url>] [--limit <n>]

Flags
-----
--dry-run       Print what would be done without writing to Qdrant.
--source-url    Restrict processing to a single source URL.
--limit         Maximum number of source groups to process (default: all).
--batch-size    Qdrant scroll batch size (default: 100).
--concurrency   LLM parallel calls (default: 2 — conservative for Ollama).

Resumption
----------
Progress is checkpointed to `scripts/ops/contextual_reprocess_state.json`.
Re-run the script after interruption — already-processed sources are skipped.

Safety
------
- Original text is preserved in a `text_original` payload field before overwrite.
- The script never deletes or re-embeds vectors; only `text` payload is updated.
- Dry-run mode performs no writes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# ── Bootstrap sys.path so backend modules resolve ──────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
sys.path.insert(0, str(BACKEND_DIR))

from qdrant_client import QdrantClient
from qdrant_client.models import PointIdsList

from app.config import settings
from services.contextual_chunking_service import ContextualChunkingService
from services.ollama_service import OllamaService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("reprocess_contextual")

STATE_FILE = Path(__file__).parent / "contextual_reprocess_state.json"


# ── State helpers ──────────────────────────────────────────────────────────────


def _load_state() -> set[str]:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def _save_state(done: set[str]) -> None:
    STATE_FILE.write_text(json.dumps(sorted(done)))


# ── Core ───────────────────────────────────────────────────────────────────────


async def reprocess(
    *,
    dry_run: bool = False,
    source_url_filter: Optional[str] = None,
    limit: Optional[int] = None,
    batch_size: int = 100,
    concurrency: int = 2,
) -> None:
    qdrant_url = os.environ.get("QDRANT_URL", settings.qdrant_url)
    collection = os.environ.get("QDRANT_COLLECTION", settings.qdrant_collection)

    logger.info("Connecting to Qdrant at %s (collection: %s)", qdrant_url, collection)
    client = QdrantClient(url=qdrant_url, timeout=30)

    # Initialise LLM + contextual service
    llm = OllamaService()
    svc = ContextualChunkingService(llm, concurrency=concurrency)

    done = _load_state()
    logger.info("Resumption: %d source(s) already processed", len(done))

    # ── Step 1: Scroll all leaf chunks ────────────────────────────────────────
    logger.info("Scrolling collection for raptor_level=0 chunks…")
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    scroll_filter = Filter(must=[FieldCondition(key="raptor_level", match=MatchValue(value=0))])

    points_by_source: dict[str, list[dict]] = {}
    offset = None

    while True:
        result, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=scroll_filter,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for pt in result:
            src = pt.payload.get("source_url", "")
            if source_url_filter and src != source_url_filter:
                continue
            points_by_source.setdefault(src, []).append({"id": pt.id, "payload": pt.payload})
        if next_offset is None:
            break
        offset = next_offset

    sources = sorted(points_by_source.keys())
    logger.info("Found %d unique source(s) with leaf chunks", len(sources))

    if limit:
        sources = sources[:limit]
        logger.info("Limiting to first %d source(s)", limit)

    # ── Step 2: Process each source ───────────────────────────────────────────
    processed = 0
    for src in sources:
        if src in done:
            logger.info("  SKIP (already done): %s", src)
            continue

        pts = points_by_source[src]
        # Sort chunks by index to reconstruct document order
        pts.sort(key=lambda p: p["payload"].get("chunk_index", 0))

        chunks = [p["payload"].get("text", "") for p in pts]
        full_doc = "\n\n".join(chunks)

        title = pts[0]["payload"].get("title", src)
        logger.info(
            "  [%d/%d] %s — %d chunks",
            sources.index(src) + 1,
            len(sources),
            title[:60],
            len(chunks),
        )

        # Generate contextual enrichments
        try:
            enriched = await svc.enrich_chunks(full_doc, chunks, source_label=title)
        except Exception as exc:
            logger.error("    ✗ Enrichment failed: %s — skipping source", exc)
            continue

        if dry_run:
            for orig, enr in zip(chunks[:3], enriched[:3]):
                logger.info(
                    "    DRY-RUN sample:\n      ORIG: %s\n      ENRI: %s", orig[:80], enr[:120]
                )
            logger.info("    (dry-run — no writes)")
            done.add(src)
            continue

        # Upsert updated payloads (preserve text_original for rollback)
        updates = []
        for pt, enr_text in zip(pts, enriched):
            payload = dict(pt["payload"])
            if "text_original" not in payload:
                payload["text_original"] = payload["text"]  # snapshot before first enrichment
            payload["text"] = enr_text
            updates.append((pt["id"], payload))

        # Batch upsert payload-only updates (no vector change)
        UPSERT_BATCH = 50
        for i in range(0, len(updates), UPSERT_BATCH):
            batch = updates[i : i + UPSERT_BATCH]
            client.overwrite_payload(
                collection_name=collection,
                payload={},  # placeholder — we set per-point below
                points=PointIdsList(points=[]),
            )
            # Qdrant supports set_payload per point
            for pt_id, payload in batch:
                client.set_payload(
                    collection_name=collection,
                    payload={
                        "text": payload["text"],
                        "text_original": payload.get("text_original", ""),
                    },
                    points=[pt_id],
                )

        done.add(src)
        _save_state(done)
        processed += 1
        logger.info("    ✓ %d chunks updated and checkpointed", len(updates))

    logger.info(
        "Reprocessing complete. %d new source(s) enriched. Total done: %d.",
        processed,
        len(done),
    )


# ── CLI ────────────────────────────────────────────────────────────────────────


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reprocess Qdrant chunks with contextual headers")
    p.add_argument("--dry-run", action="store_true", help="Print without writing")
    p.add_argument("--source-url", default=None, help="Restrict to one source URL")
    p.add_argument("--limit", type=int, default=None, help="Max sources to process")
    p.add_argument("--batch-size", type=int, default=100, help="Qdrant scroll batch")
    p.add_argument("--concurrency", type=int, default=2, help="LLM parallel calls")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    asyncio.run(
        reprocess(
            dry_run=args.dry_run,
            source_url_filter=args.source_url,
            limit=args.limit,
            batch_size=args.batch_size,
            concurrency=args.concurrency,
        )
    )
