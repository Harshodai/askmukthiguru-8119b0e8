from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Any, Optional


class RequestPriority(enum.IntEnum):
    FAST = 0
    STANDARD = 1
    DEEP = 2


class QueueStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueueItem:
    job_id: str
    priority: RequestPriority
    request_data: dict
    user_id: str
    status: QueueStatus = QueueStatus.QUEUED
    is_stream: bool = False
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class BaseRequestQueue(abc.ABC):
    @abc.abstractmethod
    async def enqueue(
        self,
        request_data: dict,
        user_id: str,
        priority: RequestPriority = RequestPriority.STANDARD,
        is_stream: bool = False,
    ) -> tuple[str, int]:
        ...

    @abc.abstractmethod
    async def dequeue(
        self,
        consumer_id: str,
        priority: Optional[RequestPriority] = None,
        timeout: float = 1.0,
    ) -> Optional[QueueItem]:
        ...

    @abc.abstractmethod
    async def ack(self, job_id: str, consumer_id: str) -> bool:
        ...

    @abc.abstractmethod
    async def nack(self, job_id: str, consumer_id: str, requeue: bool = True) -> bool:
        ...

    @abc.abstractmethod
    async def get_job(self, job_id: str) -> Optional[QueueItem]:
        ...

    @abc.abstractmethod
    async def cancel_job(self, job_id: str) -> bool:
        ...

    @abc.abstractmethod
    async def queue_depth(self) -> dict[str, int]:
        ...

    @abc.abstractmethod
    async def health(self) -> dict[str, Any]:
        ...

    @abc.abstractmethod
    async def start(self) -> None:
        ...

    @abc.abstractmethod
    async def stop(self) -> None:
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
