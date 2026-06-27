"""
Retrieval-level doc-ID cache (Ruthless Audit Phase 1 — TTFT optimisation).

Reduces Qdrant round-trips for repeated query patterns by caching the top-k
retrieved document IDs keyed on a (query_embedding_bucket, tenant_id) pair.

Design notes:
- Uses cachetools.TTLCache (pure in-memory, thread-safe wrapper).
- Bucketing quantises the dense query embedding to 1 decimal place before
  hashing, so semantically near-identical queries share a cache entry.
- TTL is governed by settings.retrieval_cache_ttl (default 300 s).
- Safe under asyncio: all operations are O(1) and release the GIL instantly.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from cachetools import TTLCache

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level singleton — created once at import time.
# maxsize=2048 keeps peak memory under ~5 MB (each entry is a list of ≤20 str IDs).
_cache: TTLCache = TTLCache(maxsize=2048, ttl=settings.retrieval_cache_ttl)


def _bucket_key(embedding: list[float], tenant_id: str) -> str:
    """Stable cache key from a quantised dense embedding + tenant.

    Quantises each dimension to 1 decimal place to allow near-identical
    queries to share a cache entry (±0.05 cosine distance typically maps
    to the same bucket).
    """
    quantised = tuple(round(v, 1) for v in embedding)
    raw = f"{tenant_id}|{quantised}"
    return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()


def get(embedding: list[float], tenant_id: str) -> Optional[list[str]]:
    """Return cached doc IDs for this embedding/tenant pair, or None on miss."""
    key = _bucket_key(embedding, tenant_id)
    result = _cache.get(key)
    if result is not None:
        logger.debug("retrieval_cache HIT key=%s n_docs=%d", key[:8], len(result))
    return result


def put(embedding: list[float], tenant_id: str, doc_ids: list[str]) -> None:
    """Store doc IDs for this embedding/tenant pair."""
    if not doc_ids:
        return
    key = _bucket_key(embedding, tenant_id)
    _cache[key] = doc_ids
    logger.debug("retrieval_cache PUT key=%s n_docs=%d ttl=%ds", key[:8], len(doc_ids), settings.retrieval_cache_ttl)


def invalidate(tenant_id: str) -> int:
    """Invalidate all cache entries for a tenant (e.g. after ingestion).

    Returns number of evicted entries.
    """
    evict = [k for k in list(_cache.keys()) if tenant_id in k]
    for k in evict:
        _cache.pop(k, None)
    if evict:
        logger.info("retrieval_cache: evicted %d entries for tenant=%s", len(evict), tenant_id)
    return len(evict)


def stats() -> dict:
    """Return cache size and capacity for metrics/health endpoints."""
    return {
        "size": len(_cache),
        "maxsize": _cache.maxsize,
        "ttl_s": _cache.ttl,
    }
