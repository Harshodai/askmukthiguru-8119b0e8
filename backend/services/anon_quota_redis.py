"""Redis-backed sliding-window adapter for anonymous message quotas.

Uses sorted sets with ZADD + ZREMRANGEBYSCORE for an O(log n) sliding window,
then sets the key TTL to the window duration so expired sessions clean up.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from services.anon_quota_port import AnonQuotaPort, QuotaResult

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class AnonQuotaRedisAdapter(AnonQuotaPort):
    """Redis sorted-set sliding window for anonymous message quotas."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    def _key(self, session_id: str) -> str:
        return f"anon_quota:{session_id}"

    async def check_and_record(
        self,
        session_id: str,
        limit: int,
        window_seconds: float,
    ) -> QuotaResult:
        key = self._key(session_id)
        now = time.time()
        cutoff = now - window_seconds
        ttl = int(window_seconds) + 1

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.pexpire(key, ttl * 1000)
        results = await pipe.execute()
        # results: [pruned_count, current_count, added_count, expire_ok]
        count_after_add = results[1] + results[2]
        allowed = count_after_add <= limit

        if not allowed:
            # Roll back the recorded event so the request is not charged.
            await self._redis.zrem(key, str(now))
            # Recompute remaining without the rolled-back event.
            count_after_add -= 1

        remaining = max(0, limit - count_after_add)
        retry_after: int | None = None
        if not allowed:
            oldest = await self._redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = max(0, int(oldest[0][1] + window_seconds - now) + 1)
        return QuotaResult(
            allowed=allowed,
            remaining=remaining,
            total_limit=limit,
            retry_after_seconds=retry_after,
        )

    async def inspect(
        self,
        session_id: str,
        limit: int,
        window_seconds: float,
    ) -> QuotaResult:
        key = self._key(session_id)
        now = time.time()
        cutoff = now - window_seconds
        await self._redis.zremrangebyscore(key, 0, cutoff)
        count = await self._redis.zcard(key)
        remaining = max(0, limit - count)
        return QuotaResult(allowed=remaining > 0, remaining=remaining, total_limit=limit)

    async def reset(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))


if __name__ == "__main__":
    import asyncio

    async def _self_check():
        try:
            import redis.asyncio as aioredis
        except ImportError:
            print("anon_quota_redis SKIP (redis not installed)")
            return

        r = aioredis.from_url("redis://localhost:6379/0", decode_responses=True)
        try:
            await r.ping()
        except Exception as exc:
            print(f"anon_quota_redis SKIP (no redis): {exc}")
            return

        adapter = AnonQuotaRedisAdapter(r)
        sid = "anon:test-redis"
        await adapter.reset(sid)
        for i in range(6):
            res = await adapter.check_and_record(sid, 5, 1.0)
            assert (i < 5) == res.allowed, f"iteration {i}: {res}"
        await adapter.reset(sid)
        print("anon_quota_redis OK")
        await r.close()

    asyncio.run(_self_check())
