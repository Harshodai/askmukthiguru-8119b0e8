"""
YouTube Video Availability Service (FI-16).

Verifies availability of YouTube discourse videos via the keyless YouTube oEmbed API:
https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json

Key Characteristics:
- Keyless: No Google Cloud API quota or API key needed.
- Decisive Status Codes:
    * HTTP 200: Video is public and playable -> available=True.
    * HTTP 404, 401, 403, 400: Video is deleted, private, or unavailable -> available=False.
- 600ms Fail-Open Timeout:
    * Network timeouts, connection errors, socket failures fail-open -> available=True.
    * An upstream network hiccup must NEVER block seeker responses or cause internal 500s.
- 2-Tier Caching (24h TTL):
    * Tier 1: In-memory LRU TTLCache (4096 entries, thread-safe).
    * Tier 2: Redis cache under REDIS_KEY_YOUTUBE_AVAILABILITY (yt:avail:{video_id}).
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import httpx
from cachetools import TTLCache

from app.config import settings

logger = logging.getLogger(__name__)

REDIS_KEY_YOUTUBE_AVAILABILITY = "yt:avail:"
AVAILABILITY_CACHE_TTL_SECONDS = 86400  # 24 hours
FAIL_OPEN_TIMEOUT_SECONDS = 0.6  # 600ms
OEMBED_URL_TEMPLATE = (
    "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
)

# Tier 1 In-Memory Cache (Thread-safe LRU TTLCache)
_memory_cache: TTLCache[str, bool] = TTLCache(maxsize=4096, ttl=AVAILABILITY_CACHE_TTL_SECONDS)
_cache_lock = threading.Lock()
_redis_client = None
_redis_lock = threading.Lock()


def _get_redis():
    """Lazily initialize Redis connection for Tier 2 caching."""
    global _redis_client
    if _redis_client is None:
        with _redis_lock:
            if _redis_client is None:
                try:
                    import redis

                    client = redis.Redis.from_url(
                        settings.redis_url, decode_responses=True, socket_timeout=0.5
                    )
                    client.ping()
                    _redis_client = client
                except Exception as e:
                    logger.debug("[YouTubeAvailability] Redis connection unavailable: %s", e)
                    _redis_client = False
    return _redis_client if _redis_client is not False else None


class YouTubeAvailabilityService:
    """Checks YouTube video availability via keyless oEmbed API with 2-tier caching."""

    def __init__(
        self,
        timeout_seconds: float = FAIL_OPEN_TIMEOUT_SECONDS,
        cache_ttl_seconds: int = AVAILABILITY_CACHE_TTL_SECONDS,
    ):
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds

    def _check_memory_cache(self, video_id: str) -> Optional[bool]:
        with _cache_lock:
            return _memory_cache.get(video_id)

    def _set_memory_cache(self, video_id: str, available: bool) -> None:
        with _cache_lock:
            _memory_cache[video_id] = available

    def _check_redis_cache(self, video_id: str) -> Optional[bool]:
        r = _get_redis()
        if r is None:
            return None
        try:
            val = r.get(f"{REDIS_KEY_YOUTUBE_AVAILABILITY}{video_id}")
            if val is not None:
                return val == "1"
        except Exception as e:
            logger.debug("[YouTubeAvailability] Redis read error: %s", e)
        return None

    def _set_redis_cache(self, video_id: str, available: bool) -> None:
        r = _get_redis()
        if r is None:
            return
        try:
            val = "1" if available else "0"
            r.set(
                f"{REDIS_KEY_YOUTUBE_AVAILABILITY}{video_id}",
                val,
                ex=self.cache_ttl_seconds,
            )
        except Exception as e:
            logger.debug("[YouTubeAvailability] Redis write error: %s", e)

    def is_available_sync(self, video_id: str) -> bool:
        """Synchronously check availability: Tier 1 -> Tier 2 -> keyless oEmbed."""
        if not video_id or not video_id.strip():
            return True

        video_id = video_id.strip()

        # Check Tier 1
        cached = self._check_memory_cache(video_id)
        if cached is not None:
            return cached

        # Check Tier 2
        cached_redis = self._check_redis_cache(video_id)
        if cached_redis is not None:
            self._set_memory_cache(video_id, cached_redis)
            return cached_redis

        # Query keyless oEmbed
        url = OEMBED_URL_TEMPLATE.format(video_id=video_id)
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    available = True
                elif resp.status_code in (404, 401, 403, 400):
                    available = False
                else:
                    # Unexpected status (e.g. 500, 429) -> fail-open
                    logger.warning(
                        "[YouTubeAvailability] Unexpected status %d for %s; failing open",
                        resp.status_code,
                        video_id,
                    )
                    return True

                # Cache decisive result
                self._set_memory_cache(video_id, available)
                self._set_redis_cache(video_id, available)
                return available

        except (httpx.TimeoutException, httpx.NetworkError, Exception) as e:
            logger.warning(
                "[YouTubeAvailability] Fail-open for video %s due to exception: %s",
                video_id,
                e,
            )
            return True

    async def is_available_async(self, video_id: str) -> bool:
        """Asynchronously check availability: Tier 1 -> Tier 2 -> keyless oEmbed."""
        if not video_id or not video_id.strip():
            return True

        video_id = video_id.strip()

        # Check Tier 1
        cached = self._check_memory_cache(video_id)
        if cached is not None:
            return cached

        # Check Tier 2
        cached_redis = self._check_redis_cache(video_id)
        if cached_redis is not None:
            self._set_memory_cache(video_id, cached_redis)
            return cached_redis

        # Query keyless oEmbed
        url = OEMBED_URL_TEMPLATE.format(video_id=video_id)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    available = True
                elif resp.status_code in (404, 401, 403, 400):
                    available = False
                else:
                    logger.warning(
                        "[YouTubeAvailability] Unexpected status %d for %s; failing open",
                        resp.status_code,
                        video_id,
                    )
                    return True

                self._set_memory_cache(video_id, available)
                self._set_redis_cache(video_id, available)
                return available

        except (httpx.TimeoutException, httpx.NetworkError, Exception) as e:
            logger.warning(
                "[YouTubeAvailability] Fail-open for video %s due to exception: %s",
                video_id,
                e,
            )
            return True

    def clear_caches(self) -> None:
        """Clear memory cache (used in testing)."""
        with _cache_lock:
            _memory_cache.clear()


_default_service = YouTubeAvailabilityService()


def is_youtube_video_available(video_id: str) -> bool:
    """Convenience sync entry point."""
    return _default_service.is_available_sync(video_id)


async def is_youtube_video_available_async(video_id: str) -> bool:
    """Convenience async entry point."""
    return await _default_service.is_available_async(video_id)
