"""P1-OPS-5: healthz liveness depth — grace period, heartbeat staleness, lifespan failure.

The Railway health probe hits /api/healthz which start_railway.py intercepts
BEFORE the real FastAPI app. These tests drive the ASGI wrapper directly with
an httpx ASGITransport so the wrapper's own heartbeat/lifespan logic is what
is under test (no FastAPI TestClient needed).
"""

import asyncio
import time
from contextlib import contextmanager

import httpx

import start_railway


@contextmanager
def _wrap_grace(_gr):
    old = start_railway._GRACE_SECONDS
    start_railway._GRACE_SECONDS = _gr
    try:
        yield
    finally:
        start_railway._GRACE_SECONDS = old


@contextmanager
def _wrap_heartbeat(stale_s):
    old = start_railway._HEARTBEAT_STALE_S
    start_railway._HEARTBEAT_STALE_S = stale_s
    try:
        yield
    finally:
        start_railway._HEARTBEAT_STALE_S = old


def _run_async(coro):
    return asyncio.get_event_loop_policy().get_event_loop().run_until_complete(coro)


async def _get_healthz() -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=start_railway.app), base_url="http://testserver"
    ) as client:
        return await client.get("/api/healthz")


def test_healthz_200_during_grace():
    """During the grace period healthz returns 200 even if lifespan never completed."""
    with _wrap_grace(180):
        old_done = start_railway._lifespan_startup_done
        start_railway._lifespan_startup_done = False
        old_start = start_railway._process_start
        start_railway._process_start = time.monotonic()
        try:
            resp = _run_async(_get_healthz())
            assert resp.status_code == 200
        finally:
            start_railway._lifespan_startup_done = old_done
            start_railway._process_start = old_start


def test_healthz_503_if_heartbeat_stale():
    """Post-grace, a stale heartbeat (> stale threshold) makes healthz return 503."""
    with _wrap_grace(-1), _wrap_heartbeat(30):
        old_done = start_railway._lifespan_startup_done
        old_beat = start_railway._last_heartbeat
        start_railway._lifespan_startup_done = True
        start_railway._last_heartbeat = time.monotonic() - 60
        try:
            resp = _run_async(_get_healthz())
            assert resp.status_code == 503
            assert b'"status":"starting"' in resp.content
        finally:
            start_railway._lifespan_startup_done = old_done
            start_railway._last_heartbeat = old_beat


def test_healthz_200_if_heartbeat_fresh():
    """Post-grace, a fresh heartbeat AND fresh executor canary keep healthz at 200."""
    with _wrap_grace(-1), _wrap_heartbeat(30):
        old_done = start_railway._lifespan_startup_done
        old_beat = start_railway._last_heartbeat
        old_canary = start_railway._last_executor_canary
        start_railway._lifespan_startup_done = True
        start_railway._last_heartbeat = time.monotonic()
        start_railway._last_executor_canary = time.monotonic()
        try:
            resp = _run_async(_get_healthz())
            assert resp.status_code == 200
            assert b'"status":"alive"' in resp.content
        finally:
            start_railway._lifespan_startup_done = old_done
            start_railway._last_heartbeat = old_beat
            start_railway._last_executor_canary = old_canary


def test_healthz_503_if_executor_canary_stale():
    """P2-OPS-1: a stale executor canary alone (heartbeat fresh, event loop fine)
    must still fail healthz -- this is the thread-pool-starvation case the
    heartbeat pump cannot see on its own (loop keeps running, to_thread queue
    never drains).
    """
    with _wrap_grace(-1), _wrap_heartbeat(30):
        old_done = start_railway._lifespan_startup_done
        old_beat = start_railway._last_heartbeat
        old_canary = start_railway._last_executor_canary
        start_railway._lifespan_startup_done = True
        start_railway._last_heartbeat = time.monotonic()  # loop is fine
        start_railway._last_executor_canary = time.monotonic() - 60  # executor starved
        try:
            resp = _run_async(_get_healthz())
            assert resp.status_code == 503
            assert b'"status":"starting"' in resp.content
        finally:
            start_railway._lifespan_startup_done = old_done
            start_railway._last_heartbeat = old_beat
            start_railway._last_executor_canary = old_canary


def test_executor_canary_pump_refreshes_timestamp():
    """The executor canary pump refreshes _last_executor_canary each interval
    by round-tripping a no-op through the same default executor
    asyncio.to_thread() callers (e.g. app/api/chat.py) share.
    """
    old_canary = start_railway._last_executor_canary
    old_interval = start_railway._HEARTBEAT_INTERVAL_S
    start_railway._HEARTBEAT_INTERVAL_S = 0.01

    async def _run():
        pump = asyncio.create_task(start_railway._run_executor_canary_pump())
        try:
            start_railway._last_executor_canary = 0.0
            await asyncio.sleep(0.2)
            assert start_railway._last_executor_canary > 0.0
        finally:
            pump.cancel()

    try:
        _run_async(_run())
    finally:
        start_railway._last_executor_canary = old_canary
        start_railway._HEARTBEAT_INTERVAL_S = old_interval


def test_executor_canary_pump_detects_starved_executor():
    """If the default executor never completes the no-op (all workers stuck),
    the canary must NOT silently mark itself fresh -- it should time out and
    leave the timestamp stale.
    """
    old_canary = start_railway._last_executor_canary
    old_interval = start_railway._HEARTBEAT_INTERVAL_S
    old_timeout = start_railway._EXECUTOR_CANARY_TIMEOUT_S
    start_railway._HEARTBEAT_INTERVAL_S = 0.01
    start_railway._EXECUTOR_CANARY_TIMEOUT_S = 0.05

    async def _hung_to_thread(_fn):
        # Simulates every worker being stuck on a blocking synchronous call.
        await asyncio.sleep(10)

    async def _run():
        original_to_thread = asyncio.to_thread
        asyncio.to_thread = _hung_to_thread
        try:
            pump = asyncio.create_task(start_railway._run_executor_canary_pump())
            try:
                start_railway._last_executor_canary = 0.0
                await asyncio.sleep(0.2)
                assert start_railway._last_executor_canary == 0.0, (
                    "canary must not mark itself fresh while the probe is still hung"
                )
            finally:
                pump.cancel()
        finally:
            asyncio.to_thread = original_to_thread

    try:
        _run_async(_run())
    finally:
        start_railway._last_executor_canary = old_canary
        start_railway._HEARTBEAT_INTERVAL_S = old_interval
        start_railway._EXECUTOR_CANARY_TIMEOUT_S = old_timeout


def test_healthz_503_if_lifespan_failed():
    """Post-grace, lifespan never completing (or failing) makes healthz return 503."""
    with _wrap_grace(-1):
        old_done = start_railway._lifespan_startup_done
        old_beat = start_railway._last_heartbeat
        start_railway._lifespan_startup_done = False
        start_railway._last_heartbeat = time.monotonic()
        try:
            resp = _run_async(_get_healthz())
            assert resp.status_code == 503
            assert b'"status":"starting"' in resp.content
        finally:
            start_railway._lifespan_startup_done = old_done
            start_railway._last_heartbeat = old_beat


def test_heartbeat_pump_refreshes_timestamp():
    """The lifespan heartbeat pump refreshes _last_heartbeat each interval."""
    old_beat = start_railway._last_heartbeat
    old_interval = start_railway._HEARTBEAT_INTERVAL_S
    old_done = start_railway._lifespan_startup_done
    start_railway._HEARTBEAT_INTERVAL_S = 0.01
    start_railway._lifespan_startup_done = True

    async def _run():
        pump = asyncio.create_task(start_railway._run_heartbeat_pump())
        try:
            start_railway._last_heartbeat = 0.0
            await asyncio.sleep(0.05)
            assert start_railway._last_heartbeat > 0.0
        finally:
            pump.cancel()

    try:
        _run_async(_run())
    finally:
        start_railway._last_heartbeat = old_beat
        start_railway._HEARTBEAT_INTERVAL_S = old_interval
        start_railway._lifespan_startup_done = old_done
