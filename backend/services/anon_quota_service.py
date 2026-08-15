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

# Small dedicated probe timeout for lazy Redis selection; deliberately
# independent of the memory-task timeout so a dead Redis fails fast.
_REDIS_PROBE_TIMEOUT = 2.0

# Reservation claim deadline: an interaction must commit its slot (claim)
# within the job-queue TTL plus this safety margin, or the reservation is
# reaped. Chosen so a queued job that dies on queue-TTL expiry stops burning
# its slot shortly after dying instead of holding it for the whole window.
_CLAIM_TTL_MARGIN = 300.0
_CLAIM_TTL_FLOOR = 900.0


class _LazyRedisAdapter(AnonQuotaPort):
    """Placeholder adapter that initializes the real Redis adapter lazily."""

    def __init__(self, service: "AnonQuotaService") -> None:
        self._service = service

    async def check_and_record(
        self, session_id: str, limit: int, window_seconds: float, claim_ttl_seconds: float
    ) -> QuotaResult:
        adapter = await self._service._build_adapter_async()
        return await adapter.check_and_record(session_id, limit, window_seconds, claim_ttl_seconds)

    async def inspect(self, session_id: str, limit: int, window_seconds: float) -> QuotaResult:
        adapter = await self._service._build_adapter_async()
        return await adapter.inspect(session_id, limit, window_seconds)

    async def reset(self, session_id: str) -> None:
        adapter = await self._service._build_adapter_async()
        await adapter.reset(session_id)

    async def claim(self, session_id: str, reservation_id: str) -> None:
        adapter = await self._service._build_adapter_async()
        await adapter.claim(session_id, reservation_id)

    async def release(self, session_id: str, reservation_id: str) -> None:
        adapter = await self._service._build_adapter_async()
        await adapter.release(session_id, reservation_id)


class AnonQuotaService:
    """Settings-aware quota service with Redis/memory adapter selection.

    Implements a user-facing API (``check_and_record(user)`` /
    ``inspect(user)`` / ``reset(user)``); the port interface is reserved
    for storage adapters.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url
        self._adapter: AnonQuotaPort | None = None
        self._enabled = bool(getattr(settings, "anon_quota_enabled", True))
        self._limit = int(getattr(settings, "anon_quota_messages", 5))
        self._window_hours = float(getattr(settings, "anon_quota_window_hours", 24.0))
        self._window_seconds = self._window_hours * 3600.0
        # Deadline by which a reservation must be claimed; see the module
        # constants. Long enough that a live queued job always has time to
        # commit, short enough that a job dropped by queue-TTL expiry stops
        # burning its slot shortly after dying.
        job_ttl = float(getattr(settings, "queue_job_ttl", 1800))
        self._claim_ttl_seconds = max(job_ttl + _CLAIM_TTL_MARGIN, _CLAIM_TTL_FLOOR)

    async def _build_adapter_async(self) -> AnonQuotaPort:
        """Lazy async initialization: probe Redis once and cache the chosen adapter."""
        if self._adapter is not None:
            return self._adapter

        if not self._redis_url:
            logger.info("AnonQuota: no redis_url configured, using in-memory adapter")
            self._adapter = AnonQuotaMemoryAdapter()
            return self._adapter

        try:
            import asyncio

            import redis.asyncio as aioredis

            client = aioredis.from_url(self._redis_url, decode_responses=True)
            await asyncio.wait_for(client.ping(), timeout=_REDIS_PROBE_TIMEOUT)
            from services.anon_quota_redis import AnonQuotaRedisAdapter

            logger.info("AnonQuota: using Redis adapter")
            self._adapter = AnonQuotaRedisAdapter(client)
        except Exception as exc:
            logger.warning(f"AnonQuota: Redis adapter failed ({exc}), falling back to in-memory")
            self._adapter = AnonQuotaMemoryAdapter()
        return self._adapter

    def _build_adapter(self, redis_url: str | None) -> AnonQuotaPort:
        """Synchronous constructor no longer probes Redis; use _build_adapter_async."""
        if not redis_url:
            return AnonQuotaMemoryAdapter()
        # Defer Redis probing to the first async call to avoid calling
        # run_until_complete inside an active event loop.
        return _LazyRedisAdapter(self)

    async def _get_adapter(self) -> AnonQuotaPort:
        return await self._build_adapter_async()

    def _session_id(self, user: dict | None) -> str | None:
        if not user or not user.get("is_anonymous"):
            return None
        sid = user.get("id") or "anonymous"
        return sid if sid.startswith("anon:") else f"anon:{sid}"

    async def check_and_record(self, user: dict | None) -> QuotaResult:
        sid = self._session_id(user)
        if sid is None or not self._enabled:
            return QuotaResult(allowed=True, remaining=self._limit, total_limit=self._limit)
        adapter = await self._get_adapter()
        return await adapter.check_and_record(
            sid, self._limit, self._window_seconds, self._claim_ttl_seconds
        )

    async def inspect(self, user: dict | None) -> QuotaResult:
        sid = self._session_id(user)
        if sid is None or not self._enabled:
            return QuotaResult(allowed=True, remaining=self._limit, total_limit=self._limit)
        adapter = await self._get_adapter()
        return await adapter.inspect(sid, self._limit, self._window_seconds)

    async def reset(self, user: dict | None) -> None:
        sid = self._session_id(user)
        if sid is None:
            return
        adapter = await self._get_adapter()
        await adapter.reset(sid)

    async def claim(self, user: dict | None, reservation_id: str | None) -> None:
        """Commit a reserved slot after a successful interaction.

        A claimed reservation counts against the window until it expires
        naturally. No-op for authenticated users, disabled quotas, and
        missing reservation tokens.
        """
        if not reservation_id:
            return
        sid = self._session_id(user)
        if sid is None or not self._enabled:
            return
        adapter = await self._get_adapter()
        await adapter.claim(sid, reservation_id)

    async def release(self, user: dict | None, reservation_id: str | None) -> None:
        """Give back a reserved slot for a failed/cancelled interaction.

        No-op for authenticated users, disabled quotas, and missing
        reservation tokens (nothing was recorded, so nothing is released).
        """
        if not reservation_id:
            return
        sid = self._session_id(user)
        if sid is None or not self._enabled:
            return
        adapter = await self._get_adapter()
        await adapter.release(sid, reservation_id)

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
        # Release returns the slot for a failed interaction.
        reserved = await svc.check_and_record(anon_user)
        assert reserved.reservation_id is not None
        await svc.release(anon_user, reserved.reservation_id)
        assert (await svc.inspect(anon_user)).remaining == 5
        # Claim commits the slot for a completed interaction.
        claimed = await svc.check_and_record(anon_user)
        assert claimed.reservation_id is not None
        await svc.claim(anon_user, claimed.reservation_id)
        assert (await svc.inspect(anon_user)).remaining == 4
        print("anon_quota_service OK")

    asyncio.run(_self_check())
