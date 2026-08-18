"""Redis-backed sliding-window adapter for anonymous message quotas.

Uses sorted sets with ZADD + ZREMRANGEBYSCORE for an O(log n) sliding window,
then sets the key TTL to the window duration so expired sessions clean up.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import TYPE_CHECKING

from redis.exceptions import RedisError

from services.anon_quota_memory import AnonQuotaMemoryAdapter, _MAX_WINDOW_SIZE
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
    """Redis sorted-set sliding window for anonymous message quotas with bounded in-memory degradation."""

    def __init__(self, redis_client: aioredis.Redis, max_sessions: int = 500) -> None:
        self._redis = redis_client
        self._fallback = AnonQuotaMemoryAdapter(
            max_sessions=max_sessions, max_limit=_MAX_WINDOW_SIZE
        )
        # Sessions whose last quota operation degraded to the in-memory
        # fallback. While tracked, all operations route to the fallback so
        # reservations recorded there are claimed/released/inspected against
        # the same store; entries expire with the quota window.
        self._degraded_sessions: dict[str, float] = {}
        self._degraded_lock = asyncio.Lock()

    def _key(self, session_id: str) -> str:
        # Shared {session_id} hash tag keeps quota + pending in one Redis
        # Cluster slot so _QUOTA_LUA's two KEYS never hit CROSSSLOT. The
        # anon_quota: / :main prefixes/suffixes are plain text outside the tag.
        return f"anon_quota:{{{session_id}}}:main"

    def _pending_key(self, session_id: str) -> str:
        return f"anon_quota:{{{session_id}}}:pending"

    def _get_fallback_limit(self, limit: int) -> int:
        try:
            from app.config import settings
            degraded_limit = int(getattr(settings, "anon_quota_degraded_limit", 3))
            return min(limit, degraded_limit)
        except Exception:
            return min(limit, 3)

    def _record_degraded(self, event: str) -> None:
        try:
            from app.metrics import ANON_QUOTA_DEGRADED_MODE
            ANON_QUOTA_DEGRADED_MODE.labels(event=event).inc()
        except Exception:
            pass

    async def _is_degraded(self, session_id: str) -> bool:
        """True while the session is routed to the in-memory fallback."""
        async with self._degraded_lock:
            expiry = self._degraded_sessions.get(session_id)
            if expiry is None:
                return False
            if expiry < time.time():
                self._degraded_sessions.pop(session_id, None)
                return False
            return True

    async def _track_degraded(self, session_id: str, window_seconds: float) -> None:
        """Route this session to the fallback for the rest of the quota window."""
        async with self._degraded_lock:
            self._degraded_sessions[session_id] = time.time() + window_seconds

    async def _check_degraded(
        self, session_id: str, limit: int, window_seconds: float, claim_ttl_seconds: float
    ) -> QuotaResult | None:
        """Record on the fallback when this session is degraded; None otherwise."""
        if not await self._is_degraded(session_id):
            return None
        fallback_limit = self._get_fallback_limit(limit)
        return await self._fallback.check_and_record(
            session_id, fallback_limit, window_seconds, claim_ttl_seconds
        )

    async def _inspect_degraded(
        self, session_id: str, limit: int, window_seconds: float
    ) -> QuotaResult | None:
        if not await self._is_degraded(session_id):
            return None
        fallback_limit = self._get_fallback_limit(limit)
        return await self._fallback.inspect(session_id, fallback_limit, window_seconds)

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

        degraded = await self._check_degraded(session_id, limit, window_seconds, claim_ttl_seconds)
        if degraded is not None:
            return degraded

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
            # Degrade to a bounded in-memory sliding-window counter with conservative
            # limit instead of failing open. The session stays on the fallback for
            # the rest of the quota window so reservations recorded here are
            # claimed/released/inspected against the same store (no split-brain).
            logger.warning(
                f"AnonQuotaRedisAdapter.check_and_record degraded to in-memory sliding window (Redis error: {exc})"
            )
            self._record_degraded("check_and_record")
            await self._track_degraded(session_id, window_seconds)
            fallback_limit = self._get_fallback_limit(limit)
            return await self._fallback.check_and_record(
                session_id,
                fallback_limit,
                window_seconds,
                claim_ttl_seconds,
            )

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
        degraded = await self._inspect_degraded(session_id, limit, window_seconds)
        if degraded is not None:
            return degraded

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
            logger.warning(
                f"AnonQuotaRedisAdapter.inspect degraded to in-memory sliding window (Redis error: {exc})"
            )
            self._record_degraded("inspect")
            await self._track_degraded(session_id, window_seconds)
            fallback_limit = self._get_fallback_limit(limit)
            return await self._fallback.inspect(session_id, fallback_limit, window_seconds)
        remaining = max(0, limit - count)
        return QuotaResult(allowed=remaining > 0, remaining=remaining, total_limit=limit)

    async def reset(self, session_id: str) -> None:
        if await self._is_degraded(session_id):
            # A degraded session resets on the fallback; the tracked expiry
            # stays so the window is not silently re-enforced on Redis.
            await self._fallback.reset(session_id)
            return
        try:
            await self._redis.delete(self._key(session_id), self._pending_key(session_id))
        except RedisError as exc:
            logger.warning(f"AnonQuotaRedisAdapter.reset degraded to in-memory fallback (Redis error: {exc})")
            self._record_degraded("reset")
            await self._fallback.reset(session_id)

    async def claim(self, session_id: str, reservation_id: str) -> None:
        # Removing the pending marker commits the reservation: it stays in the
        # window (counts against the limit) until it expires naturally.
        if await self._is_degraded(session_id):
            await self._fallback.claim(session_id, reservation_id)
            return
        try:
            await self._redis.hdel(self._pending_key(session_id), reservation_id)
        except RedisError as exc:
            logger.warning(f"AnonQuotaRedisAdapter.claim degraded to in-memory fallback (Redis error: {exc})")
            self._record_degraded("claim")
            await self._fallback.claim(session_id, reservation_id)

    async def release(self, session_id: str, reservation_id: str) -> None:
        # Single-member removal needs no Lua script: ZREM is atomic and the
        # member is only ever added/removed by quota operations.
        if await self._is_degraded(session_id):
            await self._fallback.release(session_id, reservation_id)
            return
        try:
            await self._redis.zrem(self._key(session_id), reservation_id)
            await self._redis.hdel(self._pending_key(session_id), reservation_id)
        except RedisError as exc:
            logger.warning(f"AnonQuotaRedisAdapter.release degraded to in-memory fallback (Redis error: {exc})")
            self._record_degraded("release")
            await self._fallback.release(session_id, reservation_id)


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
