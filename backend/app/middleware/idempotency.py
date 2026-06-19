"""
Mukthi Guru — Idempotency Middleware

Prevents duplicate processing of mutating requests (POST/PATCH/PUT) by
checking for an Idempotency-Key header. If a key is provided and has been
seen before (within the TTL window), the cached response is returned
instead of re-processing the request.

Storage: Redis with 24-hour TTL (configurable via settings).
Keys prefixed with "idempotency:" to avoid namespace collisions.

Usage:
    app.add_middleware(IdempotencyMiddleware)

    # Client sends:
    POST /api/feedback
    Idempotency-Key: uuid-v7-or-client-generated-key
    ...
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional

from app.config import settings
from app.metrics import IDEMPOTENCY_CACHE_HIT_TOTAL, IDEMPOTENCY_CACHE_MISS_TOTAL
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

_IDEMPOTENCY_TTL = settings.idempotency_ttl_seconds if hasattr(settings, 'idempotency_ttl_seconds') else 86400
_IDEMPOTENCY_PREFIX = settings.idempotency_redis_prefix if hasattr(settings, 'idempotency_redis_prefix') else "idempotency:"


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces idempotency on mutating requests.

    Reads the Idempotency-Key header from POST/PATCH/PUT requests.
    If the key is recognized, returns the cached response with
    X-Idempotent-Replayed: true. Otherwise, lets the request through
    and caches the response.

    GET, HEAD, OPTIONS, DELETE requests are never idempotency-checked.
    """

    def __init__(
        self,
        app: ASGIApp,
        redis_url: Optional[str] = None,
        ttl: int = _IDEMPOTENCY_TTL,
        idempotent_paths: Optional[list[str]] = None,
    ) -> None:
        super().__init__(app)
        self._redis_url = redis_url or getattr(settings, "redis_url", None)
        self._ttl = ttl
        self._redis = None
        self._idempotent_paths = idempotent_paths or [
            "/api/feedback",
            "/api/ingest",
        ]

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            try:
                self._redis = aioredis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"Idempotency Redis unavailable: {e}. Idempotency disabled.")
                self._redis = None
        return self._redis

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in ("POST", "PATCH", "PUT"):
            return await call_next(request)

        path = request.url.path
        if not any(path.startswith(p) for p in self._idempotent_paths):
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            return await call_next(request)

        redis_conn = await self._get_redis()
        if redis_conn is None:
            return await call_next(request)

        redis_key = f"{_IDEMPOTENCY_PREFIX}{idempotency_key}"

        try:
            cached = await redis_conn.get(redis_key)
            if cached is not None:
                IDEMPOTENCY_CACHE_HIT_TOTAL.inc()
                data = json.loads(cached)
                headers = MutableHeaders()
                headers["X-Idempotent-Replayed"] = "true"
                return JSONResponse(
                    content=data.get("body", {}),
                    status_code=data.get("status_code", 200),
                    headers=dict(headers),
                )
            IDEMPOTENCY_CACHE_MISS_TOTAL.inc()
        except Exception as e:
            logger.warning(f"Idempotency cache read failed: {e}")

        response = await call_next(request)

        if 200 <= response.status_code < 500:
            body = await self._extract_body(response)
            cache_data = {
                "status_code": response.status_code,
                "body": body,
                "cached_at": time.time(),
            }
            try:
                await redis_conn.setex(
                    redis_key,
                    self._ttl,
                    json.dumps(cache_data),
                )
            except Exception as e:
                logger.warning(f"Idempotency cache write failed: {e}")

        return response

    @staticmethod
    async def _extract_body(response: Response) -> dict | list | str:
        try:
            if hasattr(response, "body_iterator"):
                chunks = [chunk async for chunk in response.body_iterator]
                response.body_iterator = IdempotencyMiddleware._iterate_chunks(chunks)
                raw = b"".join(chunks)
            elif hasattr(response, "body"):
                raw = response.body if isinstance(response.body, bytes) else b""
            else:
                return {}
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    @staticmethod
    async def _iterate_chunks(chunks: list[bytes]):
        for chunk in chunks:
            yield chunk
