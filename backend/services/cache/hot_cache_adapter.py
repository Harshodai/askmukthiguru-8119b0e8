"""In-memory hot cache with TTL for FAQ/common queries.

Design: Simple dict + monotonic clock eviction. No external dependencies.
- Keys are normalized (lowercase, stripped) question strings.
- Values are (response, citations, expiry_timestamp, intent) tuples.
- Thread-safe via dict operations (CPython GIL makes single ops atomic).
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class HotCache:
    """Lightweight in-memory cache with per-entry TTL."""

    def __init__(self, default_ttl_s: float = 300.0, max_size: int = 1000):
        self._store: dict[str, tuple[str, list, float, str]] = {}
        self._default_ttl_s = default_ttl_s
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def _normalize(self, key: str) -> str:
        return key.lower().strip()

    def get(self, key: str) -> Optional[tuple[str, list, str]]:
        """Return (response, citations, intent) if cache hit and not expired, else None."""
        norm = self._normalize(key)
        entry = self._store.get(norm)
        if not entry:
            self._misses += 1
            return None
        response, citations, expiry, intent = entry
        if time.monotonic() > expiry:
            del self._store[norm]
            self._misses += 1
            return None
        self._hits += 1
        return response, citations, intent

    def _expire_stale(self) -> int:
        """Remove all TTL-expired entries. Return count evicted."""
        now = time.monotonic()
        expired = [k for k, (_, _, exp, _) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
        return len(expired)

    def put(
        self,
        key: str,
        response: str,
        citations: list,
        ttl: float | None = None,
        intent: str = "QUERY",
    ) -> None:
        """Store response with TTL. Evicts stale entries first, then oldest."""
        norm = self._normalize(key)
        expiry = time.monotonic() + (ttl or self._default_ttl_s)
        self._store[norm] = (response, citations, expiry, intent)
        # Smart eviction: expire stale first, then trim to max_size from oldest
        if len(self._store) > self._max_size:
            stale_count = self._expire_stale()
            if stale_count:
                logger.debug(f"HotCache expired {stale_count} stale entries")
        if len(self._store) > self._max_size:
            overage = len(self._store) - self._max_size
            keys = list(self._store.keys())
            for k in keys[:overage]:
                del self._store[k]
            logger.info(f"HotCache evicted {overage} oldest entries (size limit {self._max_size})")

    def invalidate(self, key: str) -> None:
        norm = self._normalize(key)
        self._store.pop(norm, None)

    def clear(self) -> None:
        self._store.clear()

    def stats(self) -> dict:
        """Return cache statistics including hit rate."""
        now = time.monotonic()
        alive = sum(1 for _, _, expiry, _ in self._store.values() if expiry > now)
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "size": len(self._store),
            "alive": alive,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
        }

    def health_check(self) -> bool:
        """Hot cache has no external dependencies; always healthy."""
        return True


# Singleton instance
hot_cache = HotCache()
