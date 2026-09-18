"""Periodic cleanup for stores that don't self-expire.

The semantic cache (services/cache/semantic_adapter.py) stores its vector in
Qdrant and its payload in Redis with a TTL. Qdrant has no TTL of its own, so
a point whose Redis key already expired sits in the collection forever unless
something deletes it. `get()` cleans up any stale point it happens to find,
but an entry nobody re-queries would never hit that path -- this sweep is
what actually bounds the collection's size.
"""

from __future__ import annotations

import logging
import time

from app.config import settings
from celery_config import celery_app

app = celery_app
logger = logging.getLogger(__name__)

_SWEEP_BATCH = 500


def _prune_once() -> dict[str, int]:
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, Range

    collection = f"mukthi_semantic_cache_{settings.embedding_dimension}d"
    ttl = getattr(settings, "semantic_cache_ttl", 604800)
    cutoff = time.time() - ttl

    client = QdrantClient(
        url=settings.qdrant_url, api_key=getattr(settings, "qdrant_api_key", "") or None
    )
    if not client.collection_exists(collection):
        return {"scanned": 0, "deleted": 0}

    stale_filter = Filter(must=[FieldCondition(key="cached_at", range=Range(lt=cutoff))])
    deleted = 0
    scanned = 0
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=stale_filter,
            limit=_SWEEP_BATCH,
            with_payload=False,
            with_vectors=False,
            offset=offset,
        )
        if not points:
            break
        scanned += len(points)
        client.delete(collection_name=collection, points_selector=[p.id for p in points])
        deleted += len(points)
        if offset is None:
            break

    if deleted:
        logger.info(f"Semantic cache sweep: deleted {deleted} stale point(s) (ttl={ttl}s)")
    return {"scanned": scanned, "deleted": deleted}


@app.task(
    bind=True,
    name="tasks.cache_maintenance_tasks.prune_semantic_cache",
    max_retries=0,
    soft_time_limit=120,
)
def prune_semantic_cache(self) -> dict[str, int]:
    """Delete Qdrant semantic-cache points older than the configured TTL."""
    try:
        return _prune_once()
    except Exception as e:
        logger.error(f"Semantic cache sweep failed: {e}")
        return {"scanned": 0, "deleted": 0, "error": str(e)}


if __name__ == "__main__":
    print(_prune_once())
