"""S1 guard: Redis pool sized for 20 pilot + headroom, exhaustion degrades.

Root cause (R1): redis-py 7.x raises MaxConnectionsError (a
redis.exceptions.ConnectionError SUBCLASS) on pool exhaustion. The old
substring name-match ("ConnectionError" in type name) missed it, so
enqueue() re-raised at job_queue.py:378 and /api/chat 500'd above ~5
concurrent against max_connections=5 caps. isinstance() catches it and
every future subclass.
"""
from __future__ import annotations

import asyncio
import pathlib
import re

import pytest


def _pool_cap(relative_path: str) -> int:
    src = (pathlib.Path(__file__).parent.parent / relative_path).read_text()
    matches = re.findall(r"max_connections=(\d+)", src)
    assert matches, f"no max_connections cap found in {relative_path}"
    return max(int(m) for m in matches)


def test_hot_path_pools_sized_for_20_pilot_plus_headroom() -> None:
    """Both hot-path Redis clients must exceed the 20-pilot target."""
    assert _pool_cap("services/cache/redis_adapter.py") >= 32
    assert _pool_cap("app/services/job_queue.py") >= 32


def test_is_connection_error_catches_pool_exhaustion() -> None:
    """MaxConnectionsError must take the graceful-degradation path."""
    import redis.exceptions

    from app.services.job_queue import JobQueueService

    assert JobQueueService._is_connection_error(
        redis.exceptions.MaxConnectionsError("Too many connections")
    )
    assert JobQueueService._is_connection_error(
        redis.exceptions.ConnectionError("Connection refused")
    )
    assert JobQueueService._is_connection_error(
        redis.exceptions.TimeoutError("Operation timed out")
    )
    assert JobQueueService._is_connection_error(TimeoutError("builtin timeout"))
    # Non-connectivity bugs must still raise, never silently degrade.
    assert not JobQueueService._is_connection_error(ValueError("not a connection problem"))
    assert not JobQueueService._is_connection_error(
        redis.exceptions.ResponseError("ERR unknown command")
    )


@pytest.mark.asyncio
async def test_max_concurrent_chat_plus_one_concurrent_enqueues_zero_5xx() -> None:
    """max_concurrent_chat + 1 concurrent enqueues under pool exhaustion.

    Every enqueue must succeed (zero 5xx proxy: no exception escapes) and
    the service must have taken the in-memory degradation path.
    """
    import redis.exceptions

    from app.config import settings
    from app.services.job_queue import JobQueueService, JobStatus

    class _ExhaustedRedis:
        """Pool-exhausted double: every write attempt raises MaxConnectionsError."""

        def pipeline(self):
            raise redis.exceptions.MaxConnectionsError("Too many connections")

    service = JobQueueService("redis://unused")
    service._redis = _ExhaustedRedis()

    n = settings.max_concurrent_chat + 1
    results = await asyncio.gather(
        *(service.enqueue({"message": f"hello-{i}"}, "anon:test") for i in range(n))
    )

    assert len(results) == n  # zero 5xx: gather raised nothing
    assert service._degraded_to_memory is True
    for job_id, queue_position in results:
        assert job_id.startswith("job_")
        assert queue_position >= 1
        job = await service.get_job(job_id)
        assert job is not None
        assert job["status"] == JobStatus.QUEUED.value


if __name__ == "__main__":
    test_hot_path_pools_sized_for_20_pilot_plus_headroom()
    test_is_connection_error_catches_pool_exhaustion()
    asyncio.run(test_max_concurrent_chat_plus_one_concurrent_enqueues_zero_5xx())
    print("self-check OK")
