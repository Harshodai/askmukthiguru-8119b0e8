"""Token-bucket rate limit middleware for /api/chat.
Per-tenant + per-user token buckets with Redis-backed Lua script."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

LUA_TOKEN_BUCKET = """
local key       = KEYS[1]
local capacity  = tonumber(ARGV[1])
local refill    = tonumber(ARGV[2])
local now       = tonumber(ARGV[3])
local cost      = tonumber(ARGV[4])
local data      = redis.call('HMGET', key, 'tokens', 'ts')
local tokens    = tonumber(data[1]) or capacity
local ts        = tonumber(data[2]) or now
local delta     = math.max(0, now - ts)
tokens          = math.min(capacity, tokens + delta * refill)
local allowed   = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, math.ceil(capacity / refill) * 2)
return {allowed, tokens}
"""


import logging

logger = logging.getLogger(__name__)


class TokenBucketMiddleware(BaseHTTPMiddleware):
    """Per-tenant + per-user token bucket on /api/chat.

    Redis key pattern::

        rl:chat:{tenant_id}:{user_id}

    Defaults: 20 tokens per tenant-user pair, refill 20/min (~1 every 3s).

    Tenant context is read from ``TenantContext.get()`` which is populated
    by ``set_tenant_from_request`` (FastAPI dependency) earlier in the
    middleware chain.
    """

    def __init__(self, app, redis_url: str, capacity: int = 20, refill_per_sec: float = 20 / 60):
        super().__init__(app)
        import redis.asyncio as redis

        self.r = redis.from_url(redis_url, decode_responses=True)
        self.capacity = capacity
        self.refill = refill_per_sec
        self.script = None
        # ponytail: process-local fallback bucket for when Redis is unreachable.
        # Previously any Redis exception here failed fully open (unlimited
        # /api/chat traffic per replica) — every other rate limiter in this repo
        # (RedisBackedRateLimiter, AnonQuotaRedisAdapter) degrades to a
        # conservative in-process limiter instead. Per-replica only, not shared
        # across replicas; upgrade to a shared cross-process store if that
        # matters more than "some" enforcement during a Redis outage.
        self._local_buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, ts)

    def _local_allowed(self, key: str) -> tuple[bool, float]:
        now = time.time()
        tokens, ts = self._local_buckets.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + max(0.0, now - ts) * self.refill)
        allowed = tokens >= 1
        if allowed:
            tokens -= 1
        self._local_buckets[key] = (tokens, now)
        return allowed, tokens

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        if not request.url.path.startswith("/api/chat"):
            return await call_next(request)

        # Bypass rate limits when IS_PRODUCTION is false
        import os

        if os.getenv("IS_PRODUCTION", "true").lower() == "false":
            return await call_next(request)

        try:
            if self.script is None:
                self.script = self.r.register_script(LUA_TOKEN_BUCKET)

            from services.tenant_context import TenantContext

            tenant_id = TenantContext.get()
            user_id = TenantContext.get_user_id()

            host = request.client.host if request.client else "unknown"
            subject = user_id or request.headers.get("x-user-id") or host
            key = f"rl:chat:{tenant_id}:{subject}"
            allowed, remaining = await self.script(
                keys=[key], args=[self.capacity, self.refill, time.time(), 1]
            )
            if not int(allowed):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=429, content={"error": "rate_limited", "remaining": 0}
                )
            resp = await call_next(request)
            resp.headers["X-RateLimit-Remaining"] = str(int(remaining))
            return resp
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Redis rate limiter unavailable, using local fallback bucket: {e}")
            try:
                from services.tenant_context import TenantContext

                tenant_id = TenantContext.get()
                user_id = TenantContext.get_user_id()
            except Exception:
                tenant_id = user_id = None
            host = request.client.host if request.client else "unknown"
            subject = user_id or request.headers.get("x-user-id") or host
            key = f"rl:chat:{tenant_id}:{subject}"
            allowed, remaining = self._local_allowed(key)
            if not allowed:
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=429, content={"error": "rate_limited", "remaining": 0}
                )
            resp = await call_next(request)
            resp.headers["X-RateLimit-Remaining"] = str(int(remaining))
            return resp
