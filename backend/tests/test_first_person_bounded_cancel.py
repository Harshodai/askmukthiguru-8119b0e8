"""T7-02 review (SYS-003): cancelling a request cancels its in-flight LLM call.

``_bounded`` awaits a provider coroutine with a deadline. When the request
itself is cancelled (pipeline timeout in ``PipelineCoordinator``, the breath
route's ``wait_for``, a client disconnect), the provider call must be cancelled
too. Otherwise it keeps running as an orphan task: it spends money after the
seeker is gone and holds the budget reservation until the provider answers.
"""

from __future__ import annotations

import asyncio

import pytest

import services.first_person_pipeline as fpp


def test_cancelling_the_caller_cancels_the_bounded_llm_call() -> None:
    state = {"started": False, "cancelled": False, "finished": False}

    async def _provider_call() -> str:
        state["started"] = True
        try:
            await asyncio.sleep(5)
            state["finished"] = True
            return "YES"
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    async def _run() -> None:
        outer = asyncio.ensure_future(fpp._bounded(_provider_call(), 10.0))
        await asyncio.sleep(0.05)
        assert state["started"]
        outer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await outer
        # Let any orphan run a few ticks. Checked inside the loop: asyncio.run
        # cancels leftover tasks at shutdown, which would hide an orphan.
        await asyncio.sleep(0.05)
        assert state["cancelled"], "the in-flight provider call was left running after cancel"
        assert not state["finished"]

    asyncio.run(_run())


def test_bounded_deadline_still_cancels_without_waiting() -> None:
    """The deadline path is unchanged: TimeoutError at the budget, call cancelled."""
    state = {"cancelled": False}

    async def _slow() -> None:
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    async def _run() -> None:
        with pytest.raises(TimeoutError):
            await fpp._bounded(_slow(), 0.05)
        await asyncio.sleep(0.01)
        assert state["cancelled"]

    asyncio.run(_run())


def test_bounded_returns_the_result_and_reraises_errors() -> None:
    async def _ok() -> int:
        return 7

    async def _boom() -> None:
        raise ValueError("provider error")

    assert asyncio.run(fpp._bounded(_ok(), 1.0)) == 7
    with pytest.raises(ValueError):
        asyncio.run(fpp._bounded(_boom(), 1.0))
