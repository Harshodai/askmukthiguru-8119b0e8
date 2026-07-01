"""Back-fill the important_kwd Qdrant payload for pre-Gap-2 chunks.

Usage:
    python -m scripts.ops.backfill_important_kwd            # dry-run (default)
    python -m scripts.ops.backfill_important_kwd --apply     # mutate Qdrant
    python -m scripts.ops.backfill_important_kwd --limit 50  # cap scan
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]  # backend/scripts/ → backend/
sys.path.insert(0, str(ROOT))

from ingest.pipeline import extract_doctrine_tags  # noqa: E402
from app.config import settings as app_settings  # noqa: E402
from app.dependencies import get_container  # noqa: E402


def _point_text(payload: dict[str, Any]) -> str:
    """Extract the chunk's text from whatever field the indexer stored it in."""
    return payload.get("content") or payload.get("text") or ""


def _needs_tags(payload: dict[str, Any]) -> bool:
    kwd = payload.get("important_kwd")
    if kwd is None:
        return True
    if isinstance(kwd, list) and not kwd:
        return True
    return False


async def run(  # noqa: C901 — CLI glue, acceptable
    *,
    apply: bool = False,
    collection: str | None = None,
    limit: int = 0,
    page_size: int = 256,
) -> tuple[int, int, int]:
    """Scroll Qdrant, identify chunks missing important_kwd, optionally fill.

    Returns (scanned, needs_fill, filled).
    """
    container = get_container()
    qdrant_svc = container._qdrant

    # Raw QdrantClient — bypass high-level service wrappers for scroll/set_payload
    raw: Any = qdrant_svc._client

    coll = collection or getattr(app_settings, "qdrant_collection", "spiritual_chunks")

    scanned = 0
    needs_fill = 0
    filled = 0
    offset: str | None = None

    while True:
        results, next_offset = raw.scroll(
            collection_name=coll,
            scroll_filter=None,
            limit=page_size,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        if not results:
            break

        for point in results:
            payload: dict[str, Any] = point.payload or {}

            if not _needs_tags(payload):
                scanned += 1
                continue

            needs_fill += 1
            text = _point_text(payload)
            tags = extract_doctrine_tags(text)

            pid = str(point.id)

            if apply:
                raw.set_payload(
                    collection_name=coll,
                    payload={"important_kwd": tags},
                    points=[point.id],
                )
                filled += 1
                print(f"[filled]  id={pid}  tags={tags}")
            else:
                print(f"[dry-run]  id={pid}  would_tag={tags}")

            scanned += 1

        if next_offset is None or len(results) == 0:
            break
        offset = str(next_offset)

        if limit and scanned >= limit:
            break

    return scanned, needs_fill, filled


def main() -> None:
    parser = argparse.ArgumentParser(description="Back-fill important_kwd payload (Gap 2)")
    parser.add_argument("--apply", action="store_true", help="Write to Qdrant (default: dry-run)")
    parser.add_argument("--collection", default=None)
    parser.add_argument("--limit", type=int, default=0, help="Max points to scan (0 = all)")
    parser.add_argument("--page-size", type=int, default=256)
    args = parser.parse_args()

    scanned, needs_fill, filled = asyncio.run(
        run(
            apply=args.apply,
            collection=args.collection,
            limit=args.limit,
            page_size=args.page_size,
        )
    )
    mode = "APPLY" if args.apply else "dry-run"
    print(
        f"Done ({mode}): collection={args.collection or app_settings.qdrant_collection}  "
        f"scanned={scanned}  needs_fill={needs_fill}  filled={filled}"
    )


if __name__ == "__main__":
    main()
