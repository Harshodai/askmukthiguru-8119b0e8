"""
Mukthi Guru -- Response Cache Service

Design Patterns:
  - Cache-Aside Pattern: Check cache before pipeline, populate after
  - TTL-based Expiration: Entries expire after 1 hour
  - Semantic Key: Uses normalized query embedding similarity for cache hits

Zero-cost caching using Python stdlib. No external dependencies.
Invalidated automatically when new content is ingested.
"""

import hashlib
import logging
import time
from typing import Optional

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Cache config
_CACHE_MAX_SIZE = 200  # Max cached responses
_CACHE_TTL = 3600  # 1 hour in seconds

from domain.ports.cache_port import ICacheRepository

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

    def put(self, query: str, response: str, intent: str, citations: list[str],
            meditation_step: int = 0) -> None:
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
        return {
            "size": len(self._cache),
            "max_size": self._cache.maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (
                f"{self._hits / (self._hits + self._misses):.1%}"
                if (self._hits + self._misses) > 0
                else "N/A"
            ),
        }

import json

class RedisCacheAdapter(ICacheRepository):
    """
    Redis-based semantic response cache (BE-6).
    """

    def __init__(self, redis_url: str, ttl: int = _CACHE_TTL) -> None:
        import redis
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    def _make_key(self, query: str) -> str:
        """Normalize query and generate cache key."""
        normalized = query.strip().lower()
        key_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"mukthiguru:cache:{key_hash}"

    def get(self, query: str) -> Optional[dict]:
        """Look up a cached response for the given query."""
        key = self._make_key(query)
        result = self._redis.get(key)

        if result is not None:
            self._hits += 1
            logger.info(f"Redis Cache HIT (hits={self._hits}, misses={self._misses})")
            return json.loads(result)

        self._misses += 1
        return None

    def put(self, query: str, response: str, intent: str, citations: list[str],
            meditation_step: int = 0) -> None:
        """Store a response in the cache with TTL."""
        key = self._make_key(query)
        payload = {
            "response": response,
            "intent": intent,
            "citations": citations,
            "meditation_step": meditation_step,
            "cached_at": time.time(),
        }
        self._redis.setex(key, self._ttl, json.dumps(payload))

    def invalidate_all(self) -> None:
        """Clear the entire cache via namespace deletion."""
        keys = self._redis.keys("mukthiguru:cache:*")
        if keys:
            self._redis.delete(*keys)
            logger.info(f"Redis Cache invalidated ({len(keys)} entries cleared)")


def init_llm_cache():
    """
    Initializes the global LangChain cache using GPTCache.
    This intercepts redundant LLM calls (particularly during LightRAG extraction)
    to drastically cut down latency and repetition.
    """
    import os
    from gptcache import Cache
    from gptcache.manager.factory import manager_factory
    from gptcache.processor.pre import get_prompt
    from langchain.globals import set_llm_cache
    from langchain_community.cache import GPTCache
    
    os.makedirs("data/gptcache", exist_ok=True)
    
    def init_gptcache(cache_obj: Cache, llm: str):
        data_manager = manager_factory(
            "sqlite", 
            data_dir="data/gptcache",
            max_size=5000,
            eviction="LRU"
        )
        cache_obj.init(
            pre_embedding_func=get_prompt,
            data_manager=data_manager,
        )

    # Note: we catch potential missing dependencies gracefully if GPTCache is missing
    try:
        set_llm_cache(GPTCache(init_gptcache))
        logger.info("GPTCache successfully attached to LangChain global cache.")
    except Exception as e:
        logger.error(f"Failed to initialize GPTCache: {e}")

