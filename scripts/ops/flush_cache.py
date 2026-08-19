"""AskMukthiGuru query-cache flusher.

This operation intentionally clears only query-response caches:

* Qdrant semantic-cache collections (active dimensioned collection and the
  historical ``semantic_query_cache`` name when present).
* Redis exact-cache keys under ``mukthiguru:cache:*``.
* Redis semantic-cache payload/index keys under ``mukthiguru:semcache:*``.

It never runs Redis FLUSHALL. Queue jobs, anonymous quota reservations, user
sessions, telemetry streams, Second Brain data, and rate-limit state remain
intact.

Designed to run inside the backend container or through the repository Makefile.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Dict, Iterable, Optional, Union

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SEPARATOR = "=" * 72
_REDIS_QUERY_PATTERNS = ("mukthiguru:cache:*", "mukthiguru:semcache:*")


def _flush_qdrant(qdrant_url: str, collection_names: Iterable[str]) -> dict[str, str]:
    """Delete and recreate only known semantic-cache collections."""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
    except ImportError:
        logger.warning("qdrant_client not installed — skipping Qdrant flush.")
        return {name: "qdrant_client_unavailable" for name in collection_names}

    results: dict[str, str] = {}
    try:
        client = QdrantClient(url=qdrant_url, timeout=10)
        collections = {c.name for c in client.get_collections().collections}
        for name in collection_names:
            if name in collections:
                client.delete_collection(name)
                logger.info("Deleted Qdrant semantic-cache collection %s", name)
            else:
                logger.info("Qdrant semantic-cache collection %s was absent", name)
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )
            results[name] = "recreated"
            logger.info("Recreated empty Qdrant semantic-cache collection %s", name)
    except Exception as exc:
        logger.error("Qdrant query-cache flush failed: %s", exc)
        for name in collection_names:
            results.setdefault(name, f"error: {exc}")
    return results


def _flush_redis(redis_url: str, password: Optional[str] = None) -> Dict[str, Union[int, str]]:
    """Delete only query-cache namespaces using SCAN and batched pipelines."""
    try:
        import redis as redis_lib
    except ImportError:
        logger.error("redis package is required for the targeted cache flush")
        return {pattern: "redis_package_unavailable" for pattern in _REDIS_QUERY_PATTERNS}

    try:
        client_kwargs = {"socket_connect_timeout": 5, "socket_timeout": 10}
        if password:
            client_kwargs["password"] = password
        client = redis_lib.from_url(redis_url, **client_kwargs)
        client.ping()
        results: Dict[str, Union[int, str]] = {}
        for pattern in _REDIS_QUERY_PATTERNS:
            deleted = 0
            pipe = client.pipeline(transaction=False)
            for key in client.scan_iter(match=pattern, count=500):
                pipe.delete(key)
                deleted += 1
                if deleted % 500 == 0:
                    pipe.execute()
                    pipe = client.pipeline(transaction=False)
            if deleted % 500:
                pipe.execute()
            results[pattern] = deleted
            logger.info("Deleted %d Redis query-cache keys matching %s", deleted, pattern)
        return results
    except Exception as exc:
        logger.error("Redis query-cache flush failed: %s", exc)
        return {pattern: f"error: {exc}" for pattern in _REDIS_QUERY_PATTERNS}


def _load_settings():
    """Attempt to load backend settings for correct production URLs."""
    try:
        backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
        sys.path.insert(0, os.path.abspath(backend_dir))
        from app.config import settings

        return settings
    except Exception as exc:
        logger.warning("Could not load app.config settings (%s); using env vars", exc)
        return None


def main() -> int:
    print(f"\n{SEPARATOR}\n  AskMukthiGuru targeted query-cache flush\n{SEPARATOR}\n")
    settings = _load_settings()
    qdrant_url = (
        getattr(settings, "qdrant_url", None) if settings else None
    ) or os.getenv("QDRANT_URL", "http://qdrant:6333")
    redis_url = (
        getattr(settings, "redis_url", None) if settings else None
    ) or os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_password = (
        getattr(settings, "redis_password", None) if settings else None
    ) or os.getenv("REDIS_PASSWORD", "")
    dimension = getattr(settings, "embedding_dimension", 1024) if settings else 1024
    collection_names = (f"mukthi_semantic_cache_{dimension}d", "semantic_query_cache")

    print("[1/2] Clearing Qdrant semantic-cache collections only...")
    qdrant_results = _flush_qdrant(qdrant_url, collection_names)
    print("[2/2] Clearing Redis query-cache namespaces only...")
    redis_results = _flush_redis(redis_url, redis_password or None)
    print("\nQdrant:", qdrant_results)
    print("Redis:", redis_results)
    print("\nQueues, sessions, quotas, telemetry, rate limits, and user data were not flushed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
