"""Redis-backed response cache adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Dict, Optional, Union

from app.metrics import (
    REDIS_CACHE_BUDGET_REJECTIONS,
    REDIS_NAMESPACE_KEYS,
    REDIS_NAMESPACE_NONEXPIRING_KEYS,
)

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

    _NAMESPACE = "exact_query"
    _KEY_PATTERN = "mukthiguru:cache:*"

    def __init__(
        self,
        redis_url: str,
        ttl: int = _CACHE_TTL,
        mode: str = "best_effort",
        max_keys: int = 10_000,
        telemetry_interval_seconds: int = 60,
    ) -> None:
        import redis

        self._redis = None
        self._ttl = ttl
        self._hits = 0
        self._misses = 0
        self._mode = mode
        self._max_keys = max(0, int(max_keys))
        self._telemetry_interval_seconds = max(5, int(telemetry_interval_seconds))
        self._last_telemetry_at = 0.0
        self._last_key_count = 0

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
            healthy = bool(self._redis.ping())
            if healthy:
                self._refresh_namespace_telemetry()
            return healthy
        except Exception as exc:
            logger.debug("Redis health check failed: %s", exc)
            return False

    def _make_key(self, query: str) -> str:
        """Normalize query and generate cache key."""
        from services.tenant_context import TenantContext

        normalized = query.strip().lower()
        key_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        tenant_id = TenantContext.get()
        return f"mukthiguru:cache:{tenant_id}:{key_hash}"

    def _refresh_namespace_telemetry(self, force: bool = False) -> Dict[str, int]:
        """Sample only the exact-query namespace and publish bounded metrics.

        This is deliberately not a global Redis scan. Queue, session, quota,
        telemetry, and Second Brain namespaces remain outside the policy.
        """
        if not self._redis:
            return {"keys": 0, "nonexpiring": 0}
        now = time.monotonic()
        if not force and now - self._last_telemetry_at < self._telemetry_interval_seconds:
            return {"keys": self._last_key_count, "nonexpiring": 0}

        keys = 0
        nonexpiring = 0
        try:
            for key in self._redis.scan_iter(match=self._KEY_PATTERN, count=500):
                keys += 1
                if self._redis.ttl(key) < 0:
                    nonexpiring += 1
                if self._max_keys and keys > self._max_keys:
                    logger.warning(
                        "Redis exact-query cache exceeded configured scan budget (%d)",
                        self._max_keys,
                    )
                    break
            self._last_key_count = keys
            self._last_telemetry_at = now
            REDIS_NAMESPACE_KEYS.labels(namespace=self._NAMESPACE).set(keys)
            REDIS_NAMESPACE_NONEXPIRING_KEYS.labels(namespace=self._NAMESPACE).set(nonexpiring)
        except Exception as exc:
            logger.warning("Redis exact-query telemetry failed: %s", exc)
        return {"keys": keys, "nonexpiring": nonexpiring}

    def telemetry_snapshot(self, force: bool = False) -> Dict[str, Union[int, str]]:
        """Return non-sensitive exact-query namespace telemetry for health/ops."""
        snapshot = self._refresh_namespace_telemetry(force=force)
        snapshot.update({"namespace": self._NAMESPACE, "max_keys": self._max_keys})
        return snapshot

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
            if self._max_keys and not self._redis.exists(key):
                snapshot = self._refresh_namespace_telemetry()
                if snapshot["keys"] >= self._max_keys:
                    REDIS_CACHE_BUDGET_REJECTIONS.labels(namespace=self._NAMESPACE).inc()
                    logger.warning(
                        "Redis exact-query cache budget reached (%d keys); skipping cache write",
                        self._max_keys,
                    )
                    return
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
