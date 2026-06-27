"""Redis-backed response cache adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional

from domain.ports.cache_port import ICacheRepository
from services.cache.constants import _CACHE_TTL
from services.cache.exceptions import CacheInitializationError

logger = logging.getLogger(__name__)


class RedisCacheAdapter(ICacheRepository):
    """
    Redis-based semantic response cache (BE-6).

    Init modes:
      - best_effort (default): try Redis, fall back to disabled (no caching) on failure.
      - fail_closed: raise CacheInitializationError if Redis is unreachable.
        Use this when Redis is required for correctness (e.g. distributed caching).
    """

    def __init__(
        self,
        redis_url: str,
        ttl: int = _CACHE_TTL,
        mode: str = "best_effort",
    ) -> None:
        import redis

        self._redis = None
        self._ttl = ttl
        self._hits = 0
        self._misses = 0
        self._mode = mode

        try:
            self._redis = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            self._redis.ping()
            logger.info("RedisCacheAdapter connected to Redis")
        except Exception as e:
            if mode == "fail_closed":
                raise CacheInitializationError(
                    f"Redis is required but unavailable (mode={mode}, url={redis_url}): {e}"
                ) from e
            logger.warning(f"Failed to connect to Redis: {e}. Gracefully continuing without cache.")
            self._redis = None

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_available(self) -> bool:
        return self._redis is not None

    def health_check(self) -> bool:
        """Verify Redis connection is alive."""
        if not self._redis:
            return False
        try:
            return self._redis.ping()
        except Exception:
            return False

    def _make_key(self, query: str) -> str:
        """Normalize query and generate cache key."""
        from services.tenant_context import TenantContext
        normalized = query.strip().lower()
        key_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        tenant_id = TenantContext.get()
        return f"mukthiguru:cache:{tenant_id}:{key_hash}"

    def get(self, query: str) -> Optional[dict]:
        """Look up a cached response for the given query."""
        if not self._redis:
            return None

        try:
            key = self._make_key(query)
            result = self._redis.get(key)

            if result is not None:
                self._hits += 1
                logger.info(f"Redis Cache HIT (hits={self._hits}, misses={self._misses})")
                return json.loads(result)
        except Exception as e:
            logger.warning(f"Redis get failed for query={query}: {e}")

        self._misses += 1
        return None

    def put(
        self, query: str, response: str, intent: str, citations: list[str], meditation_step: int = 0
    ) -> None:
        """Store a response in the cache with TTL."""
        if not self._redis:
            return

        try:
            key = self._make_key(query)
            payload = {
                "response": response,
                "intent": intent,
                "citations": citations,
                "meditation_step": meditation_step,
                "cached_at": time.time(),
            }
            self._redis.setex(key, self._ttl, json.dumps(payload))
        except Exception as e:
            logger.warning(f"Redis put failed for query={query}: {e}")

    def invalidate_all(self) -> None:
        """Clear the entire cache via namespace deletion using non-blocking SCAN batched pipeline."""
        if not self._redis:
            return

        try:
            pipe = self._redis.pipeline()
            count = 0
            from services.tenant_context import TenantContext
            tenant_id = TenantContext.get()
            for key in self._redis.scan_iter(match=f"mukthiguru:cache:{tenant_id}:*"):
                pipe.delete(key)
                count += 1
                # Execute in batches of 1000 to prevent large memory spikes or blocking
                if count % 1000 == 0:
                    pipe.execute()
                    pipe = self._redis.pipeline()
            if count % 1000 != 0:
                pipe.execute()
            logger.info(f"Redis Cache invalidated ({count} entries cleared)")
        except Exception as e:
            logger.warning(f"Redis invalidate failed: {e}")
