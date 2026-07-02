#!/usr/bin/env python3
"""
Backfill missing Qdrant payload metadata (title, speaker, language).

Uses LLM + langdetect via metadata_extractor — NO yt-dlp dependency.

Usage:
    source .venv/bin/activate
    # Pass 1: Fix language only (free, no LLM)
    python scripts/ingestion/backfill_metadata.py --language-only
    # Pass 2: Fix title+speaker (LLM, slower)
    python scripts/ingestion/backfill_metadata.py [--limit N]
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_metadata")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "spiritual_wisdom")

YT_ID_PATTERN = re.compile(r"(?:v=|youtu\.be/|/shorts/)([\w-]{11})")


def extract_video_id(source_url: str) -> str | None:
    m = YT_ID_PATTERN.search(source_url)
    return m.group(1) if m else None


def needs_backfill(point) -> dict | None:
    payload = point.payload or {}
    updates = {}
    title = (payload.get("title") or "").strip().lower()
    speaker = (payload.get("speaker") or "").strip().lower()
    lang = (payload.get("language") or "").strip()

    if not title or title in {"unknown", "unknown title", "none", ""}:
        updates["title"] = ""
    if not speaker or speaker in {"unknown", "unknown speaker", "none", ""}:
        updates["speaker"] = ""
    if not lang or lang.lower() in {"none", "unknown", ""}:
        updates["language"] = ""

    return updates if updates else None


def fetch_content_for_video(video_id: str, qdrant_client) -> str:
    """Fetch first chunk of content for a video to use for metadata extraction."""
    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    results, _ = qdrant_client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="source_url",
                    match=MatchValue(value=f"https://www.youtube.com/watch?v={video_id}"),
                )
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    if results:
        content = results[0].payload.get("text") or results[0].payload.get("content", "")
        return content[:5000] if content else ""
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill missing Qdrant metadata using LLM + langdetect"
    )
    parser.add_argument("--dry-run", action="store_true", help="Scan only, do not write")
    parser.add_argument("--limit", type=int, default=0, help="Max videos to backfill (0 = all)")
    parser.add_argument(
        "--min-chars", type=int, default=100,
        help="Min transcript chars to attempt LLM extraction (default 100)",
    )
    parser.add_argument(
        "--language-only", action="store_true",
        help="Only backfill language using langdetect (no LLM call, free)",
    )
    args = parser.parse_args()

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

    from qdrant_client import QdrantClient
    if not args.language_only:
        from services.metadata_extractor import extract_video_metadata

    client = QdrantClient(url=QDRANT_URL, timeout=30)

    count = client.count(COLLECTION, exact=True).count
    logger.info("Collection %s has %s points", COLLECTION, count)

    scroll_limit = 5000
    all_points = []
    next_offset = None
    while True:
        batch, next_offset = client.scroll(
            COLLECTION,
            limit=scroll_limit,
            offset=next_offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(batch)
        if next_offset is None or (args.limit and len(all_points) >= args.limit):
            break
    if args.limit:
        all_points = all_points[:args.limit]

    points = all_points

    if not points:
        logger.info("No points found")
        return 0

    video_points = {}
    for p in points:
        vid = extract_video_id(p.payload.get("source_url", ""))
        if vid:
            if vid not in video_points:
                video_points[vid] = []
            video_points[vid].append(p)

    logger.info("Found %d unique videos across %d points", len(video_points), len(points))

    backfilled = 0
    skipped = 0
    errors = 0

    for vid, vid_points in video_points.items():
        missing = {}
        for p in vid_points:
            n = needs_backfill(p)
            if n:
                missing.update(n)

        if not missing:
            skipped += 1
            continue

        if args.dry_run:
            logger.info(
                "[DRY-RUN] Would backfill %s: missing fields=%s (%d points)",
                vid, list(missing.keys()), len(vid_points),
            )
            skipped += 1
            continue

        content = fetch_content_for_video(vid, client)
        if not content or len(content) < args.min_chars:
            logger.info(
                "Skipping %s: insufficient content (%d chars, need %d)",
                vid, len(content), args.min_chars,
            )
            skipped += 1
            continue

        if args.language_only:
            from langdetect import DetectorFactory, detect as langdetect_detect
            DetectorFactory.seed = 0
            try:
                lang = langdetect_detect(content[:500])
            except Exception:
                lang = "en"
            meta = {"language": lang}
        else:
            try:
                meta = extract_video_metadata(content, vid)
            except Exception as e:
                logger.error("Failed to extract metadata for %s: %s", vid, e)
                errors += 1
                continue

        point_ids = [p.id for p in vid_points]
        update_payload = {}
        for field in ("title", "speaker", "language"):
            if field in missing and meta.get(field):
                update_payload[field] = meta[field]

        if not update_payload:
            logger.info("No new metadata for %s (extraction returned empty)", vid)
            skipped += 1
            continue

        try:
            client.set_payload(
                collection_name=COLLECTION,
                payload=update_payload,
                points=point_ids,
            )
            backfilled += 1
            logger.info(
                "Backfilled %s: %s -> %d points",
                vid, update_payload, len(point_ids),
            )
        except Exception as e:
            logger.error("Failed to update Qdrant for %s: %s", vid, e)
            errors += 1

    logger.info("=" * 50)
    logger.info("Done: %d backfilled, %d skipped, %d errors", backfilled, skipped, errors)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
