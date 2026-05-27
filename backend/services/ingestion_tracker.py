"""
Ingestion Status Tracker backed by Redis (or in-memory fallback).

Tracks progress of active content-ingestion jobs across all pods
so that /api/ingest/status returns consistent data regardless
of which backend pod handles the request.
"""

import time
import typing

# Try to import sync Redis first
_redis = None
try:
    import redis as _redis_module
    _redis = _redis_module.Redis
except ImportError:
    _redis = None  # type: ignore[assignment]


class IngestionTracker:
    """Base interface for ingestion tracking."""

    def update(self, url: str, message: str, percent: float) -> None:
        raise NotImplementedError  # pragma: no cover

    def get_all(self) -> dict:
        raise NotImplementedError  # pragma: no cover

    def mark_error(self, url: str, error_message: str) -> None:
        raise NotImplementedError  # pragma: no cover


class _InMemoryIngestionTracker(IngestionTracker):
    """Fallback tracker when Redis is unavailable."""

    def __init__(self) -> None:
        self._data: dict = {}

    def update(self, url: str, message: str, percent: float) -> None:
        self._data[url] = {
            "url": url,
            "message": message,
            "progress": percent,
            "updated_at": time.time(),
            "status": "processing" if percent < 1.0 else "success",
        }

    def get_all(self) -> dict:
        return self._data.copy()

    def mark_error(self, url: str, error_message: str) -> None:
        self._data[url] = {
            "url": url,
            "message": error_message,
            "progress": 0.0,
            "updated_at": time.time(),
            "status": "error",
        }


class RedisIngestionTracker(IngestionTracker):
    """
    Redis-backed ingestion tracker using the synchronous Redis client.
    """

    _KEY_PREFIX = "ingest:status"
    _TTL = 24 * 3600  # 24 hours

    def __init__(self, redis_url: str) -> None:
        if _redis is None:
            raise ImportError("redis package is required for RedisIngestionTracker")
        self._client = _redis_module.Redis.from_url(redis_url, decode_responses=True)  # type: ignore[union-attr]

    def _key(self, url: str) -> str:
        return f"{self._KEY_PREFIX}:{url}"

    def update(self, url: str, message: str, percent: float) -> None:
        data = {
            "url": url,
            "message": message,
            "progress": str(percent),
            "updated_at": str(time.time()),
            "status": "processing" if percent < 1.0 else "success",
        }
        key = self._key(url)
        self._client.hset(key, mapping=data)  # type: ignore[no-untyped-call]
        self._client.expire(key, self._TTL)  # type: ignore[no-untyped-call]

    def get_all(self) -> dict:
        keys = list(self._client.scan_iter(match=f"{self._KEY_PREFIX}:*"))  # type: ignore[no-untyped-call]
        result: dict[str, typing.Any] = {}
        for key in keys:
            data = self._client.hgetall(key)  # type: ignore[no-untyped-call]
            if data:
                url = key.replace(f"{self._KEY_PREFIX}:", "")
                result[url] = {
                    k: v for k, v in data.items()
                }
        return result

    def mark_error(self, url: str, error_message: str) -> None:
        key = self._key(url)
        data = {
            "url": url,
            "message": error_message,
            "progress": "0.0",
            "updated_at": str(time.time()),
            "status": "error",
        }
        self._client.hset(key, mapping=data)  # type: ignore[no-untyped-call]
        self._client.expire(key, self._TTL)  # type: ignore[no-untyped-call]


def build_tracker(redis_url: str | None = None) -> IngestionTracker:
    if redis_url and _redis is not None:
        return RedisIngestionTracker(redis_url)
    return _InMemoryIngestionTracker()
