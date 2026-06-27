"""
Redis-backed Request Coalescer for Horizontal Scaling.

Merges identical concurrent requests across pods to avoid redundant RAG runs.
Uses Redis SETNX for distributed locking and key TTL for auto-cleanup.
"""

import asyncio
import json
import logging
import time
import typing
from typing import Optional

try:
    import redis.asyncio as Redis
except ImportError:
    Redis = None

logger = logging.getLogger(__name__)

from services.tenant_context import TenantContext


class _InMemoryCoalescer:
    """
    Fallback coalescer when Redis is unavailable.
    Works within a single process only.
    """

    def __init__(self, ttl: float = 60.0):
        self._locks: dict = {}
        self._results: dict = {}
        self._ttl = ttl

    def _cleanup(self):
        now = time.time()
        expired = [k for k, (_, ts) in self._results.items() if now - ts > self._ttl]
        for k in expired:
            self._results.pop(k, None)
            self._locks.pop(k, None)

    async def get_or_run(self, key: str, coro_func: typing.Callable[[], typing.Any]):
        self._cleanup()
        if key in self._results:
            return self._results[key][0]

        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        async with self._locks[key]:
            if key in self._results:
                return self._results[key][0]
            result = await coro_func()
            self._results[key] = (result, time.time())
            return result


class RedisCoalescer:
    """
    Distributed request coalescer backed by Redis.

    Identical concurrent requests across multiple pods share a single
    pipeline execution. The first pod acquires a Redis lock, runs the
    pipeline, stores the result. Other pods poll Redis for the result.
    """

    def __init__(self, redis_url: str, ttl: float = 60.0) -> None:
        if Redis is None:
            raise ImportError("redis package is required for RedisCoalescer")
        self._redis = Redis.from_url(redis_url)
        self._ttl = int(ttl)
        self._poll_interval = 0.1
        self._max_wait = self._ttl  # Don't wait longer than TTL

    async def get_or_run(self, key: str, coro_func: typing.Callable[[], typing.Any]):
        tenant_id = TenantContext.get()
        lock_key = f"coalesce:{tenant_id}:lock:{key}"
        result_key = f"coalesce:{tenant_id}:result:{key}"

        # Try to acquire lock (leader election)
        acquired = await self._redis.set(lock_key, "1", ex=self._ttl + 10, nx=True)
        if acquired:
            return await self._run_as_leader(coro_func, result_key, lock_key)

        # Wait for result from leader
        result = await self._wait_for_result(result_key, lock_key, coro_func)
        return result

    async def _run_as_leader(
        self, coro_func: typing.Callable[[], typing.Any], result_key: str, lock_key: str
    ) -> typing.Any:
        tenant_id = TenantContext.get()
        list_key = f"coalesce:{tenant_id}:list:{result_key.split(':')[-1]}"
        try:
            result = await coro_func()
            try:
                serialized = json.dumps(result, default=str)
                await self._redis.set(result_key, serialized, ex=self._ttl)
                await self._redis.rpush(list_key, "done")
                await self._redis.expire(list_key, self._ttl)
            except (TypeError, ValueError) as e:
                logger.warning(f"Could not serialize coalescer result: {e}")
            return result
        except Exception:
            logger.exception("Coalescer pipeline failed")
            raise
        finally:
            # Remove lock; keep result for TTL so followers can read it
            try:
                await self._redis.delete(lock_key)
            except Exception:
                pass

    async def _wait_for_result(
        self,
        result_key: str,
        lock_key: str,
        coro_func: typing.Callable[[], typing.Any],
    ) -> typing.Any:
        tenant_id = TenantContext.get()
        list_key = f"coalesce:{tenant_id}:list:{result_key.split(':')[-1]}"
        waited = 0.0
        block_timeout = 2
        while waited < self._max_wait:
            # Check if result is available
            data = await self._redis.get(result_key)
            if data:
                try:
                    return json.loads(data)
                except (TypeError, ValueError):
                    pass

            # If leader died without producing result, take over
            lock_exists = await self._redis.exists(lock_key)
            if not lock_exists:
                # Re-attempt to become leader
                acquired = await self._redis.set(lock_key, "1", ex=self._ttl + 10, nx=True)
                if acquired:
                    return await self._run_as_leader(coro_func, result_key, lock_key)

            try:
                res = await self._redis.blpop(list_key, timeout=block_timeout)
                if res:
                    await self._redis.rpush(list_key, "done")
                    data = await self._redis.get(result_key)
                    if data:
                        return json.loads(data)
            except Exception as e:
                logger.warning(f"Error during blpop blocking wait: {e}")
                await asyncio.sleep(0.1)
                waited += 0.1
                continue

            waited += block_timeout

        # Timeout exceeded — run independently
        logger.warning(f"Coalesce timeout for {result_key}, running independently")
        return await coro_func()

    async def close(self):
        try:
            if hasattr(self._redis, "aclose"):
                await self._redis.aclose()
            else:
                await self._redis.close()
        except Exception:
            pass


def build_coalescer(redis_url: Optional[str] = None, ttl: float = 60.0):
    """
    Build the best available coalescer.

    Tries Redis first; falls back to in-memory if Redis is not configured.
    In-memory coalescer only works within a single pod/process.
    """
    if redis_url and Redis is not None:
        try:
            coalescer = RedisCoalescer(redis_url, ttl=ttl)
            logger.info(f"Using Redis coalescer at {redis_url}")
            return coalescer
        except Exception as e:
            logger.warning(f"Failed to create Redis coalescer: {e}, falling back to in-memory")
    return _InMemoryCoalescer(ttl=ttl)
