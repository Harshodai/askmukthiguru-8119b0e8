from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from app.queue.request_queue import BaseRequestQueue, QueueItem, QueueStatus, RequestPriority

logger = logging.getLogger(__name__)


class InProcessQueue(BaseRequestQueue):
    """Default no-op queue: executes inline, bypasses queue entirely.

    This is the safe default used when USE_REQUEST_QUEUE=false.
    All requests pass through immediately without queuing.
    """

    def __init__(self) -> None:
        self._running = False

    async def enqueue(
        self,
        request_data: dict,
        user_id: str,
        priority: RequestPriority = RequestPriority.STANDARD,
        is_stream: bool = False,
    ) -> tuple[str, int]:
        job_id = f"inline_{uuid.uuid4().hex[:12]}"
        logger.debug(f"InProcessQueue: bypassing queue for {job_id}")
        return job_id, 0

    async def dequeue(
        self,
        consumer_id: str,
        priority: Optional[RequestPriority] = None,
        timeout: float = 1.0,
    ) -> Optional[QueueItem]:
        return None

    async def ack(self, job_id: str, consumer_id: str) -> bool:
        return True

    async def nack(self, job_id: str, consumer_id: str, requeue: bool = True) -> bool:
        return True

    async def get_job(self, job_id: str) -> Optional[QueueItem]:
        return None

    async def cancel_job(self, job_id: str) -> bool:
        return False

    async def queue_depth(self) -> dict[str, int]:
        return {"fast": 0, "standard": 0, "deep": 0}

    async def health(self) -> dict[str, Any]:
        return {"enabled": False, "type": "in_process", "depth": 0}

    async def start(self) -> None:
        self._running = True
        logger.info("InProcessQueue: started (no-op, requests bypass queue)")

    async def stop(self) -> None:
        self._running = False
        logger.info("InProcessQueue: stopped")

    def __repr__(self) -> str:
        return "InProcessQueue(no-op)"
