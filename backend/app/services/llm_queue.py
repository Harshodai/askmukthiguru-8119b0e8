from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LLMPriority(Enum):
    CLASSIFY = 0
    GENERATE = 1
    VERIFY = 2
    BACKGROUND = 3


class LLMQueueService:
    def __init__(self, max_concurrent: int = 5, queue_maxsize: int = 50):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent
        self._queue = asyncio.PriorityQueue(maxsize=queue_maxsize)
        self._total_enqueued = 0
        self._total_completed = 0
        self._total_failed = 0
        self._wait_times: list[float] = []
        self._max_wait_time_log = 100
        self._running = False
        self._workers: list[asyncio.Task] = []

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def avg_wait_time(self) -> float:
        if not self._wait_times:
            return 0.0
        return sum(self._wait_times) / len(self._wait_times)

    @property
    def total_enqueued(self) -> int:
        return self._total_enqueued

    @property
    def total_completed(self) -> int:
        return self._total_completed

    @property
    def total_failed(self) -> int:
        return self._total_failed

    @property
    def running(self) -> bool:
        return self._running

    async def start(self):
        self._running = True
        logger.info(
            "LLMQueueService started (max_concurrent=%d)",
            self._max_concurrent,
        )

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("LLMQueueService stopped")

    async def execute(self, priority: LLMPriority, provider_call, *args, **kwargs) -> Any:
        if not self._running:
            return await provider_call(*args, **kwargs)

        self._total_enqueued += 1
        wait_start = time.monotonic()

        async with self._semaphore:
            wait_time = time.monotonic() - wait_start
            self._wait_times.append(wait_time)
            if len(self._wait_times) > self._max_wait_time_log:
                self._wait_times.pop(0)

            try:
                result = await provider_call(*args, **kwargs)
                self._total_completed += 1
                return result
            except Exception:
                self._total_failed += 1
                raise

    async def execute_stream(self, priority: LLMPriority, stream_factory, *args, **kwargs):
        """Streaming twin of execute(): holds the semaphore for the FULL stream
        lifetime so an in-flight stream counts against max_concurrent.

        Without this, generate_stream bypassed the queue and every concurrent
        streaming request opened an unbounded provider connection — a root
        cause of memory spikes under load. Metrics (enqueue/wait/complete/fail)
        are updated consistently with execute(). `priority` is accepted for
        parity with execute() (which likewise does not use it for ordering —
        the semaphore is the sole concurrency gate today).
        """
        if not self._running:
            async for chunk in stream_factory(*args, **kwargs):
                yield chunk
            return

        self._total_enqueued += 1
        wait_start = time.monotonic()

        async with self._semaphore:
            wait_time = time.monotonic() - wait_start
            self._wait_times.append(wait_time)
            if len(self._wait_times) > self._max_wait_time_log:
                self._wait_times.pop(0)

            try:
                async for chunk in stream_factory(*args, **kwargs):
                    yield chunk
                self._total_completed += 1
            except Exception:
                self._total_failed += 1
                raise

    def get_stats(self) -> dict:
        return {
            "max_concurrent": self._max_concurrent,
            "queue_depth": self.queue_depth,
            "avg_wait_time_ms": round(self.avg_wait_time * 1000, 2),
            "total_enqueued": self._total_enqueued,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "running": self._running,
        }


class QueuedLLMProvider:
    def __init__(self, provider, queue_service: LLMQueueService):
        self._provider = provider
        self._queue = queue_service

    async def generate(self, *args, **kwargs):
        priority = kwargs.pop("priority", LLMPriority.GENERATE)
        return await self._queue.execute(priority, self._provider.generate, *args, **kwargs)

    async def generate_stream(self, *args, **kwargs):
        priority = kwargs.pop("priority", LLMPriority.GENERATE)
        async for chunk in self._queue.execute_stream(
            priority, self._provider.generate_stream, *args, **kwargs
        ):
            yield chunk

    async def classify(self, **kwargs):
        return await self._queue.execute(LLMPriority.CLASSIFY, self._provider.classify, **kwargs)

    async def classify_intent_and_complexity(self, **kwargs):
        return await self._queue.execute(LLMPriority.CLASSIFY, self._provider.classify_intent_and_complexity, **kwargs)

    async def classify_distress_structured(self, message: str):
        return await self._queue.execute(LLMPriority.CLASSIFY, self._provider.classify_distress_structured, message)

    async def grade_relevance(self, **kwargs):
        return await self._queue.execute(LLMPriority.VERIFY, self._provider.grade_relevance, **kwargs)

    async def check_faithfulness(self, **kwargs):
        return await self._queue.execute(LLMPriority.VERIFY, self._provider.check_faithfulness, **kwargs)

    async def verify_answer(self, **kwargs):
        return await self._queue.execute(LLMPriority.VERIFY, self._provider.verify_answer, **kwargs)

    async def decompose_query(self, **kwargs):
        return await self._queue.execute(LLMPriority.VERIFY, self._provider.decompose_query, **kwargs)

    async def rewrite_query(self, **kwargs):
        return await self._queue.execute(LLMPriority.VERIFY, self._provider.rewrite_query, **kwargs)

    async def generate_hyde(self, **kwargs):
        return await self._queue.execute(LLMPriority.GENERATE, self._provider.generate_hyde, **kwargs)

    async def compress_context(self, **kwargs):
        return await self._queue.execute(LLMPriority.BACKGROUND, self._provider.compress_context, **kwargs)

    async def translate_text(self, **kwargs):
        return await self._queue.execute(LLMPriority.BACKGROUND, self._provider.translate_text, **kwargs)

    async def health_check(self):
        return await self._provider.health_check()

    def __getattr__(self, name):
        return getattr(self._provider, name)
