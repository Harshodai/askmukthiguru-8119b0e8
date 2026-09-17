"""Regression tests for the 2026-09-15 incident: /api/health hung for minutes
under concurrent load with zero response, and the container sat "unhealthy"
for hours because nothing else caught it.

Two independent bugs, two independent tests:

1. `_check_neo4j` used to be a bare `async def` wrapping fully synchronous
   driver calls with no `await` inside -- `asyncio.wait_for(..., timeout=3.0)`
   around it was a no-op because there was no yield point for cancellation to
   land on. A slow/hung driver call froze the single event-loop thread, not
   just that one check. `test_check_neo4j_does_not_block_event_loop` proves a
   slow driver call no longer blocks other coroutines on the same loop.

2. `health_endpoint` had no OUTER bound: it composed several per-check
   timeouts serially, so worst case was their SUM, and if a check bypassed
   its own timeout (as in bug 1), there was no ceiling at all.
   `test_health_endpoint_returns_within_hard_bound_even_if_a_check_hangs`
   proves the route always answers (503) by `_HEALTH_HARD_BOUND_SECONDS`
   regardless of what a downstream check does.
"""

from __future__ import annotations

import asyncio
import time

import pytest

import app.api.health as health_module


def test_check_neo4j_does_not_block_event_loop():
    """A slow driver call must not freeze the event loop -- only the worker
    thread it runs on."""

    class _SlowSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def run(self, *_a, **_kw):
            time.sleep(0.3)  # simulates a slow/hung Memgraph/Neo4j call

    class _SlowDriver:
        def session(self):
            return _SlowSession()

    class _Container:
        neo4j_driver = _SlowDriver()

    async def _drive():
        progress = {"ticks": 0}

        async def _ticker():
            while True:
                await asyncio.sleep(0.01)
                progress["ticks"] += 1

        ticker = asyncio.create_task(_ticker())
        ok = await health_module._check_neo4j(_Container())
        ticker.cancel()
        return ok, progress["ticks"]

    ok, ticks = asyncio.run(_drive())
    assert ok is True
    # The 0.3s driver call ran on _HEALTH_EXECUTOR, so the loop kept ticking
    # (~30 ticks at 10ms) instead of freezing for the duration of the call.
    assert ticks > 5, f"event loop only ticked {ticks} times -- looks blocked"


def test_health_endpoint_returns_within_hard_bound_even_if_a_check_hangs(monkeypatch):
    """The route must answer within the hard bound even when the check
    sequence itself never returns."""
    monkeypatch.setattr(health_module, "_HEALTH_HARD_BOUND_SECONDS", 0.2)

    async def _hangs_forever(_container):
        await asyncio.sleep(999)

    monkeypatch.setattr(health_module, "_build_health_response", _hangs_forever)

    async def _drive():
        start = time.monotonic()
        resp = await health_module.health_endpoint(container=object())
        elapsed = time.monotonic() - start
        return resp, elapsed

    resp, elapsed = asyncio.run(_drive())
    assert resp.status_code == 503
    assert elapsed < 2.0, f"took {elapsed}s, expected to bail out near the 0.2s hard bound"


if __name__ == "__main__":
    test_check_neo4j_does_not_block_event_loop()
    test_health_endpoint_returns_within_hard_bound_even_if_a_check_hangs(pytest.MonkeyPatch())
    print("OK")
