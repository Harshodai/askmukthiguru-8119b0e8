"""Anonymous message-quota service.

Production path uses Redis; falls back to an in-memory adapter when Redis is
unavailable so the app keeps working in sandboxes/single-node dev. The service
reads limits from app.config.settings so callers only pass a session id.
"""
from __future__ import annotations

import logging

from app.config import settings
from services.anon_quota_port import AnonQuotaPort, QuotaResult
from services.anon_quota_memory import AnonQuotaMemoryAdapter

logger = logging.getLogger(__name__)


class AnonQuotaService(AnonQuotaPort):
    """Settings-aware quota service with Redis/memory adapter selection."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._adapter = self._build_adapter(redis_url)
        self._enabled = bool(getattr(settings, "anon_quota_enabled", True))
        self._limit = int(getattr(settings, "anon_quota_messages", 5))
        self._window_hours = float(getattr(settings, "anon_quota_window_hours", 24.0))
        self._window_seconds = self._window_hours * 3600.0

    def _build_adapter(self, redis_url: str | None) -> AnonQuotaPort:
        if not redis_url:
            logger.info("AnonQuota: no redis_url configured, using in-memory adapter")
            return AnonQuotaMemoryAdapter()
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(redis_url, decode_responses=True)
            # Fail fast: if Redis is unreachable, fall back to memory.
            # We do not await here at __init__ time; a sync ping blocks briefly.
            import asyncio

            loop = asyncio.get_event_loop()
            loop.run_until_complete(client.ping())
            from services.anon_quota_redis import AnonQuotaRedisAdapter

            logger.info("AnonQuota: using Redis adapter")
            return AnonQuotaRedisAdapter(client)
        except Exception as exc:
            logger.warning(f"AnonQuota: Redis adapter failed ({exc}), falling back to in-memory")
            return AnonQuotaMemoryAdapter()

    def _session_id(self, user: dict | None) -> str | None:
        if not user or not user.get("is_anonymous"):
            return None
        sid = user.get("id") or "anonymous"
        return sid if sid.startswith("anon:") else f"anon:{sid}"

    async def check_and_record(self, user: dict | None) -> QuotaResult:
        sid = self._session_id(user)
        if sid is None or not self._enabled:
            return QuotaResult(allowed=True, remaining=self._limit, total_limit=self._limit)
        return await self._adapter.check_and_record(sid, self._limit, self._window_seconds)

    async def inspect(self, user: dict | None) -> QuotaResult:
        sid = self._session_id(user)
        if sid is None or not self._enabled:
            return QuotaResult(allowed=True, remaining=self._limit, total_limit=self._limit)
        return await self._adapter.inspect(sid, self._limit, self._window_seconds)

    async def reset(self, user: dict | None) -> None:
        sid = self._session_id(user)
        if sid is None:
            return
        await self._adapter.reset(sid)

    async def quota_state(self, user: dict | None) -> QuotaResult:
        """Alias for inspect kept for route handlers that prefer explicit naming."""
        return await self.inspect(user)


if __name__ == "__main__":
    import asyncio

    async def _self_check():
        svc = AnonQuotaService()
        anon_user = {"id": "anon:abc", "is_anonymous": True}
        auth_user = {"id": "user-123"}
        assert (await svc.check_and_record(auth_user)).allowed
        for i in range(6):
            r = await svc.check_and_record(anon_user)
            assert (i < 5) == r.allowed, f"iteration {i}: {r}"
        assert (await svc.inspect(anon_user)).remaining == 0
        await svc.reset(anon_user)
        assert (await svc.inspect(anon_user)).remaining == 5
        print("anon_quota_service OK")

    asyncio.run(_self_check())
