"""Regression tests for durable job ownership in JobQueueService."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.services.job_queue import _CANCEL_LUA, _CLAIM_LUA, JobQueueService, JobStatus


class _MemoryRedis:
    """Minimal async Redis double for job ownership tests."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def hset(self, key: str, *args, mapping: dict[str, str] | None = None) -> int:
        target = self.hashes.setdefault(key, {})
        if mapping is not None:
            target.update({name: str(value) for name, value in mapping.items()})
        elif len(args) == 2:
            target[str(args[0])] = str(args[1])
        else:
            raise AssertionError("Unexpected hset arguments")
        return 1

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        return 1 if self.values.pop(key, None) is not None else 0

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def lrem(self, key: str, count: int, value: str) -> int:
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

    async def eval(self, script: str, num_keys: int, *args) -> int:
        """Simulate the two CAS scripts: atomic status guard + side effects."""
        keys = list(args[:num_keys])
        argv = list(args[num_keys:])
        if script is _CANCEL_LUA:
            meta_key, pending_key = keys
            expected, new_status, job_id = argv
            if self.hashes.get(meta_key, {}).get("status") != expected:
                return 0
            self.hashes[meta_key]["status"] = new_status
            await self.lrem(pending_key, 1, job_id)
            return 1
        if script is _CLAIM_LUA:
            meta_key = keys[0]
            expected, new_status, started_at = argv
            if self.hashes.get(meta_key, {}).get("status") != expected:
                return 0
            self.hashes.setdefault(meta_key, {})["status"] = new_status
            self.hashes[meta_key]["started_at"] = started_at
            return 1
        raise AssertionError(f"Unknown Lua script in test double: {script[:60]!r}")


@pytest.mark.asyncio
async def test_lease_allows_only_one_concurrent_worker_for_the_same_job() -> None:
    """A second worker must skip a job while the first worker owns its Redis lease."""
    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    job_id = "job_concurrent"
    redis.hashes[f"job:{job_id}:meta"] = {
        "status": JobStatus.QUEUED.value,
        "is_stream": "0",
        "request_data": json.dumps({"message": "test"}),
    }
    redis.lists["job_queue:pending"] = [job_id]

    started = asyncio.Event()
    release = asyncio.Event()
    call_count = 0

    async def worker_factory(request_data: dict, is_stream: bool, received_job_id: str) -> dict:
        nonlocal call_count
        call_count += 1
        assert request_data == {"message": "test"}
        assert is_stream is False
        assert received_job_id == job_id
        started.set()
        await release.wait()
        return {"ok": True}

    first = asyncio.create_task(service._process_job(job_id, worker_factory, worker_id=1))
    await asyncio.wait_for(started.wait(), timeout=1)
    await service._process_job(job_id, worker_factory, worker_id=2)
    assert call_count == 1

    release.set()
    await first
    assert call_count == 1
    assert redis.hashes[f"job:{job_id}:meta"]["status"] == JobStatus.COMPLETED.value
    assert f"job:{job_id}:lease" not in redis.values
    assert redis.lists["job_queue:pending"] == []


def _queued_job(redis: _MemoryRedis, job_id: str) -> None:
    redis.hashes[f"job:{job_id}:meta"] = {
        "status": JobStatus.QUEUED.value,
        "is_stream": "0",
        "request_data": json.dumps({"message": "test"}),
    }
    redis.lists["job_queue:pending"] = [job_id]


@pytest.mark.asyncio
async def test_cancel_wins_race_before_claim() -> None:
    """A cancel that lands before the worker claim wins atomically: the job is
    marked CANCELLED, removed from pending, and the worker must not run it."""
    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    job_id = "job_cancel_win"
    _queued_job(redis, job_id)

    assert await service.cancel_job(job_id) is True
    assert redis.hashes[f"job:{job_id}:meta"]["status"] == JobStatus.CANCELLED.value
    assert redis.lists["job_queue:pending"] == []

    call_count = 0

    async def worker_factory(request_data: dict, is_stream: bool, received_job_id: str) -> dict:
        nonlocal call_count
        call_count += 1
        return {"ok": True}

    await service._process_job(job_id, worker_factory, worker_id=1)
    assert call_count == 0
    assert redis.hashes[f"job:{job_id}:meta"]["status"] == JobStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_cancel_after_claim_is_atomic_noop() -> None:
    """A cancel racing a worker that already claimed must lose cleanly: it
    returns False and never overwrites the PROCESSING status."""
    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    job_id = "job_cancel_lose"
    _queued_job(redis, job_id)

    claimed = await service._redis.eval(
        _CLAIM_LUA,
        1,
        f"job:{job_id}:meta",
        JobStatus.QUEUED.value,
        JobStatus.PROCESSING.value,
        "1234.5",
    )
    assert claimed == 1

    assert await service.cancel_job(job_id) is False
    assert redis.hashes[f"job:{job_id}:meta"]["status"] == JobStatus.PROCESSING.value
    assert redis.lists["job_queue:pending"] == [job_id]
