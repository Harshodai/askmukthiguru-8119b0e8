#!/usr/bin/env python3
"""Backfill missing language codes on spiritual_wisdom Qdrant points.

Run ONCE after deployment. Uses langdetect on the text payload to infer language
where the `language` field is missing or set to 'unknown'.

Usage:
  cd backend
  .venv/bin/python scripts/ops/backfill_language.py [--dry-run] [--batch 100]

Takes ~10-20 minutes for 89k points. Safe to re-run (idempotent: only touches
points where language is null/empty/unknown).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# Ensure project root on path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

BATCH_SIZE = 100
COLLECTION = "spiritual_wisdom"

# BCP-47 → internal language code mapping
_LANG_MAP = {
    "hi": "hi",     # Hindi
    "te": "te",     # Telugu
    "kn": "kn",     # Kannada
    "ta": "ta",     # Tamil
    "mr": "mr",     # Marathi
    "en": "en",     # English
    "gu": "gu",     # Gujarati (partial coverage)
    "ml": "ml",     # Malayalam (partial coverage)
    "bn": "bn",     # Bengali
    "ur": "ur",     # Urdu
}


def _detect_language(text: str) -> str:
    """Detect language using langdetect. Falls back to 'en' on error."""
    try:
        from langdetect import detect
        code = detect(text[:500])  # first 500 chars is sufficient
        return _LANG_MAP.get(code, "en")
    except Exception:
        return "en"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill language codes on spiritual_wisdom")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help="Scroll batch size")
    parser.add_argument("--limit", type=int, default=0, help="Max points to process (0 = all)")
    args = parser.parse_args()

    from qdrant_client import QdrantClient
    from qdrant_client.models import PointIdsList

    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key = os.environ.get("QDRANT_API_KEY", "")
    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key or None, timeout=30)

    print(f"Connected to Qdrant at {qdrant_url}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE WRITE'}")

    offset = None
    total_scanned = 0
    total_updated = 0
    start = time.time()

    while True:
        results, next_offset = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=None,
            limit=args.batch,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not results:
            break

        updates: list[tuple[int | str, str]] = []
        for point in results:
            lang = (point.payload or {}).get("language", "")
            if lang and lang not in ("", "unknown", None):
                continue  # already has valid language

            text = (
                (point.payload or {}).get("text", "")
                or (point.payload or {}).get("content", "")
                or ""
            )
            if not text.strip():
                continue

            detected = _detect_language(text)
            updates.append((point.id, detected))

        if updates and not args.dry_run:
            # Batch-update payload fields
            for point_id, lang_code in updates:
                try:
                    client.set_payload(
                        collection_name=COLLECTION,
                        payload={"language": lang_code},
                        points=PointIdsList(points=[point_id]),
                    )
                except Exception as e:
                    print(f"  WARN: failed to update {point_id}: {e}")

        total_scanned += len(results)
        total_updated += len(updates)

        if updates:
            sample = updates[:3]
            print(f"  Batch: scanned={len(results)}, updated={len(updates)} — sample: {sample}")
        else:
            print(f"  Batch: scanned={len(results)}, 0 needed update")

        if args.limit and total_scanned >= args.limit:
            print(f"Limit of {args.limit} reached.")
            break

        offset = next_offset
        if offset is None:
            break

    elapsed = time.time() - start
    print(f"\nDone. scanned={total_scanned}, updated={total_updated}, elapsed={elapsed:.1f}s")
    if args.dry_run:
        print("DRY RUN — no changes written.")


if __name__ == "__main__":
    main()
