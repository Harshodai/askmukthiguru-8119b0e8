"""Redis-backed sliding-window adapter for anonymous message quotas.

Uses sorted sets with ZADD + ZREMRANGEBYSCORE for an O(log n) sliding window,
then sets the key TTL to the window duration so expired sessions clean up.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from redis.exceptions import RedisError

from services.anon_quota_port import AnonQuotaPort, QuotaResult

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Atomic prune + count + record for the sliding window. The prune, count,
# add, TTL refresh and conditional rollback must run as one script, or
# concurrent requests could both pass the limit and the compensating
# rollback would leak events. A parallel hash tracks each reservation's
# claim deadline: members whose deadline passed without a claim() (dropped
# jobs, e.g. queue-TTL expiry) are reaped so they cannot burn a slot for
# the rest of the window.
_QUOTA_LUA = """
local key = KEYS[1]
local pending = KEYS[2]
local member = ARGV[1]
local now = tonumber(ARGV[2])
local cutoff = tonumber(ARGV[3])
local limit = tonumber(ARGV[4])
local ttl_ms = tonumber(ARGV[5])
local deadline = tonumber(ARGV[6])

local members = redis.call('ZRANGE', key, 0, -1)
for _, m in ipairs(members) do
    local dl = redis.call('HGET', pending, m)
    if dl and tonumber(dl) < now then
        redis.call('ZREM', key, m)
        redis.call('HDEL', pending, m)
    end
end

redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local count = redis.call('ZCARD', key)
if count >= limit then
    return {0, count}
end
redis.call('ZADD', key, now, member)
redis.call('HSET', pending, member, deadline)
redis.call('PEXPIRE', key, ttl_ms)
redis.call('PEXPIRE', pending, ttl_ms)
return {1, count + 1}
"""


class AnonQuotaRedisAdapter(AnonQuotaPort):
    """Redis sorted-set sliding window for anonymous message quotas."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    def _key(self, session_id: str) -> str:
        # Shared {session_id} hash tag keeps quota + pending in one Redis
        # Cluster slot so _QUOTA_LUA's two KEYS never hit CROSSSLOT. The
        # anon_quota: / :main prefixes/suffixes are plain text outside the tag.
        return f"anon_quota:{{{session_id}}}:main"

    def _pending_key(self, session_id: str) -> str:
        return f"anon_quota:{{{session_id}}}:pending"

    async def check_and_record(
        self,
        session_id: str,
        limit: int,
        window_seconds: float,
        claim_ttl_seconds: float,
    ) -> QuotaResult:
        key = self._key(session_id)
        pending = self._pending_key(session_id)
        now = time.time()
        cutoff = now - window_seconds
        ttl = int(window_seconds) + 1
        member = str(uuid.uuid4())
        deadline = now + claim_ttl_seconds

        try:
            allowed, count_after_add = await self._redis.eval(
                _QUOTA_LUA,
                2,
                key,
                pending,
                member,
                now,
                cutoff,
                limit,
                ttl * 1000,
                deadline,
            )
            allowed = bool(allowed)
            remaining = max(0, limit - count_after_add)
            retry_after: int | None = None
            if not allowed:
                oldest = await self._redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    retry_after = max(0, int(oldest[0][1] + window_seconds - now) + 1)
        except RedisError as exc:
            # This adapter is only selected after a successful cold-start Redis
            # probe (AnonQuotaService._build_adapter_async); a LATER outage
            # (connection drop, timeout) must not 500 anonymous chat. Degrade
            # to allowed -- unenforced, not crashed -- matching the documented
            # mid-session Redis-outage contract (backend/CLAUDE.md).
            logger.warning(f"AnonQuotaRedisAdapter.check_and_record degraded to allowed (Redis error): {exc}")
            return QuotaResult(allowed=True, remaining=limit, total_limit=limit)

        # reservation_id is the member added by the Lua script; only a slot
        # that was actually reserved can be given back via release().
        reservation_id = member if allowed else None
        return QuotaResult(
            allowed=allowed,
            remaining=remaining,
            total_limit=limit,
            retry_after_seconds=retry_after,
            reservation_id=reservation_id,
        )

    async def inspect(
        self,
        session_id: str,
        limit: int,
        window_seconds: float,
    ) -> QuotaResult:
        key = self._key(session_id)
        pending = self._pending_key(session_id)
        now = time.time()
        cutoff = now - window_seconds
        try:
            await self._redis.zremrangebyscore(key, 0, cutoff)
            # Reap reservations whose claim deadline passed without a claim.
            members = await self._redis.zrange(key, 0, -1)
            if members:
                deadlines = await self._redis.hmget(pending, *members)
                for member, dl in zip(members, deadlines):
                    if dl and float(dl) < now:
                        await self._redis.zrem(key, member)
                        await self._redis.hdel(pending, member)
            count = await self._redis.zcard(key)
        except RedisError as exc:
            logger.warning(f"AnonQuotaRedisAdapter.inspect degraded to allowed (Redis error): {exc}")
            return QuotaResult(allowed=True, remaining=limit, total_limit=limit)
        remaining = max(0, limit - count)
        return QuotaResult(allowed=remaining > 0, remaining=remaining, total_limit=limit)

    async def reset(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id), self._pending_key(session_id))

    async def claim(self, session_id: str, reservation_id: str) -> None:
        # Removing the pending marker commits the reservation: it stays in the
        # window (counts against the limit) until it expires naturally.
        await self._redis.hdel(self._pending_key(session_id), reservation_id)

    async def release(self, session_id: str, reservation_id: str) -> None:
        # Single-member removal needs no Lua script: ZREM is atomic and the
        # member is only ever added/removed by quota operations.
        await self._redis.zrem(self._key(session_id), reservation_id)
        await self._redis.hdel(self._pending_key(session_id), reservation_id)


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
            res = await adapter.check_and_record(sid, 5, 1.0, 30.0)
            assert (i < 5) == res.allowed, f"iteration {i}: {res}"
        # Release returns the slot for a failed interaction.
        await adapter.reset(sid)
        reserved = await adapter.check_and_record(sid, 5, 1.0, 30.0)
        assert reserved.reservation_id is not None
        await adapter.release(sid, reserved.reservation_id)
        assert (await adapter.inspect(sid, 5, 1.0)).remaining == 5
        # A claim keeps the slot until natural window expiry.
        claimed = await adapter.check_and_record(sid, 5, 1.0, 30.0)
        await adapter.claim(sid, claimed.reservation_id)
        assert (await adapter.inspect(sid, 5, 1.0)).remaining == 4
        # An unclaimed reservation past its deadline is reaped.
        await adapter.reset(sid)
        dropped = await adapter.check_and_record(sid, 5, 1.0, 0.05)
        assert dropped.reservation_id is not None
        await asyncio.sleep(0.06)
        assert (await adapter.inspect(sid, 5, 1.0)).remaining == 5
        await adapter.reset(sid)
        print("anon_quota_redis OK")
        await r.close()

    asyncio.run(_self_check())
