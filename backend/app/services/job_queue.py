from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from enum import Enum
from typing import Any, Callable, Optional

from anyio import Semaphore as AsyncSemaphore

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QueueFullError(Exception):
    pass


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
        self._semaphore = AsyncSemaphore(max_concurrency)
        self._queue: asyncio.Queue[str] | None = None
        self._redis: Any = None
        self._workers: list[asyncio.Task] = []
        self._running = False

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
        return self._redis

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
            await self._redis.aclose()
            self._redis = None
        logger.info("JobQueue: stopped")

    @property
    def queue_size(self) -> int:
        return self._queue.qsize() if self._queue is not None else 0

    @property
    def max_queue(self) -> int:
        return self._max_queue

    async def enqueue(
        self,
        request_data: dict,
        user_id: str,
        is_stream: bool = False,
    ) -> tuple[str, int]:
        """Enqueue a job. Returns (job_id, queue_position). Raises QueueFullError if queue is full."""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        r = await self._get_redis()
        now = time.time()
        pipe = r.pipeline()
        pipe.hset(f"job:{job_id}:meta", mapping={
            "status": JobStatus.QUEUED.value,
            "user_id": user_id,
            "is_stream": "1" if is_stream else "0",
            "created_at": str(now),
            "request_data": json.dumps(request_data),
        })
        pipe.expire(f"job:{job_id}:meta", self._job_ttl)
        pipe.rpush("job_queue:pending", job_id)
        pipe.expire("job_queue:pending", self._job_ttl)
        await pipe.execute()
        queue_position = await r.llen("job_queue:pending")
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
                    jobs.append({
                        "job_id": job_id,
                        "status": meta.get("status", "unknown"),
                        "user_id": meta.get("user_id", ""),
                        "created_at": float(meta.get("created_at", 0)),
                        "is_stream": meta.get("is_stream") == "1",
                        "queue_position": (pending_ids.index(job_id) + 1)
                            if job_id in pending_set else None,
                    })
            if not cursor:
                break
        jobs.sort(key=lambda j: j["created_at"], reverse=True)
        return jobs[:limit]

    async def cancel_job(self, job_id: str) -> bool:
        r = await self._get_redis()
        meta = await r.hgetall(f"job:{job_id}:meta")
        if not meta:
            return False
        status = meta.get("status", "")
        if status == JobStatus.QUEUED.value:
            await r.hset(f"job:{job_id}:meta", "status", JobStatus.CANCELLED.value)
            await r.lrem("job_queue:pending", 1, job_id)
            logger.info(f"JobQueue: cancelled {job_id}")
            return True
        return False

    async def _worker_loop(self, worker_factory: Callable, worker_id: int) -> None:
        while self._running:
            try:
                job_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            async with self._semaphore:
                await self._process_job(job_id, worker_factory, worker_id)
            self._queue.task_done()

    async def _process_job(self, job_id: str, worker_factory: Callable, worker_id: int) -> None:
        r = await self._get_redis()
        meta = await r.hgetall(f"job:{job_id}:meta")
        if not meta or meta.get("status") == JobStatus.CANCELLED.value:
            return
        is_stream = meta.get("is_stream", "0") == "1"
        await r.hset(f"job:{job_id}:meta", mapping={
            "status": JobStatus.PROCESSING.value,
            "started_at": str(time.time()),
        })
        try:
            request_data = json.loads(meta.get("request_data", "{}"))
            result = await worker_factory(request_data, is_stream, job_id)
            if not is_stream:
                await r.set(f"job:{job_id}:result", json.dumps(result, default=str))
            await r.hset(f"job:{job_id}:meta", mapping={
                "status": JobStatus.COMPLETED.value,
                "completed_at": str(time.time()),
            })
            if not is_stream:
                await r.expire(f"job:{job_id}:result", self._job_ttl)
            logger.info(f"JobQueue worker {worker_id}: completed {job_id}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"JobQueue worker {worker_id}: {job_id} failed: {e}")
            await r.set(f"job:{job_id}:error", str(e))
            await r.hset(f"job:{job_id}:meta", mapping={
                "status": JobStatus.FAILED.value,
                "completed_at": str(time.time()),
            })
            await r.expire(f"job:{job_id}:error", self._job_ttl)
        finally:
            await r.lrem("job_queue:pending", 1, job_id)

    @staticmethod
    def _safe_float(val: Optional[str]) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
