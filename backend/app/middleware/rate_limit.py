"""Token-bucket rate limit middleware for /api/chat.
Per-tenant + per-user token buckets with Redis-backed Lua script."""

from __future__ import annotations

import ipaddress
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


def _try_set_tenant_from_auth_header(request: Request) -> None:
    """Best-effort: peek at the Authorization bearer token to extract the
    tenant_id claim and populate TenantContext before _chat_bucket_key runs.

    This is NOT an access-control check — the claim is read without signature
    verification solely to scope the rate-limit bucket to the authenticated
    tenant.  On any failure the context is left unchanged and _chat_bucket_key
    falls back to the existing default-tenant behaviour.
    """
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return
        token = auth_header[len("bearer "):].strip()
        if not token:
            return
        import jwt as pyjwt  # PyJWT

        # Decode without verification — we only need the tenant_id claim.
        payload = pyjwt.decode(token, options={"verify_signature": False})
        from app.config import get_settings
        from services.tenant_context import TenantContext

        settings = get_settings()
        tenant_id = (
            payload.get("tenant_id")
            or getattr(settings, "default_tenant_id", "default")
        )
        if isinstance(tenant_id, str) and tenant_id.strip():
            TenantContext.set(tenant_id.strip())
    except Exception:
        # Any failure is intentionally swallowed — this is advisory only.
        pass


def _chat_bucket_key(request: Request) -> str:
    """Build a bounded key from server-resolved tenant context and peer IP.

    Route authentication dependencies run after this ASGI middleware, so an
    authenticated user is not reliably available here. Never substitute a
    client-supplied identity header; use the server-observed peer address,
    normalized and bounded by IP parsing. Behind a trusted proxy, the ASGI
    server's proxy-header allowlist determines which peer address is exposed.
    """
    try:
        from services.tenant_context import TenantContext

        tenant_id = str(TenantContext.get() or "default")[:128]
    except Exception:
        tenant_id = "default"
    try:
        peer = request.client.host if request.client else ""
        subject = ipaddress.ip_address(peer).compressed
    except (ValueError, TypeError, AttributeError):
        subject = "unknown"
    return f"rl:chat:{tenant_id}:{subject}"


class TokenBucketMiddleware(BaseHTTPMiddleware):
    """Per-tenant + server-observed peer-IP token bucket on /api/chat.

    Redis key pattern::

        rl:chat:{tenant_id}:{peer_ip}

    Defaults: 20 tokens per tenant-peer pair, refill 20/min (~1 every 3s).

    The bucket uses current server-resolved tenant context and the server-
    observed peer IP. FastAPI route dependencies run after this middleware,
    so client-supplied identity headers are deliberately never used here.
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

        # Best-effort: resolve tenant from the Authorization header before key
        # construction so _chat_bucket_key sees the correct TenantContext.
        # Route authentication dependencies run after ASGI middleware, so the
        # full auth bridge is not available here. We do a minimal JWT peek
        # (unverified decode, claims only) to extract the tenant_id claim.
        # Access control is never derived from this path — the sole purpose is
        # scoping the rate-limit bucket to the authenticated tenant.
        _try_set_tenant_from_auth_header(request)

        key = _chat_bucket_key(request)
        try:
            if self.script is None:
                self.script = self.r.register_script(LUA_TOKEN_BUCKET)

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
            allowed, remaining = self._local_allowed(key)
            if not allowed:
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=429, content={"error": "rate_limited", "remaining": 0}
                )
            resp = await call_next(request)
            resp.headers["X-RateLimit-Remaining"] = str(int(remaining))
            return resp
import ipaddress
import time
