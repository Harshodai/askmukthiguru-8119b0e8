"""One asyncio event loop per Celery worker process (T7-02, CQ-011).

``asyncio.run`` creates and closes a loop per call. Async clients that are
shared across calls (Redis, pooled HTTP, the provider RPM limiter and budget
ledger) bind to the first loop they run on, so every later call on a fresh loop
fails with "Event loop is closed" — the serve path hit exactly this on
2026-10-11 (invariant 22). Tasks call ``run_in_worker_loop(coro)`` instead.

The loop is created lazily and keyed on the process id, so a loop inherited
through a prefork ``fork()`` is never reused in the child. Celery's default
prefork pool runs one task at a time per process on the main thread; a
threads/eventlet pool would call this from several threads, which raises.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Coroutine
from typing import Any, Optional, TypeVar

T = TypeVar("T")

_LOOP: Optional[asyncio.AbstractEventLoop] = None
_LOOP_PID: Optional[int] = None
_LOCK = threading.Lock()


def worker_loop() -> asyncio.AbstractEventLoop:
    """This process's long-lived task loop (re-created after a fork or a close)."""
    global _LOOP, _LOOP_PID
    with _LOCK:
        if _LOOP is None or _LOOP.is_closed() or _LOOP_PID != os.getpid():
            _LOOP = asyncio.new_event_loop()
            _LOOP_PID = os.getpid()
        return _LOOP


def run_in_worker_loop(coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` to completion on the process loop.

    If the run is interrupted (Celery's ``SoftTimeLimitExceeded`` raised in the
    main thread, or any other exception escaping the loop), the task is
    cancelled and drained before the exception propagates, so it can never
    resume inside the next task that runs on this loop.
    """
    loop = worker_loop()
    if loop.is_running():
        coro.close()
        raise RuntimeError(
            "worker loop already running: run_in_worker_loop needs the prefork pool "
            "(one task per process) and must not be called from async code"
        )
    asyncio.set_event_loop(loop)
    task = loop.create_task(coro)
    try:
        return loop.run_until_complete(task)
    except BaseException:
        if not task.done():
            task.cancel()
            loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        raise


if __name__ == "__main__":

    async def _loop_id() -> int:
        return id(asyncio.get_running_loop())

    first = run_in_worker_loop(_loop_id())
    assert run_in_worker_loop(_loop_id()) == first, "one loop per process"
    print("worker_loop self-check ok")
