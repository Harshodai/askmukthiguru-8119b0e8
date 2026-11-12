"""T7-02 / CQ-011: one event loop per Celery worker process.

Acceptance (audit doc 13, CQ-011): two consecutive tasks in one worker process
share a loop-bound async client. A loop-bound asyncio object stands in for the
shared Redis client: it works across tasks on the process loop and fails on a
per-call ``asyncio.run`` loop, which is the defect being removed.
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import threading
from pathlib import Path

import pytest

import tasks.worker_loop as wl
from tasks.worker_loop import run_in_worker_loop

BACKEND = Path(__file__).resolve().parents[1]


class _Interrupted(Exception):
    """Stands in for celery.exceptions.SoftTimeLimitExceeded."""


@pytest.fixture(autouse=True)
def _fresh_worker_loop(monkeypatch):
    monkeypatch.setattr(wl, "_LOOP", None)
    monkeypatch.setattr(wl, "_LOOP_PID", None)
    yield
    if wl._LOOP is not None and not wl._LOOP.is_closed():
        wl._LOOP.close()


def _shared_client_two_tasks(run) -> None:
    # A future is bound to the loop that created it, like a pooled async
    # client's connections: awaiting it from another loop raises.
    shared: dict[str, asyncio.Future] = {}

    async def task_one() -> None:
        shared["client"] = asyncio.get_running_loop().create_future()

    async def task_two() -> str:
        asyncio.get_running_loop().call_soon(shared["client"].set_result, "hello")
        return await shared["client"]

    run(task_one())
    assert run(task_two()) == "hello"


def test_two_tasks_share_a_loop_bound_client_on_the_worker_loop() -> None:
    _shared_client_two_tasks(run_in_worker_loop)


def test_per_call_asyncio_run_breaks_the_shared_client() -> None:
    """The defect the worker loop removes, so the test above can fail."""
    with pytest.raises(RuntimeError):
        _shared_client_two_tasks(asyncio.run)


def test_a_forked_child_never_reuses_the_parents_loop(monkeypatch) -> None:
    parent = wl.worker_loop()
    monkeypatch.setattr(os, "getpid", lambda: -1)
    assert wl.worker_loop() is not parent


@pytest.mark.skipif(not hasattr(signal, "pthread_kill"), reason="needs POSIX signals")
def test_soft_time_limit_cancels_the_task_before_the_next_one_runs() -> None:
    """Celery raises SoftTimeLimitExceeded from a signal handler in the main thread."""
    state = {"cancelled": False}

    async def slow_task() -> None:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    def _raise(_signum, _frame):
        raise _Interrupted

    previous = signal.signal(signal.SIGUSR1, _raise)
    timer = threading.Timer(
        0.1, signal.pthread_kill, (threading.main_thread().ident, signal.SIGUSR1)
    )
    try:
        timer.start()
        with pytest.raises(_Interrupted):
            run_in_worker_loop(slow_task())
    finally:
        timer.cancel()
        signal.signal(signal.SIGUSR1, previous)

    assert state["cancelled"], "the interrupted task must not resume in the next task"

    async def next_task() -> str:
        return "ran"

    assert run_in_worker_loop(next_task()) == "ran"


def test_called_from_async_code_raises_instead_of_nesting() -> None:
    async def outer() -> None:
        async def inner() -> None:
            return None

        loop = asyncio.get_running_loop()
        wl._LOOP, wl._LOOP_PID = loop, os.getpid()
        with pytest.raises(RuntimeError, match="already running"):
            run_in_worker_loop(inner())

    asyncio.run(outer())
    wl._LOOP = None


TASK_MODULES = (
    "tasks/memory_outbox_tasks.py",
    "tasks/layered_memory_tasks.py",
    "tasks/web_ingest_tasks.py",
    "tasks/okf_extract_tasks.py",
    "tasks/ingest_tasks.py",
    "tasks/contextual_reingest_task.py",
)


@pytest.mark.parametrize("module", TASK_MODULES)
def test_task_modules_never_open_a_per_call_loop(module: str) -> None:
    """Only the documented already-in-a-loop escape hatch may call asyncio.run."""
    source = (BACKEND / module).read_text(encoding="utf-8")
    direct = [
        line.strip()
        for line in source.splitlines()
        if re.search(r"\basyncio\.run\(", line) and "submit(asyncio.run" not in line
    ]
    assert not direct, f"{module}: per-call event loop {direct}"
    assert "new_event_loop()" not in source, f"{module}: private loop instead of worker_loop()"
