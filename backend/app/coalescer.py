"""
Redis-backed Request Coalescer for Horizontal Scaling.

Merges identical concurrent requests across pods to avoid redundant RAG runs.
Uses Redis SETNX for distributed locking and key TTL for auto-cleanup.
"""

import asyncio
import dataclasses
import json
import logging
import time
import typing
from typing import Optional

try:
    import redis.asyncio as Redis
except ImportError:
    Redis = None

from prometheus_client import Counter, Histogram

COLLAPSED_REQUESTS = Counter('request_collapsed_total', 'In-flight requests collapsed')
COALESCER_LATENCY = Histogram('coalescer_wait_seconds', 'Time spent waiting for shared result')

logger = logging.getLogger(__name__)

from services.tenant_context import TenantContext


class _InMemoryCoalescer:
    """
    Fallback coalescer when Redis is unavailable.
    Works within a single process only.
    """

    def __init__(self, ttl: float = 60.0):
        self._locks: dict = {}
        self._lock_created: dict = {}
        self._results: dict = {}
        self._ttl = ttl

    def _cleanup(self):
        now = time.time()
        expired = [k for k, (_, ts) in self._results.items() if now - ts > self._ttl]
        for k in expired:
            self._results.pop(k, None)
            self._locks.pop(k, None)
            self._lock_created.pop(k, None)

        # A key whose coro_func() always raises never lands in self._results,
        # so the loop above never sees it -- without this, _locks/_lock_created
        # grow forever for permanently-failing keys. Only drop unlocked entries
        # so an in-flight coalesced call is never disturbed.
        stale_locks = [
            k for k, ts in self._lock_created.items()
            if now - ts > self._ttl and not self._locks.get(k, asyncio.Lock()).locked()
        ]
        for k in stale_locks:
            self._locks.pop(k, None)
            self._lock_created.pop(k, None)

    async def get_or_run(self, key: str, coro_func: typing.Callable[[], typing.Any]):
        self._cleanup()
        if key in self._results:
            COLLAPSED_REQUESTS.inc()
            return self._results[key][0]

        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
            self._lock_created[key] = time.time()

        is_collapsed = self._locks[key].locked()
        if is_collapsed:
            COLLAPSED_REQUESTS.inc()

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
        COLLAPSED_REQUESTS.inc()
        logger.info(f"Collapsing request for key: {key}, waiting for leader to complete")
        with COALESCER_LATENCY.time():
            result = await self._wait_for_result(result_key, lock_key, coro_func)
        return result

    async def _run_as_leader(
        self, coro_func: typing.Callable[[], typing.Any], result_key: str, lock_key: str
    ) -> typing.Any:
        tenant_id = TenantContext.get()
        list_key = f"coalesce:{tenant_id}:list:{result_key.split(':')[-1]}"
        try:
            # Shielded: if the leader's own request (e.g. an SSE client that
            # disconnected) gets cancelled, followers waiting on this same
            # Redis key must not have their shared pipeline run yanked out
            # from under them.
            result = await asyncio.shield(coro_func())
            try:
                serialized = self._serialize_result(result)
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
            # Remove lock; keep result for TTL so followers can read it.
            # Suppress Redis errors here — lock expiry is the safety net.
            try:
                await self._redis.delete(lock_key)
            except Exception as e:  # noqa: BLE001
                logger.debug("Coalescer: failed to delete lock key %s: %s", lock_key, e)

    @staticmethod
    def _serialize_result(result: typing.Any) -> str:
        """Serialize a coalescer result for Redis storage.

        PipelineResult (a frozen dataclass) round-trips via
        dataclasses.asdict plus a type marker so followers can
        reconstruct the original object. Other result types keep the
        plain JSON behavior.
        """
        if dataclasses.is_dataclass(result) and not isinstance(result, type):
            from app.pipeline.result import PipelineResult

            if isinstance(result, PipelineResult):
                return json.dumps(
                    {
                        "__coalescer_type__": "PipelineResult",
                        "data": dataclasses.asdict(result),
                    },
                    default=str,
                )
        return json.dumps(result, default=str)

    @staticmethod
    def _deserialize_result(data: typing.Any) -> typing.Any:
        """Reconstruct the original result type from a stored JSON payload."""
        if isinstance(data, dict) and data.get("__coalescer_type__") == "PipelineResult":
            try:
                from app.pipeline.result import (
                    ActionStep,
                    AnswerEvidence,
                    GuidancePlan,
                    PipelineResult,
                    TeachingAttribution,
                )

                payload = dict(data["data"])
                evidence = payload.get("answer_evidence")
                if isinstance(evidence, dict):
                    payload["answer_evidence"] = AnswerEvidence(**evidence)
                guidance = payload.get("guidance_plan")
                if isinstance(guidance, dict):
                    attribution = guidance.get("attribution")
                    action_step = guidance.get("action_step")
                    if isinstance(attribution, dict):
                        guidance["attribution"] = TeachingAttribution(**attribution)
                    if isinstance(action_step, dict):
                        guidance["action_step"] = ActionStep(**action_step)
                    payload["guidance_plan"] = GuidancePlan(**guidance)
                return PipelineResult(**payload)
            except TypeError as exc:
                logger.warning("Could not reconstruct PipelineResult from coalescer payload: %s", exc)
                return data["data"]
        return data

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
                    return self._deserialize_result(json.loads(data))
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
                        return self._deserialize_result(json.loads(data))
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
        except Exception as e:  # noqa: BLE001
            logger.debug("RedisCoalescer.close(): error closing Redis connection: %s", e)


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
