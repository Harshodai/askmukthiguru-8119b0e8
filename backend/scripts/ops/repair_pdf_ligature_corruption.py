"""One-off (but re-runnable) data repair: fix pypdf ligature-drop corruption
(literal NUL bytes for dropped fi/fl/ff/ffi/ffl glyphs -- see
services/pdf_ligature_repair.py) already stored in Qdrant payload text.

Found 2026-09-18: 52 of 70 chunks ingested from The Four Sacred Secrets
(scripts/ingestion/ingest_four_sacred_secrets.py) carried this corruption in
`text` and/or `parent_text`. Scans the whole collection for ANY point with a
NUL in either field, not just that source -- the bug is generic to pypdf, so
any other book ingested the same way would carry the same corruption.

Payload-only update (set_payload), no re-embedding. The text delta per chunk
is a handful of restored letters inside already-recognizable words -- not
enough semantic drift to justify re-embedding 70+ chunks through bge-m3 for
what is effectively a typo fix. If a future audit finds retrieval quality
measurably regressed on this source, re-embed then; don't preemptively pay
for it here.

Usage (from backend/):
    .venv/bin/python -m scripts.ops.repair_pdf_ligature_corruption --dry-run
    .venv/bin/python -m scripts.ops.repair_pdf_ligature_corruption --apply
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qdrant_client import QdrantClient  # noqa: E402

from app.config import settings  # noqa: E402
from services.pdf_ligature_repair import repair_ligature_drops  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_TEXT_FIELDS = ("text", "parent_text")


def find_and_repair(client: QdrantClient, collection: str, apply: bool) -> int:
    fixed = 0
    scanned = 0
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=200,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        for point in points:
            scanned += 1
            payload = point.payload or {}
            updates = {}
            for field in _TEXT_FIELDS:
                value = payload.get(field)
                if isinstance(value, str) and "\x00" in value:
                    updates[field] = repair_ligature_drops(value)
            if updates:
                fixed += 1
                title = payload.get("title", "?")
                logger.info("  %s: repairing %s (id=%s)", title, list(updates.keys()), point.id)
                if apply:
                    client.set_payload(
                        collection_name=collection,
                        payload=updates,
                        points=[point.id],
                    )
        if offset is None:
            break
    logger.info("scanned=%d repaired=%d apply=%s", scanned, fixed, apply)
    return fixed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default=settings.qdrant_collection)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Explicit no-op alias of default")
    args = parser.parse_args()

    client = QdrantClient(url=settings.qdrant_url)
    find_and_repair(client, args.collection, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
