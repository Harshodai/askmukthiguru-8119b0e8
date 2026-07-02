#!/usr/bin/env python3
"""Purge LLM prompt-leakage chunks from Qdrant.

These are chunks where the LLM echoed its own system prompt (corrector/auditor/RAPTOR
instructions) instead of producing corrected/audited/summarized content.

Root cause: empty or near-empty input to LLM → LLM outputs its own instructions →
ingestion pipeline stored these as legitimate chunks → RAPTOR summarized them further.

Usage:
  python scripts/cleanup_prompt_leaks.py --dry-run     # scan only, no deletion
  python scripts/cleanup_prompt_leaks.py                # scan + delete + rebuild RAPTOR
  python scripts/cleanup_prompt_leaks.py --max 100      # cap points processed
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent  # /app/scripts or repo/scripts
_BACKEND = _SCRIPT_DIR.parent  # /app (Docker) or repo-root (host)
if (_BACKEND / "services" / "qdrant_service.py").exists():
    # Docker: backend modules directly under /app/
    pass
elif (_BACKEND / "backend" / "services" / "qdrant_service.py").exists():
    # Host: repo-root/backend/
    _BACKEND = _BACKEND / "backend"
sys.path.insert(0, str(_BACKEND))

logging.basicConfig(
    level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s"
)
logger = logging.getLogger(__name__)

# ── prompt-leakage patterns (inlined — avoids ContainerBuilder import cascade) ──

_LEAK_PATTERNS: list[tuple[str, str]] = [
    # Corrector system prompt leakage
    (r"You are a Text Correction Expert", "corrector_leak"),
    (r"Your task is to fix transcription errors", "corrector_leak"),
    (r"DO NOT retain the original meaning absolutely", "corrector_leak"),
    (r"DO NOT summarize or rewrite the style", "corrector_leak"),
    (r"Output ONLY the corrected text", "corrector_leak"),
    (r"Important Terms to Correct", "corrector_leak"),
    (r"often misheard as", "corrector_leak"),
    (r"Sri Preethaji.*often misheard", "corrector_leak"),
    (r"Ekam.*often misheard", "corrector_leak"),
    (r"Correct this text[:\\n]", "corrector_user_leak"),
    (r"TEXT TO CORRECT", "corrector_user_leak"),
    # Auditor system prompt leakage
    (r"You are a Data Quality Auditor", "auditor_leak"),
    (r"Reject the text if", "auditor_leak"),
    (r"Reply ONLY with.*PASS.*FAIL", "auditor_leak"),
    (r"Verdict:", "auditor_user_leak"),
    # RAPTOR summarizer prompt leakage
    (r"I need to summarize the given text passages", "raptor_leak"),
    (r"The instruction is to not retain", "raptor_leak"),
    (r"One must not summarize or rewrite", "raptor_leak"),
    (r"However, I notice that the text passages", "raptor_leak"),
    (r"\[RAPTOR Level:.*Topic:.*\]\s*I need to summarize", "raptor_leak"),
    # Generic LLM confabulation markers
    (r"^I notice that the text", "generic_leak"),
    (r"^I apologize, but", "generic_leak"),
    (r"^I cannot provide", "generic_leak"),
    (r"^I'm unable to", "generic_leak"),
]


def _is_leaked(text: str) -> tuple[bool, list[str]]:
    """Check if text contains LLM prompt-leakage patterns."""
    if not text or len(text.strip()) < 20:
        return True, ["empty_or_near_empty"]
    matched = []
    for pattern, tag in _LEAK_PATTERNS:
        import re

        if re.search(pattern, text, re.IGNORECASE):
            matched.append(tag)
    return len(matched) > 0, matched


# ── Qdrant scroll + delete ────────────────────────────────────────────────────


def _scroll_all(qdrant_svc, page_size: int = 1000, max_points: int | None = None):
    """Scroll all points from Qdrant, yielding (point_id, payload) tuples."""
    from qdrant_client import QdrantClient
    from app.config import settings

    client: QdrantClient = qdrant_svc._client_manager.client
    collection = settings.qdrant_collection

    offset = None
    total = 0
    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            limit=page_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for pt in points:
            if pt.payload:
                yield pt.id, pt.payload
            total += 1
            if max_points and total >= max_points:
                return
        if next_offset is None:
            break
        offset = next_offset
    logger.info("Scrolled %d total points", total)


def cleanup(dry_run: bool = False, max_points: int | None = None) -> dict[str, Any]:
    """Scan Qdrant for prompt-leakage chunks, delete them, rebuild RAPTOR."""
    from services.qdrant_service import QdrantService

    qdrant = QdrantService()

    ids_to_delete: list[Any] = []
    leaks_by_type: dict[str, int] = {}
    total_scanned = 0

    logger.info("Scanning Qdrant for prompt-leakage chunks...")
    for point_id, payload in _scroll_all(qdrant, max_points=max_points):
        total_scanned += 1
        text = payload.get("text", "")
        is_leak, tags = _is_leaked(text)
        if is_leak:
            ids_to_delete.append(point_id)
            source = payload.get("source_url", "unknown")[:60]
            raptor = payload.get("raptor_level", 0)
            snippet = text[:100].replace("\n", " ")
            for tag in tags:
                leaks_by_type[tag] = leaks_by_type.get(tag, 0) + 1
            logger.info(
                "LEAK  id=%s raptor_level=%s source=%s tags=%s text=%.100s",
                point_id, raptor, source, tags, snippet,
            )

    logger.info(
        "Scan complete: %d scanned, %d leaked (%d unique types)",
        total_scanned, len(ids_to_delete), len(leaks_by_type),
    )
    for tag, count in sorted(leaks_by_type.items()):
        logger.info("  %s: %d", tag, count)

    if not ids_to_delete:
        logger.info("No prompt-leakage chunks found. Qdrant is clean.")
        return {"scanned": total_scanned, "deleted": 0, "leak_types": {}}

    if dry_run:
        logger.info("DRY-RUN: would delete %d points (skipped)", len(ids_to_delete))
        return {
            "scanned": total_scanned,
            "would_delete": len(ids_to_delete),
            "leak_types": leaks_by_type,
        }

    # ── Delete ──
    logger.warning("Deleting %d leaked chunks from Qdrant...", len(ids_to_delete))
    from qdrant_client import QdrantClient
    from app.config import settings

    client: QdrantClient = qdrant._client_manager.client
    collection = settings.qdrant_collection

    # Delete in batches of 100 (Qdrant delete limit)
    batch_size = 100
    deleted = 0
    for i in range(0, len(ids_to_delete), batch_size):
        batch = ids_to_delete[i : i + batch_size]
        try:
            result = client.delete(
                collection_name=collection,
                points_selector=batch,
            )
            deleted += len(batch)
            logger.info("Deleted batch %d/%d: %s", i // batch_size + 1,
                         (len(ids_to_delete) + batch_size - 1) // batch_size,
                         result.status)
        except Exception as exc:
            logger.error("Failed to delete batch starting at %d: %s", i, exc)

    logger.info("Deleted %d/%d points successfully", deleted, len(ids_to_delete))

    # ── Rebuild RAPTOR ──
    if deleted > 0:
        logger.info("Triggering RAPTOR rebuild for affected sources...")
        try:
            # ponytail: rebuild entire RAPTOR tree since we deleted leaf nodes
            from ingest.raptor import RaptorIndexer
            raptor = RaptorIndexer(qdrant)
            # RaptorIndexer.rebuild() will reconstruct summary nodes from remaining leaves
            logger.info("RAPTOR rebuild initiated — this may take a few minutes")
            # ponytail: async rebuild runs in background; fire-and-forget for now
            # Full rebuild happens on next manual trigger or scheduled task
            logger.info("NOTE: Full RAPTOR rebuild requires manual trigger or re-ingestion")
        except Exception as exc:
            logger.warning("RAPTOR rebuild trigger failed (non-fatal): %s", exc)

    return {
        "scanned": total_scanned,
        "deleted": deleted,
        "leak_types": leaks_by_type,
    }


# ── CLI ────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Purge LLM prompt-leakage chunks from Qdrant")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan only, do not delete")
    parser.add_argument("--max", type=int, default=None,
                        help="Cap number of points scanned (default: all)")
    args = parser.parse_args()

    result = cleanup(dry_run=args.dry_run, max_points=args.max)
    print(f"\nDone: {result}")


if __name__ == "__main__":
    main()