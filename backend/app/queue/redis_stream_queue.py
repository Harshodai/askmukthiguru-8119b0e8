from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional

from app.queue.request_queue import BaseRequestQueue, QueueItem, QueueStatus, RequestPriority

logger = logging.getLogger(__name__)

_STREAM_KEYS = {
    RequestPriority.FAST: "request:fast",
    RequestPriority.STANDARD: "request:standard",
    RequestPriority.DEEP: "request:deep",
}


class RedisStreamQueue(BaseRequestQueue):
    """Redis Streams-backed request queue.

    Implements BaseRequestQueue using Redis Streams with consumer groups.
    Supports priority lanes via separate stream keys.

    NOTE: This implementation requires a running Redis instance and is
    gated behind USE_REQUEST_QUEUE=true. Until that flag is set, the
    InProcessQueue (no-op) is used instead.
    """

    def __init__(
        self,
        redis_url: str,
        consumer_group: str = "backend-workers",
        consumer_id: str | None = None,
        max_stream_length: int = 10_000,
    ):
        self._redis_url = redis_url
        self._consumer_group = consumer_group
        self._consumer_id = consumer_id or f"worker_{uuid.uuid4().hex[:8]}"
        self._max_stream_length = max_stream_length
        self._redis: Any = None
        self._running = False

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def _ensure_group(self, stream_key: str) -> None:
        r = await self._get_redis()
        try:
            await r.xgroup_create(stream_key, self._consumer_group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                logger.warning(f"xgroup_create({stream_key}): {exc}")

    async def start(self) -> None:
        self._running = True
        r = await self._get_redis()
        for stream_key in set(_STREAM_KEYS.values()):
            await self._ensure_group(stream_key)
        logger.info(
            "RedisStreamQueue: started (group=%s, consumer=%s)",
            self._consumer_group,
            self._consumer_id,
        )

    async def stop(self) -> None:
        self._running = False
        if self._redis:
            await self._redis.close()
            self._redis = None
        logger.info("RedisStreamQueue: stopped")

    async def enqueue(
        self,
        request_data: dict,
        user_id: str,
        priority: RequestPriority = RequestPriority.STANDARD,
        is_stream: bool = False,
    ) -> tuple[str, int]:
        r = await self._get_redis()
        job_id = f"q_{uuid.uuid4().hex[:12]}"
        stream_key = _STREAM_KEYS.get(priority, _STREAM_KEYS[RequestPriority.STANDARD])
        body = {
            "job_id": job_id,
            "user_id": user_id,
            "is_stream": "1" if is_stream else "0",
            "created_at": str(time.time()),
            "priority": priority.value,
            "request_data": json.dumps(request_data),
        }
        await r.xadd(stream_key, body, maxlen=self._max_stream_length)
        depth = await r.xlen(stream_key)
        logger.info("RedisStreamQueue: enqueued %s -> %s (depth=%d)", job_id, stream_key, depth)
        return job_id, depth

    async def dequeue(
        self,
        consumer_id: str,
        priority: Optional[RequestPriority] = None,
        timeout: float = 1.0,
    ) -> Optional[QueueItem]:
        r = await self._get_redis()
        stream_keys = (
            [_STREAM_KEYS[priority]]
            if priority
            else [_STREAM_KEYS[p] for p in sorted(RequestPriority)]
        )
        results = await r.xreadgroup(
            group=self._consumer_group,
            consumer=consumer_id or self._consumer_id,
            streams={k: ">" for k in stream_keys},
            count=1,
            block=int(timeout * 1000),
        )
        if not results:
            return None
        stream_key, messages = results[0]
        if not messages:
            return None
        msg_id, data = messages[0]
        item = QueueItem(
            job_id=data.get("job_id", msg_id),
            priority=RequestPriority(int(data.get("priority", RequestPriority.STANDARD.value))),
            request_data=json.loads(data.get("request_data", "{}")),
            user_id=data.get("user_id", ""),
            is_stream=data.get("is_stream", "0") == "1",
            status=QueueStatus.PROCESSING,
            metadata={"stream_key": stream_key, "message_id": msg_id, "consumer": consumer_id or self._consumer_id},
        )
        return item

    async def ack(self, job_id: str, consumer_id: str) -> bool:
        return await self._ack_nack(job_id, consumer_id)

    async def nack(self, job_id: str, consumer_id: str, requeue: bool = True) -> bool:
        return await self._ack_nack(job_id, consumer_id)

    async def _ack_nack(self, job_id: str, consumer_id: str) -> bool:
        r = await self._get_redis()
        for stream_key in _STREAM_KEYS.values():
            try:
                entries = await r.xpending_range(
                    stream_key, self._consumer_group, min="-", max="+", count=10
                )
                for entry in entries:
                    entry_data = entry.get("data") or {}
                    if entry.get("entry_id") and entry.get("consumer") == (consumer_id or self._consumer_id):
                        await r.xack(stream_key, self._consumer_group, entry["entry_id"])
                        return True
            except Exception:
                continue
        return False

    async def get_job(self, job_id: str) -> Optional[QueueItem]:
        r = await self._get_redis()
        for stream_key in _STREAM_KEYS.values():
            try:
                entries = await r.xrevrange(stream_key, count=100)
                for msg_id, data in entries:
                    if data.get("job_id") == job_id:
                        return QueueItem(
                            job_id=job_id,
                            priority=RequestPriority(int(data.get("priority", RequestPriority.STANDARD.value))),
                            request_data=json.loads(data.get("request_data", "{}")),
                            user_id=data.get("user_id", ""),
                            is_stream=data.get("is_stream", "0") == "1",
                            status=QueueStatus.QUEUED,
                            metadata={"stream_key": stream_key, "message_id": msg_id},
                        )
            except Exception:
                continue
        return None

    async def cancel_job(self, job_id: str) -> bool:
        logger.warning("RedisStreamQueue: cancel_job needs external XLIMIT, not supported yet")
        return False

    async def queue_depth(self) -> dict[str, int]:
        r = await self._get_redis()
        depths = {}
        for priority, stream_key in _STREAM_KEYS.items():
            try:
                depths[priority.name.lower()] = await r.xlen(stream_key)
            except Exception:
                depths[priority.name.lower()] = -1
        return depths

    async def health(self) -> dict[str, Any]:
        try:
            r = await self._get_redis()
            await r.ping()
            depths = await self.queue_depth()
            return {
                "enabled": True,
                "type": "redis_streams",
                "group": self._consumer_group,
                "consumer": self._consumer_id,
                "depth": depths,
                "total_depth": sum(depths.values()),
            }
        except Exception as exc:
            return {
                "enabled": True,
                "type": "redis_streams",
                "healthy": False,
                "error": str(exc),
            }

    def __repr__(self) -> str:
        return f"RedisStreamQueue(group={self._consumer_group}, consumer={self._consumer_id})"
