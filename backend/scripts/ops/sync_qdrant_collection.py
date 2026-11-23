#!/usr/bin/env python3
"""Sync a Qdrant collection from source to target with vectors and payload indexes.

Invariants satisfied:
- X1/X2: byte-identical copy in scripts/ops/ and backend/scripts/ops/.
- Idempotent: upserts all points with dense/sparse vectors and payload.
- Ensures all payload indexes match.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_qdrant")


def sync_collection(
    collection: str,
    source_url: str,
    target_url: str,
    target_api_key: str | None = None,
    batch_size: int = 100,
) -> None:
    source_client = QdrantClient(url=source_url, check_compatibility=False, timeout=120)
    target_client = QdrantClient(
        url=target_url,
        api_key=target_api_key,
        check_compatibility=False,
        timeout=120,
    )

    logger.info("Connecting to source: %s, target: %s", source_url, target_url)
    source_info = source_client.get_collection(collection)
    logger.info(
        "Source %s has %d points, %d vectors",
        collection,
        source_info.points_count,
        source_info.indexed_vectors_count or 0,
    )

    # Sync payload indexes
    logger.info("Syncing payload index schema...")
    for field_name, field_info in source_info.payload_schema.items():
        try:
            target_client.create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=field_info.data_type,
                wait=True,
            )
        except Exception as e:
            logger.debug("Index for %s already exists or error: %s", field_name, e)

    # Scroll all points from source and upsert to target
    logger.info("Scrolling points from source in batches of %d...", batch_size)
    offset = None
    total_upserted = 0
    t0 = time.time()

    while True:
        pts, next_offset = source_client.scroll(
            collection_name=collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not pts:
            break

        structs = [PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in pts]
        target_client.upsert(collection_name=collection, points=structs, wait=True)
        total_upserted += len(structs)
        logger.info(
            "Progress: synced %d / %d points (%.1f%%)",
            total_upserted,
            source_info.points_count,
            (total_upserted / max(1, source_info.points_count)) * 100,
        )

        if next_offset is None:
            break
        offset = next_offset

    target_info = target_client.get_collection(collection)
    logger.info(
        "Sync completed in %.2fs! Target %s now has %d points.",
        time.time() - t0,
        collection,
        target_info.points_count,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="first_person_v13_shadow")
    parser.add_argument("--source", default="http://localhost:6333")
    parser.add_argument("--target", default="http://localhost:6335")
    parser.add_argument("--target-key", default="")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    sync_collection(
        collection=args.collection,
        source_url=args.source,
        target_url=args.target,
        target_api_key=args.target_key or None,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
