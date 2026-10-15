"""Regression tests for durable job ownership in JobQueueService."""

from __future__ import annotations

import asyncio
import itertools
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

    async def scan(self, cursor: int, match: str = "*", count: int = 100):
        prefix, _, suffix = match.partition("*")
        keys = [
            k for k in self.hashes if k.startswith(prefix) and (not suffix or k.endswith(suffix))
        ]
        return 0, keys

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

    async def incr(self, key: str) -> int:
        current = int(self.values.get(key, "0") or "0") + 1
        self.values[key] = str(current)
        return current

    async def decr(self, key: str) -> int:
        current = int(self.values.get(key, "0") or "0") - 1
        if current <= 0:
            self.values.pop(key, None)
            return 0
        self.values[key] = str(current)
        return current

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


@pytest.mark.asyncio
async def test_queue_lifecycle_context_is_propagated_and_persisted(monkeypatch) -> None:
    """Queue timestamps reach the worker context and terminal metadata."""
    import app.services.job_queue as job_queue_module
    from app.context import queue_timing_var

    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    job_id = "job_timing"
    redis.hashes[f"job:{job_id}:meta"] = {
        "status": JobStatus.QUEUED.value,
        "is_stream": "0",
        "request_data": json.dumps({"message": "test"}),
        "created_at": "100.0",
        "admitted_at": "100.0",
        "correlation_id": "corr-test",
    }
    redis.lists["job_queue:pending"] = [job_id]

    # job_queue_module.time is the real stdlib `time` module (a single shared
    # object across the process), so patching its `.time` attribute here also
    # patches every other caller of time.time() in this process for the
    # duration of the test — including Python's own `logging` module, which
    # stamps `LogRecord.created` via time.time() when a LogRecord is built.
    # `_process_job`'s trailing `logger.info(...)` (app/services/job_queue.py)
    # therefore consumes one MORE clock value than the four real business
    # calls (claim, claimed_at, dispatch_started_at, published_at) — a 4-value
    # iterator raises StopIteration on that 5th, incidental call. Pad with a
    # repeating sentinel so the test only enforces the values it actually
    # asserts on, not every internal time.time() call anywhere in the process.
    clock = itertools.chain([101.0, 102.0, 103.0, 104.0], itertools.repeat(999.0))
    monkeypatch.setattr(job_queue_module.time, "time", lambda: next(clock))
    observed: dict = {}

    async def worker_factory(request_data: dict, is_stream: bool, received_job_id: str) -> dict:
        observed.update(queue_timing_var.get())
        assert received_job_id == job_id
        return {"ok": True}

    await service._process_job(job_id, worker_factory, worker_id=1)

    assert observed == {
        "admitted_at": 100.0,
        "claimed_at": 102.0,
        "dispatch_started_at": 103.0,
        "correlation_id": "corr-test",
    }
    metadata = redis.hashes[f"job:{job_id}:meta"]
    assert metadata["admitted_at"] == "100.0"
    assert metadata["claimed_at"] == "102.0"
    assert metadata["dispatch_started_at"] == "103.0"
    assert metadata["correlation_id"] == "corr-test"
    assert metadata["result_published_at"] == "104.0"
    assert metadata["status"] == JobStatus.COMPLETED.value
    assert queue_timing_var.get() == {}


@pytest.mark.asyncio
async def test_job_poll_projection_omits_internal_lifecycle_fields() -> None:
    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    job_id = "job_projection"
    redis.hashes[f"job:{job_id}:meta"] = {
        "status": JobStatus.COMPLETED.value,
        "created_at": "100.0",
        "started_at": "101.0",
        "completed_at": "104.0",
        "user_id": "anon:test",
        "admitted_at": "100.0",
        "claimed_at": "102.0",
        "dispatch_started_at": "103.0",
        "result_published_at": "104.0",
        "correlation_id": "corr-test",
        "trace_id": "trace-test",
    }
    redis.values[f"job:{job_id}:result"] = json.dumps({"response": "safe"})

    public_job = await service.get_job(job_id)

    assert public_job is not None
    assert public_job["status"] == JobStatus.COMPLETED.value
    assert public_job["result"] == {"response": "safe"}
    for internal_key in (
        "admitted_at",
        "claimed_at",
        "dispatch_started_at",
        "result_published_at",
        "correlation_id",
        "trace_id",
    ):
        assert internal_key not in public_job


@pytest.mark.asyncio
async def test_enqueue_degrades_to_in_memory_fallback_on_redis_outage() -> None:
    """Production-audit follow-up (2026-09-05 live chaos testing): a Redis
    outage during enqueue() used to raise redis.exceptions.ConnectionError
    uncaught, 500ing every /api/chat request. enqueue() must catch a Redis
    connection error, degrade to the in-memory fallback, and still complete
    the enqueue — and every subsequent call (get_job, cancel_job) must keep
    working against that same in-memory state."""
    import redis.exceptions

    class _DeadRedis:
        def pipeline(self):
            raise redis.exceptions.ConnectionError("Connection refused")

    service = JobQueueService("redis://unused")
    service._redis = _DeadRedis()

    job_id, queue_position = await service.enqueue({"message": "hello"}, "anon:test")

    assert job_id.startswith("job_")
    assert queue_position == 1
    assert service._degraded_to_memory is True

    job = await service.get_job(job_id)
    assert job is not None
    assert job["status"] == JobStatus.QUEUED.value
    assert job["user_id"] == "anon:test"

    cancelled = await service.cancel_job(job_id)
    assert cancelled is True
    job_after_cancel = await service.get_job(job_id)
    assert job_after_cancel["status"] == JobStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_stale_processing_job_is_marked_failed_not_left_hanging() -> None:
    """AMK-C-002 (2026-09-18 audit, live-reproduced 3x this session): a job
    whose worker was SIGKILLed mid-execution never reaches _process_job's
    finally block, so it stays status=PROCESSING forever with nothing to
    ever resolve it -- a client's GET /api/jobs/{id} poll hangs indefinitely.
    The sweep must find it (lease/dispatch window expired) and mark it
    FAILED so the poll resolves, without touching a job that's still legitimately
    in flight (dispatch_started_at recent) or already terminal.
    """
    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    service._lease_ttl = 300

    now = 10_000.0
    stuck_id = "job_stuck_from_crash"
    redis.hashes[f"job:{stuck_id}:meta"] = {
        "status": JobStatus.PROCESSING.value,
        "dispatch_started_at": str(now - 301),  # just past the lease TTL
    }
    redis.lists["job_queue:pending"] = [stuck_id]

    still_running_id = "job_still_running"
    redis.hashes[f"job:{still_running_id}:meta"] = {
        "status": JobStatus.PROCESSING.value,
        "dispatch_started_at": str(now - 5),  # well within the lease TTL
    }

    done_id = "job_already_done"
    redis.hashes[f"job:{done_id}:meta"] = {
        "status": JobStatus.COMPLETED.value,
        "dispatch_started_at": str(now - 10_000),
    }

    import app.services.job_queue as job_queue_module

    monkeypatch_time = now
    orig_time = job_queue_module.time.time
    job_queue_module.time.time = lambda: monkeypatch_time
    try:
        failed_count = await service._sweep_stale_processing_jobs()
    finally:
        job_queue_module.time.time = orig_time

    assert failed_count == 1
    assert redis.hashes[f"job:{stuck_id}:meta"]["status"] == JobStatus.FAILED.value
    assert stuck_id not in redis.lists["job_queue:pending"]
    assert redis.values[f"job:{stuck_id}:error"]  # a real message, not empty

    # Untouched: still-running job and already-terminal job.
    assert redis.hashes[f"job:{still_running_id}:meta"]["status"] == JobStatus.PROCESSING.value
    assert redis.hashes[f"job:{done_id}:meta"]["status"] == JobStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_enqueue_reraises_non_connection_errors_without_degrading() -> None:
    """A bug elsewhere (not a Redis outage) must not be silently swallowed
    into a false 'degraded to memory' state."""

    class _BuggyRedis:
        def pipeline(self):
            raise ValueError("not a connection problem")

    service = JobQueueService("redis://unused")
    service._redis = _BuggyRedis()

    with pytest.raises(ValueError):
        await service.enqueue({"message": "hello"}, "anon:test")
    assert service._degraded_to_memory is False


def _running_job(redis: _MemoryRedis, job_id: str, user_message: str = "hello") -> None:
    redis.hashes[f"job:{job_id}:meta"] = {
        "status": JobStatus.QUEUED.value,
        "is_stream": "0",
        "request_data": json.dumps({"chat_body": {"user_message": user_message}}),
    }


@pytest.mark.asyncio
async def test_exec_slot_bounds_concurrent_queued_execution(monkeypatch) -> None:
    """P1-1: with the shared cap exhausted, a second job backs off (stays
    QUEUED, factory never runs) instead of executing past the cap."""
    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    monkeypatch.setattr(service, "_exec_slot_cap", lambda: 1)
    _running_job(redis, "job_first")
    _running_job(redis, "job_second")

    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def worker_factory(request_data: dict, is_stream: bool, job_id: str) -> dict:
        calls.append(job_id)
        started.set()
        await release.wait()
        return {"ok": True}

    first = asyncio.create_task(service._process_job("job_first", worker_factory, worker_id=1))
    await asyncio.wait_for(started.wait(), timeout=5)
    await service._process_job("job_second", worker_factory, worker_id=2)

    assert calls == ["job_first"]
    assert redis.hashes["job:job_second:meta"]["status"] == JobStatus.QUEUED.value
    assert redis.values.get("chat:queue_exec_inflight") == "1"

    release.set()
    await first
    assert redis.hashes["job:job_first:meta"]["status"] == JobStatus.COMPLETED.value
    assert "chat:queue_exec_inflight" not in redis.values


@pytest.mark.asyncio
async def test_crisis_job_bypasses_exec_slot(monkeypatch) -> None:
    """RP-A2: a crisis job runs even with the cap exhausted and takes no slot."""
    import app.pipeline.stages.distress_stage as distress_mod

    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    monkeypatch.setattr(service, "_exec_slot_cap", lambda: 0)
    monkeypatch.setattr(
        distress_mod, "has_severe_crisis_keywords", lambda text: "crisis-now" in text
    )
    _running_job(redis, "job_crisis", user_message="this is crisis-now help")

    async def worker_factory(request_data: dict, is_stream: bool, job_id: str) -> dict:
        return {"ok": True}

    await service._process_job("job_crisis", worker_factory, worker_id=1)
    assert redis.hashes["job:job_crisis:meta"]["status"] == JobStatus.COMPLETED.value
    assert "chat:queue_exec_inflight" not in redis.values


@pytest.mark.asyncio
async def test_exec_slot_counter_error_runs_unbounded() -> None:
    """A broken counter degrades to the old behavior, never sheds the job."""

    class _BrokenCounter(_MemoryRedis):
        async def incr(self, key: str) -> int:
            raise ConnectionError("redis down")

    redis = _BrokenCounter()
    service = JobQueueService("redis://unused")
    service._redis = redis
    _running_job(redis, "job_degraded")

    async def worker_factory(request_data: dict, is_stream: bool, job_id: str) -> dict:
        return {"ok": True}

    await service._process_job("job_degraded", worker_factory, worker_id=1)
    assert redis.hashes["job:job_degraded:meta"]["status"] == JobStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_backoff_queue_full_marks_failed_with_error(monkeypatch) -> None:
    """Backoff CAS success path: local queue still full after retries marks
    the still-QUEUED job FAILED with a retryable error and drops it from
    the durable pending list."""
    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    monkeypatch.setattr(service, "_exec_slot_cap", lambda: 0)
    _running_job(redis, "job_backoff_failed")
    service._queue = asyncio.Queue(maxsize=1)
    service._queue.put_nowait("filler")

    async def worker_factory(request_data: dict, is_stream: bool, job_id: str) -> dict:
        raise AssertionError("backed-off job must never run")

    await service._process_job("job_backoff_failed", worker_factory, worker_id=1)

    assert redis.hashes["job:job_backoff_failed:meta"]["status"] == JobStatus.FAILED.value
    assert (
        redis.values["job:job_backoff_failed:error"]
        == "Server busy: local execution queue full (retryable)"
    )
    assert "job_backoff_failed" not in redis.lists["job_queue:pending"]


@pytest.mark.asyncio
async def test_backoff_preserves_concurrently_cancelled_job(monkeypatch) -> None:
    """Backoff CAS failure path: a cancel landing during the local-requeue
    retries must survive the queue-full branch — status stays CANCELLED and
    no error key is written."""
    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    monkeypatch.setattr(service, "_exec_slot_cap", lambda: 0)
    _running_job(redis, "job_backoff_cancel")
    service._queue = asyncio.Queue(maxsize=1)
    service._queue.put_nowait("filler")

    async def worker_factory(request_data: dict, is_stream: bool, job_id: str) -> dict:
        raise AssertionError("backed-off job must never run")

    task = asyncio.create_task(
        service._process_job("job_backoff_cancel", worker_factory, worker_id=1)
    )
    await asyncio.sleep(0.2)  # inside the 5x0.1s local-requeue retry loop
    assert await service.cancel_job("job_backoff_cancel") is True
    await task

    assert redis.hashes["job:job_backoff_cancel:meta"]["status"] == JobStatus.CANCELLED.value
    assert "job:job_backoff_cancel:error" not in redis.values
    assert "job_backoff_cancel" not in redis.lists["job_queue:pending"]


@pytest.mark.asyncio
async def test_exec_slot_expiry_set_only_on_key_creation(monkeypatch) -> None:
    """Review 2026-10-14: refreshing the TTL on every INCR lets steady
    traffic keep leaked (crashed-worker) slots alive indefinitely."""

    class _ExpiringRedis(_MemoryRedis):
        def __init__(self) -> None:
            super().__init__()
            self.expire_calls: list[str] = []

        async def expire(self, key: str, seconds: int) -> bool:
            self.expire_calls.append(key)
            return True

    redis = _ExpiringRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    monkeypatch.setattr(service, "_exec_slot_cap", lambda: 10)
    assert await service._acquire_exec_slot(redis) is True
    assert await service._acquire_exec_slot(redis) is True
    assert redis.expire_calls == ["chat:queue_exec_inflight"]
