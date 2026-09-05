from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from enum import Enum
from typing import Any, Optional

from anyio import Semaphore as AsyncSemaphore

from app.context import correlation_id_var, queue_timing_var

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QueueFullError(Exception):
    pass


class _InMemoryRedisFallback:
    """Drop-in async-Redis-shaped fallback for JobQueueService.

    Production-audit follow-up (2026-09-05 live chaos testing): the entire
    chat job queue was hard-Redis-dependent with no fallback at all — a Redis
    outage 500'd every request (fixed short-term in app/api/chat.py with a
    503). This closes the gap properly: implements exactly the subset of the
    async-Redis interface JobQueueService actually calls (hgetall/hset/set/
    get/delete/expire/lrem/rpush/llen/lrange/scan/pipeline/eval/ping/close),
    backed by plain dicts guarded by one asyncio.Lock. `eval` special-cases
    the two named Lua scripts by identity (module-level constants, same
    objects the real Redis client is invoked with) to preserve the exact
    atomic claim/cancel semantics the real script gives.

    Single-process only — like AnonQuotaMemoryAdapter, this does not
    coordinate across pods/replicas. Once JobQueueService falls back to this,
    it stays on it for the process lifetime (matching the same "degrade and
    stay degraded" choice as AnonQuotaRedisAdapter) rather than attempting to
    detect Redis recovery mid-flight, which would risk split-brain between
    jobs recorded in each store.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.hashes: dict[str, dict[str, str]] = {}
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    async def hgetall(self, key: str) -> dict[str, str]:
        async with self._lock:
            return dict(self.hashes.get(key, {}))

    async def hset(self, key: str, *args, mapping: Optional[dict[str, Any]] = None) -> int:
        async with self._lock:
            target = self.hashes.setdefault(key, {})
            if mapping is not None:
                target.update({str(k): str(v) for k, v in mapping.items()})
            elif len(args) == 2:
                target[str(args[0])] = str(args[1])
            return 1

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: Optional[int] = None
    ) -> bool:
        async with self._lock:
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            return self.values.get(key)

    async def delete(self, key: str) -> int:
        async with self._lock:
            self.hashes.pop(key, None)
            return 1 if self.values.pop(key, None) is not None else 0

    async def expire(self, key: str, seconds: int) -> bool:
        # Best-effort no-op: this store lives only as long as the process, and
        # TTL expiry exists in Redis mainly to bound cross-restart storage —
        # not correctness-critical for an in-memory fallback.
        return True

    async def rpush(self, key: str, value: str) -> int:
        async with self._lock:
            lst = self.lists.setdefault(key, [])
            lst.append(value)
            return len(lst)

    async def lrem(self, key: str, count: int, value: str) -> int:
        async with self._lock:
            values = self.lists.setdefault(key, [])
            removed = 0
            retained: list[str] = []
            for item in values:
                if item == value and (count == 0 or removed < count):
                    removed += 1
                else:
                    retained.append(item)
            self.lists[key] = retained
            return removed

    async def llen(self, key: str) -> int:
        async with self._lock:
            return len(self.lists.get(key, []))

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        async with self._lock:
            values = self.lists.get(key, [])
            if end == -1:
                return list(values[start:])
            return list(values[start : end + 1])

    async def scan(self, cursor: int, match: str = "*", count: int = 100):
        # Single-pass scan: the in-memory dict is never large enough (bounded
        # by max_queue + job_ttl-scale job counts on one pod) to need real
        # cursor-based pagination.
        async with self._lock:
            prefix, _, suffix = match.partition("*")
            keys = [
                k for k in self.hashes if k.startswith(prefix) and (not suffix or k.endswith(suffix))
            ]
            return 0, keys

    def pipeline(self):
        return _InMemoryPipeline(self)

    async def eval(self, script: str, num_keys: int, *args) -> int:
        keys = list(args[:num_keys])
        argv = list(args[num_keys:])
        async with self._lock:
            if script is _CANCEL_LUA:
                meta_key, pending_key = keys
                expected, new_status, job_id = argv
                if self.hashes.get(meta_key, {}).get("status") != expected:
                    return 0
                self.hashes[meta_key]["status"] = new_status
                values = self.lists.setdefault(pending_key, [])
                if job_id in values:
                    values.remove(job_id)
                return 1
            if script is _CLAIM_LUA:
                meta_key = keys[0]
                expected, new_status, started_at = argv
                if self.hashes.get(meta_key, {}).get("status") != expected:
                    return 0
                self.hashes.setdefault(meta_key, {})["status"] = new_status
                self.hashes[meta_key]["started_at"] = started_at
                return 1
            raise AssertionError(f"Unknown Lua script in in-memory fallback: {script[:60]!r}")


class _InMemoryPipeline:
    """Buffers hset/expire/rpush calls for one atomic-looking execute(), mirroring
    the subset of redis.asyncio pipeline usage in JobQueueService.enqueue()."""

    def __init__(self, store: _InMemoryRedisFallback) -> None:
        self._store = store
        self._ops: list[tuple[str, tuple, dict]] = []

    def hset(self, *args, **kwargs):
        self._ops.append(("hset", args, kwargs))
        return self

    def expire(self, *args, **kwargs):
        self._ops.append(("expire", args, kwargs))
        return self

    def rpush(self, *args, **kwargs):
        self._ops.append(("rpush", args, kwargs))
        return self

    async def execute(self) -> list:
        results = []
        for name, args, kwargs in self._ops:
            results.append(await getattr(self._store, name)(*args, **kwargs))
        self._ops.clear()
        return results


# Atomic QUEUED -> CANCELLED transition + pending-list removal. A cancel that
# races a worker's claim must either win cleanly (job never runs) or lose
# cleanly (job already claimed) — never overwrite a newer status.
_CANCEL_LUA = """
local status = redis.call('HGET', KEYS[1], 'status')
if status == ARGV[1] then
    redis.call('HSET', KEYS[1], 'status', ARGV[2])
    redis.call('LREM', KEYS[2], 1, ARGV[3])
    return 1
end
return 0
"""

# Atomic QUEUED -> PROCESSING claim. Only one worker (or a cancel) wins the
# transition; the loser skips the job instead of executing it twice.
_CLAIM_LUA = """
if redis.call('HGET', KEYS[1], 'status') == ARGV[1] then
    redis.call('HSET', KEYS[1], 'status', ARGV[2], 'started_at', ARGV[3])
    return 1
end
return 0
"""


class JobQueueService:
    """Bounded async queue with Redis-backed job storage.

    Design:
      - In-memory asyncio.Queue(maxsize) for light-fast dispatch
      - Redis hash for job metadata + result storage (survives restarts)
      - Semaphore for concurrency gating
      - Worker pool drains the queue and calls a user-supplied coroutine factory
    """

    def __init__(
        self,
        redis_url: str,
        max_queue: int = 20,
        max_concurrency: int = 3,
        job_ttl: int = 600,
    ) -> None:
        self._redis_url = redis_url
        self._max_queue = max_queue
        self._job_ttl = job_ttl
        self._lease_ttl = 300
        self._worker_instance_id = uuid.uuid4().hex
        self._semaphore = AsyncSemaphore(max_concurrency)
        self._queue: asyncio.Queue[str] | None = None
        self._redis: Any = None
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._degraded_to_memory = False

    async def _get_redis(self):
        if self._degraded_to_memory:
            return self._redis
        if self._redis is None:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            try:
                await asyncio.wait_for(self._redis.ping(), timeout=5.0)
            except TimeoutError:
                logger.error("Redis ping timed out after 5s — connection may be stalled")
                raise
        return self._redis

    def _degrade_to_memory(self, exc: Exception) -> None:
        """Switch to the in-memory fallback store and stay on it.

        Production-audit follow-up (2026-09-05 live chaos testing): a Redis
        outage AFTER startup used to raise uncaught from inside enqueue(),
        500ing every /api/chat request (short-term-fixed in app/api/chat.py
        with a 503; this is the real fix). See _InMemoryRedisFallback's
        docstring for why this doesn't attempt to detect recovery mid-flight.
        """
        if self._degraded_to_memory:
            return
        logger.error(
            f"JobQueue: Redis unreachable ({exc}) — degrading to in-memory "
            f"job queue for the remainder of this process's lifetime. "
            f"Cross-pod job visibility and durability across restarts are "
            f"lost until the next deploy/restart with Redis healthy."
        )
        self._redis = _InMemoryRedisFallback()
        self._degraded_to_memory = True

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        module = type(exc).__module__.lower()
        return "redis" in module and (
            "ConnectionError" in type(exc).__name__ or "TimeoutError" in type(exc).__name__
        )

    async def start(self, worker_factory: Callable) -> None:
        """Start worker pool.

        worker_factory is called as worker_factory(request_data, is_stream, job_id)
        and must return the result dict (for sync) or None (for stream).
        """
        self._running = True
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._max_queue)
        r = await self._get_redis()
        pending = await r.lrange("job_queue:pending", 0, -1)
        recovered = 0
        for job_id in pending:
            try:
                self._queue.put_nowait(job_id)
                recovered += 1
            except asyncio.QueueFull:
                break
        for i in range(self._semaphore.value):
            worker = asyncio.create_task(self._worker_loop(worker_factory, i))
            self._workers.append(worker)
        logger.info(
            f"JobQueue: started {len(self._workers)} workers, "
            f"recovered {recovered}/{len(pending)} pending jobs"
        )

    async def stop(self) -> None:
        self._running = False
        for w in self._workers:
            w.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        if self._redis:
            await self._redis.close()
            self._redis = None
        logger.info("JobQueue: stopped")

    @property
    def queue_size(self) -> int:
        return self._queue.qsize() if self._queue is not None else 0

    @property
    def max_queue(self) -> int:
        return self._max_queue

    async def _enqueue_via(self, r: Any, job_id: str, request_data: dict, user_id: str, is_stream: bool) -> int:
        """The actual write sequence, run against whichever client (real Redis
        or the in-memory fallback) `r` is. Split out of enqueue() so a Redis
        connection failure partway through can retry the same sequence
        against the fallback instead of leaving a half-written job."""
        now = time.time()
        pipe = r.pipeline()
        pipe.hset(
            f"job:{job_id}:meta",
            mapping={
                "status": JobStatus.QUEUED.value,
                "user_id": user_id,
                "is_stream": "1" if is_stream else "0",
                "created_at": str(now),
                "admitted_at": str(now),
                "correlation_id": str(correlation_id_var.get() or "-")[:128],
                "request_data": json.dumps(request_data),
            },
        )
        pipe.expire(f"job:{job_id}:meta", self._job_ttl)
        pipe.rpush("job_queue:pending", job_id)
        pipe.expire("job_queue:pending", self._job_ttl)
        await pipe.execute()
        return await r.llen("job_queue:pending")

    async def enqueue(
        self,
        request_data: dict,
        user_id: str,
        is_stream: bool = False,
    ) -> tuple[str, int]:
        """Enqueue a job. Returns (job_id, queue_position). Raises QueueFullError if queue is full."""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        r = await self._get_redis()
        try:
            queue_position = await self._enqueue_via(r, job_id, request_data, user_id, is_stream)
        except Exception as exc:
            if self._degraded_to_memory or not self._is_connection_error(exc):
                raise
            # production-audit follow-up: retry the SAME write against the
            # in-memory fallback rather than losing this job entirely.
            self._degrade_to_memory(exc)
            r = self._redis
            queue_position = await self._enqueue_via(r, job_id, request_data, user_id, is_stream)
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._max_queue)
        try:
            self._queue.put_nowait(job_id)
        except asyncio.QueueFull:
            await r.lrem("job_queue:pending", 1, job_id)
            await r.delete(f"job:{job_id}:meta")
            raise QueueFullError("Server is busy. Please try again shortly.")
        logger.info(f"JobQueue: enqueued {job_id} (stream={is_stream}, user={user_id})")
        return job_id, queue_position

    async def get_job(self, job_id: str) -> Optional[dict]:
        r = await self._get_redis()
        meta = await r.hgetall(f"job:{job_id}:meta")
        if not meta:
            return None
        result_raw = await r.get(f"job:{job_id}:result")
        error_raw = await r.get(f"job:{job_id}:error")
        return {
            "job_id": job_id,
            "status": meta.get("status", "unknown"),
            "created_at": float(meta.get("created_at", 0)),
            "started_at": self._safe_float(meta.get("started_at")),
            "completed_at": self._safe_float(meta.get("completed_at")),
            "user_id": meta.get("user_id", ""),
            "result": json.loads(result_raw) if result_raw else None,
            "error": error_raw,
        }

    async def list_jobs(self, limit: int = 100) -> list[dict]:
        """List all active (non-expired) jobs. Returns most recent first."""
        r = await self._get_redis()
        pending_ids = await r.lrange("job_queue:pending", 0, -1)
        pending_set = set(pending_ids)
        cursor = 0
        jobs: list[dict] = []
        while True:
            cursor, keys = await r.scan(cursor, match="job:*:meta", count=200)
            for key in keys:
                job_id = key.replace("job:", "").replace(":meta", "")
                meta = await r.hgetall(key)
                if meta:
                    jobs.append(
                        {
                            "job_id": job_id,
                            "status": meta.get("status", "unknown"),
                            "user_id": meta.get("user_id", ""),
                            "created_at": float(meta.get("created_at", 0)),
                            "is_stream": meta.get("is_stream") == "1",
                            "queue_position": (pending_ids.index(job_id) + 1)
                            if job_id in pending_set
                            else None,
                        }
                    )
            if not cursor:
                break
        jobs.sort(key=lambda j: j["created_at"], reverse=True)
        return jobs[:limit]

    async def cancel_job(self, job_id: str) -> bool:
        r = await self._get_redis()
        meta = await r.hgetall(f"job:{job_id}:meta")
        if not meta:
            return False
        cancelled = await r.eval(
            _CANCEL_LUA,
            2,
            f"job:{job_id}:meta",
            "job_queue:pending",
            JobStatus.QUEUED.value,
            JobStatus.CANCELLED.value,
            job_id,
        )
        if cancelled:
            logger.info(f"JobQueue: cancelled {job_id}")
        else:
            logger.debug("JobQueue: cancel skipped %s (no longer queued)", job_id)
        return bool(cancelled)

    async def get_request_data(self, job_id: str) -> dict:
        """Return the raw request_data payload for a job, or {} if gone."""
        r = await self._get_redis()
        meta = await r.hgetall(f"job:{job_id}:meta")
        if not meta:
            return {}
        try:
            return json.loads(meta.get("request_data", "{}"))
        except (json.JSONDecodeError, TypeError):
            return {}

    async def _worker_loop(self, worker_factory: Callable, worker_id: int) -> None:
        while self._running:
            try:
                job_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            async with self._semaphore:
                await self._process_job(job_id, worker_factory, worker_id)
            self._queue.task_done()

    async def _release_lease(self, redis_client: Any, lease_key: str, owner: str) -> None:
        """Release only this worker's lease; never delete a newer owner's lock."""
        if await redis_client.get(lease_key) == owner:
            await redis_client.delete(lease_key)

    async def _process_job(self, job_id: str, worker_factory: Callable, worker_id: int) -> None:
        r = await self._get_redis()
        meta = await r.hgetall(f"job:{job_id}:meta")
        if not meta or meta.get("status") in {
            JobStatus.CANCELLED.value,
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
        }:
            return

        lease_key = f"job:{job_id}:lease"
        lease_owner = f"{self._worker_instance_id}:{worker_id}"
        lease_acquired = await r.set(
            lease_key,
            lease_owner,
            nx=True,
            ex=self._lease_ttl,
        )
        if not lease_acquired:
            logger.debug("JobQueue worker %s skipped leased job %s", worker_id, job_id)
            return

        remove_from_pending = True
        try:
            # Re-read after acquiring the lease so a cancelled or terminal job is
            # never resurrected by a competing worker that observed stale metadata.
            meta = await r.hgetall(f"job:{job_id}:meta")
            if not meta or meta.get("status") in {
                JobStatus.CANCELLED.value,
                JobStatus.COMPLETED.value,
                JobStatus.FAILED.value,
            }:
                return

            is_stream = meta.get("is_stream", "0") == "1"
            # Atomic QUEUED -> PROCESSING claim: the final authority on whether
            # a cancel (or a competing worker) already took the job. A failed
            # claim means the job must not run.
            claimed = await r.eval(
                _CLAIM_LUA,
                1,
                f"job:{job_id}:meta",
                JobStatus.QUEUED.value,
                JobStatus.PROCESSING.value,
                str(time.time()),
            )
            if not claimed:
                logger.debug(
                    "JobQueue worker %s: %s no longer queued — skipping", worker_id, job_id
                )
                return
            claimed_at = time.time()
            request_data = json.loads(meta.get("request_data", "{}"))
            dispatch_started_at = time.time()
            await r.hset(
                f"job:{job_id}:meta",
                mapping={
                    "claimed_at": str(claimed_at),
                    "dispatch_started_at": str(dispatch_started_at),
                },
            )
            queue_token = queue_timing_var.set(
                {
                    "admitted_at": self._safe_float(meta.get("created_at")) or dispatch_started_at,
                    "claimed_at": claimed_at,
                    "dispatch_started_at": dispatch_started_at,
                    "correlation_id": str(meta.get("correlation_id") or "-")[:128],
                }
            )
            try:
                result = await worker_factory(request_data, is_stream, job_id)
            finally:
                queue_timing_var.reset(queue_token)
            published_at = time.time()
            if not is_stream:
                await r.set(f"job:{job_id}:result", json.dumps(result, default=str))
            result_trace_id = result.get("trace_id") if isinstance(result, dict) else None
            completion_mapping = {
                "status": JobStatus.COMPLETED.value,
                "completed_at": str(published_at),
                "result_published_at": str(published_at),
            }
            if result_trace_id:
                completion_mapping["trace_id"] = str(result_trace_id)[:128]
            await r.hset(f"job:{job_id}:meta", mapping=completion_mapping)
            if not is_stream:
                await r.expire(f"job:{job_id}:result", self._job_ttl)
            logger.info(f"JobQueue worker {worker_id}: completed {job_id}")
        except asyncio.CancelledError:
            # Shutdown must leave the job recoverable; start() re-enqueues IDs
            # that remain in the durable pending list on the next process.
            remove_from_pending = False
            await r.hset(
                f"job:{job_id}:meta",
                mapping={
                    "status": JobStatus.QUEUED.value,
                    "started_at": "",
                },
            )
            logger.info("JobQueue worker %s returned %s to queued on shutdown", worker_id, job_id)
            raise
        except Exception as e:
            logger.error(f"JobQueue worker {worker_id}: {job_id} failed: {e}")
            await r.set(f"job:{job_id}:error", str(e))
            await r.hset(
                f"job:{job_id}:meta",
                mapping={
                    "status": JobStatus.FAILED.value,
                    "completed_at": str(time.time()),
                },
            )
            await r.expire(f"job:{job_id}:error", self._job_ttl)
        finally:
            await self._release_lease(r, lease_key, lease_owner)
            if remove_from_pending:
                await r.lrem("job_queue:pending", 1, job_id)

    @staticmethod
    def _safe_float(val: Optional[str]) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
