"""Celery task: extract OKF entries from Qdrant, Neo4j, and LightRAG via LLM.

Routed to the `okf` queue. Calls scripts.extract_okf_from_stores.extract_okf.
Triggered by ingestion hook (fire-and-forget) or admin UI (future).

ponytail: thin wrapper — all logic lives in the extraction script. Celery just
schedules the async call in a worker thread.
"""

from __future__ import annotations

import asyncio
import logging

from celery_config import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.okf_extract_tasks.extract_okf_entries")
def extract_okf_entries(
    self,
    *,
    target_topic: str | None = None,
    target_video_id: str | None = None,
    limit: int = 20,
    auto_approve: bool = False,
    chunk_limit: int | None = None,
) -> dict:
    """Extract OKF entries from knowledge stores via LLM synthesis.

    Args:
        target_topic: Specific topic to extract (e.g. 'beautiful state')
        target_video_id: Extract from a single YouTube video
        limit: Max topic clusters to process
        auto_approve: Write directly to memory/okf/ and compile
        chunk_limit: Max Qdrant chunks to scan

    Returns:
        Dict with 'status', 'entries_written', 'paths', 'mode' (staging|approved).
    """
    try:
        import sys
        from pathlib import Path
        _base = Path(__file__).resolve().parent.parent
        if str(_base) not in sys.path:
            sys.path.insert(0, str(_base))

        from scripts.extract_okf_from_stores import extract_okf

        paths = asyncio.run(
            extract_okf(
                target_topic=target_topic,
                target_video_id=target_video_id,
                limit=limit,
                auto_approve=auto_approve,
                chunk_limit=chunk_limit,
            )
        )

        mode = "approved" if auto_approve else "staging"
        logger.info(
            "OKF extraction via Celery: %d entries → %s",
            len(paths), mode,
        )
        return {
            "status": "ok",
            "entries_written": len(paths),
            "paths": [str(p) for p in paths],
            "mode": mode,
        }
    except Exception as exc:
        logger.exception("OKF extraction failed")
        # ponytail: retry once with backoff — transient LLM/Qdrant failures
        # recover quickly; permanent failures (no data) don't retry
        if "No Qdrant chunks available" not in str(exc):
            self.retry(exc=exc, countdown=30, max_retries=1)
        return {"status": "error", "error": str(exc)}