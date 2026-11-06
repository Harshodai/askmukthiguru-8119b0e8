"""T7-02 review (SYS-003): the sync ``execute`` entry point has an outer bound.

``execute`` schedules ``aexecute`` on the stable LLM loop and blocks. Every
LLM core bounds its own provider call, but nothing bounded the whole run: a
wedged store read or loop would hold the caller's thread forever (the
``to_thread(execute)`` fallback of ``serve_first_person`` and the breath
route's ``wait_for`` cannot cancel a thread). The bound cancels the run.
"""

from __future__ import annotations

import asyncio
import time

import pytest

import services.first_person_pipeline as fpp


def test_execute_times_out_and_cancels_a_wedged_run(monkeypatch) -> None:
    state = {"cancelled": False}
    pipeline = fpp.FirstPersonPipeline.__new__(fpp.FirstPersonPipeline)
    pipeline._llm_loop = None

    async def _wedged(self, **_kwargs):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    monkeypatch.setattr(fpp.FirstPersonPipeline, "aexecute", _wedged)
    monkeypatch.setattr(fpp, "_EXECUTE_TIMEOUT_S", 0.2, raising=False)

    start = time.monotonic()
    with pytest.raises(TimeoutError):
        pipeline.execute(query="q", query_dense_vector=[0.0])
    assert time.monotonic() - start < 5.0
    deadline = time.monotonic() + 2.0
    while not state["cancelled"] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert state["cancelled"], "the wedged run kept going after the caller gave up"
