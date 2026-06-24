"""In-memory cache adapters (exact response, embedding, and search result caches)."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional

from cachetools import TTLCache

from domain.ports.cache_port import ICacheRepository
from services.cache.constants import _CACHE_MAX_SIZE, _CACHE_TTL

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """In-memory embedding cache keyed by SHA-256 of input text.

    Prevents redundant encode() calls when the same query text is embedded
    multiple times across different pipeline stages (retrieval, rerank, semantic cache).
    Uses simple dict with LRU-style eviction.
    """

    def __init__(self, max_size: int = 1000):
        self._cache: dict[str, dict] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
        self._access_order: list[str] = []  # For LRU eviction tracking

    def _key(self, text: str) -> str:
        return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()

    def get(self, text: str) -> Optional[dict]:
        """Return cached embedding dict or None."""
        key = self._key(text)
        cached = self._cache.get(key)
        if cached is not None:
            self._hits += 1
            # Move to end of access order (most recently used)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            return cached
        self._misses += 1
        return None

    def put(self, text: str, embedding: dict) -> None:
        """Cache an embedding dict keyed by input text."""
        key = self._key(text)
        if not self._cache.get(key):
            # Evict oldest if at capacity
            if len(self._cache) >= self._max_size and self._access_order:
                oldest = self._access_order.pop(0)
                self._cache.pop(oldest, None)
            self._access_order.append(key)
        self._cache[key] = embedding

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / total:.1%}" if total > 0 else "N/A",
        }

    def health_check(self) -> bool:
        """Embedding cache has no external dependencies; always healthy."""
        return True


class InMemoryCacheAdapter(ICacheRepository):
    """
    In-memory response cache with TTL expiration.

    Cache key: SHA-256 hash of normalized (lowercased, stripped) query.
    Cache value: dict with 'response', 'intent', 'citations', 'cached_at'.
    """

    def __init__(self, max_size: int = _CACHE_MAX_SIZE, ttl: int = _CACHE_TTL) -> None:
        self._cache: TTLCache = TTLCache(maxsize=max_size, ttl=ttl)
        self._hits = 0
        self._misses = 0

    def _make_key(self, query: str) -> str:
        """Normalize query and generate cache key."""
        normalized = query.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, query: str) -> Optional[dict]:
        """
        Look up a cached response for the given query.

        Returns cached dict or None if not found / expired.
        """
        key = self._make_key(query)
        result = self._cache.get(key)

        if result is not None:
            self._hits += 1
            logger.info(f"Cache HIT (hits={self._hits}, misses={self._misses})")
            return result

        self._misses += 1
        return None

    def put(
        self, query: str, response: str, intent: str, citations: list[str], meditation_step: int = 0
    ) -> None:
        """Store a response in the cache."""
        key = self._make_key(query)
        self._cache[key] = {
            "response": response,
            "intent": intent,
            "citations": citations,
            "meditation_step": meditation_step,
            "cached_at": time.time(),
        }

    def invalidate_all(self) -> None:
        """Clear the entire cache (call after new content ingestion)."""
        size = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache invalidated ({size} entries cleared)")

    @property
    def stats(self) -> dict:
        """Return cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._cache.maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (
                f"{self._hits / total:.1%}"
                if total > 0
                else "N/A"
            ),
        }

    def health_check(self) -> bool:
        """In-memory exact cache has no external dependencies; always healthy."""
        return True


class SearchResultCache:
    """In-memory cache for Qdrant search results.

    Keyed by SHA-256 of (query_vector_hash, content_type, cluster_ids, raptor_level).
    TTL-based expiration (default 5 minutes) -- safe since new content
    is rarely ingested mid-session.
    """

    def __init__(self, maxsize: int = 200, ttl: int = 300):
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._hits = 0
        self._misses = 0

    def _make_key(
        self,
        query_vector_hash: str,
        content_type: Optional[str],
        cluster_ids: Optional[list[int]],
        raptor_level: Optional[int],
    ) -> str:
        raw = (
            f"{query_vector_hash}|{content_type or ''}|"
            f"{sorted(cluster_ids or [])}|{raptor_level or ''}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(
        self,
        query_vector_hash: str,
        content_type: Optional[str] = None,
        cluster_ids: Optional[list[int]] = None,
        raptor_level: Optional[int] = None,
    ) -> Optional[list[dict]]:
        """Look up cached search results. Returns None on miss."""
        key = self._make_key(query_vector_hash, content_type, cluster_ids, raptor_level)
        result = self._cache.get(key)
        if result is not None:
            self._hits += 1
            logger.debug(f"Search result cache HIT (hits={self._hits})")
            return result
        self._misses += 1
        return None

    def put(
        self,
        query_vector_hash: str,
        results: list[dict],
        content_type: Optional[str] = None,
        cluster_ids: Optional[list[int]] = None,
        raptor_level: Optional[int] = None,
    ) -> None:
        """Store search results in the cache."""
        key = self._make_key(query_vector_hash, content_type, cluster_ids, raptor_level)
        self._cache[key] = results

    def invalidate(self) -> None:
        """Clear the entire search result cache."""
        self._cache.clear()
        logger.info("Search result cache invalidated")

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "maxsize": self._cache.maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / total:.1%}" if total > 0 else "N/A",
        }

    def health_check(self) -> bool:
        """Search-result cache has no external dependencies; always healthy."""
        return True
