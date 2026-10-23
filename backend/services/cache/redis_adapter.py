"""Redis-backed response cache adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional

from app.metrics import (
    REDIS_CACHE_BUDGET_REJECTIONS,
    REDIS_NAMESPACE_KEYS,
    REDIS_NAMESPACE_NONEXPIRING_KEYS,
    set_cache_hit_ratio,
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
                max_connections=32,
            )
            self._redis.ping()
            logger.info("RedisCacheAdapter connected to Redis")
        except Exception as e:
            if mode == "fail_closed":
                # Redis URLs can embed credentials; never echo the URL or raw
                # client exception into an application log/error response.
                raise CacheInitializationError(
                    f"Redis is required but unavailable (mode={mode}, error={type(e).__name__})"
                ) from None
            logger.warning(
                "Failed to connect to Redis (error=%s); continuing without cache.",
                type(e).__name__,
            )
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

    def _make_key(self, query: str, user_id: str | None = None) -> str:
        """Normalize query and generate cache key.

        When ``user_id`` is provided, a personalized cache namespace is used
        so that personalized queries (those carrying user-specific context like
        topic_boost, teaching_boost, or memory_context) are never served from
        or written to the shared cache. When ``user_id`` is absent (anonymous),
        the shared key is used unchanged.
        """
        from services.tenant_context import TenantContext

        normalized = query.strip().lower()
        hash_input = normalized
        if user_id:
            hash_input = f"{normalized}:{user_id}"
        key_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        tenant_id = TenantContext.get()
        return f"mukthiguru:cache:{tenant_id}:{key_hash}"

    def _user_index_key(self, user_id: str) -> str:
        """Tenant-scoped index of personal exact-cache keys for erasure."""
        from services.tenant_context import TenantContext

        digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
        return f"mukthiguru:user_cache_index:{TenantContext.get()}:{digest}"

    def invalidate_user(self, user_id: str, *, all_tenants: bool = False) -> int:
        """Invalidate exact answers after a memory privacy change.

        Current keys are tenant-scoped, but older deployments wrote query-only
        keys (mukthiguru:cache:<digest>). Those legacy keys have no owner or
        tenant metadata, so a scoped privacy mutation must delete them too:
        they cannot safely be attributed to another tenant. Other Redis
        namespaces remain untouched.
        """
        if not self._redis:
            raise RuntimeError(
                "Redis exact cache is unavailable; privacy invalidation cannot be confirmed"
            )

        from services.tenant_context import TenantContext

        tenant_id = TenantContext.get()
        tenant_prefix = f"mukthiguru:cache:{tenant_id}:"
        index_pattern = (
            "mukthiguru:user_cache_index:*:*"
            if all_tenants
            else f"mukthiguru:user_cache_index:{tenant_id}:*"
        )
        try:
            deleted = 0
            pipe = self._redis.pipeline()
            # Scan the exact-cache namespace once, selecting current keys for
            # this tenant (or all tenants for account erasure) and legacy
            # unscoped keys. A tenant-only wildcard misses pre-tenant keys.
            for key in self._redis.scan_iter(match="mukthiguru:cache:*", count=500):
                is_legacy_unscoped = str(key).count(":") == 2
                in_scope = all_tenants or str(key).startswith(tenant_prefix) or is_legacy_unscoped
                if not in_scope:
                    continue
                pipe.delete(key)
                deleted += 1
                if deleted % 1000 == 0:
                    pipe.execute()
                    pipe = self._redis.pipeline()
            pipe.execute()

            deleted_indexes = 0
            pipe = self._redis.pipeline()
            for key in self._redis.scan_iter(match=index_pattern, count=500):
                pipe.delete(key)
                deleted_indexes += 1
                if deleted_indexes % 1000 == 0:
                    pipe.execute()
                    pipe = self._redis.pipeline()
            pipe.execute()

            logger.info(
                "Invalidated exact cache after a memory privacy change "
                "(entries=%d, indexes=%d, scope=%s, tenant=%s)",
                deleted,
                deleted_indexes,
                "all_tenants" if all_tenants else "tenant_plus_legacy",
                tenant_id,
            )
            return deleted
        except Exception as exc:
            # Preserve the original storage failure so callers can fail closed
            # without an unrelated NameError masking the root cause.
            logger.error(
                "User-scoped exact-cache invalidation failed (%s)",
                type(exc).__name__,
            )
            raise

    def _refresh_namespace_telemetry(self, force: bool = False) -> dict[str, int]:
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

    def telemetry_snapshot(self, force: bool = False) -> dict[str, int | str]:
        """Return non-sensitive exact-query namespace telemetry for health/ops."""
        snapshot = self._refresh_namespace_telemetry(force=force)
        snapshot.update({"namespace": self._NAMESPACE, "max_keys": self._max_keys})
        return snapshot

    def _report_hit_ratio(self) -> None:
        total = self._hits + self._misses
        if not total:
            return
        try:
            set_cache_hit_ratio("exact", self._hits / total)
        except Exception:
            pass

    def get(self, query: str, user_id: str | None = None) -> Optional[dict]:
        """Look up a cached response for the given query.

        When ``user_id`` is provided, the lookup uses a personalized cache
        namespace so that a previously-cached personalized answer is never
        served to a different user.
        """
        if not self._redis:
            return None

        try:
            key = self._make_key(query, user_id=user_id)
            result = self._redis.get(key)

            if result is not None:
                self._hits += 1
                self._report_hit_ratio()
                logger.info(f"Redis Cache HIT (hits={self._hits}, misses={self._misses})")
                return json.loads(result)
        except Exception as e:
            logger.warning("Redis get failed (query_len=%d): %s", len(query), e)

        self._misses += 1
        self._report_hit_ratio()
        return None

    def put(
        self,
        query: str,
        response: str,
        intent: str,
        citations: list[str],
        meditation_step: int = 0,
        user_id: str | None = None,
    ) -> None:
        """Store a response in the cache with TTL.

        When ``user_id`` is provided, the entry is written to a personalized
        cache namespace so it is never served to another user.
        """
        if not self._redis:
            return

        try:
            key = self._make_key(query, user_id=user_id)
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
            if user_id:
                # Do not publish a personal answer unless its erase index is
                # recorded in the same pipeline. Both index and answer expire
                # together; invalidate_user removes both on consent revocation.
                pipe = self._redis.pipeline()
                index_key = self._user_index_key(user_id)
                pipe.sadd(index_key, key)
                pipe.expire(index_key, self._ttl)
                pipe.setex(key, self._ttl, json.dumps(payload))
                pipe.execute()
            else:
                self._redis.setex(key, self._ttl, json.dumps(payload))
        except Exception as e:
            # Queries can contain PII or user-supplied control characters. Keep
            # operational logs bounded and do not echo the query or provider text.
            logger.warning(
                "Redis put failed (query_len=%d, error=%s)", len(query), type(e).__name__
            )

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
            # Remove indexes as well as exact keys; otherwise a future
            # invalidation can point at keys removed by this full-cache clear.
            for key in self._redis.scan_iter(match=f"mukthiguru:user_cache_index:{tenant_id}:*"):
                self._redis.delete(key)
            logger.info(f"Redis Cache invalidated ({count} entries cleared)")
        except Exception as e:
            logger.warning(f"Redis invalidate failed: {e}")
