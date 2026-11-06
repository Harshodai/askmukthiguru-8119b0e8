"""T7-02: the first-person teaching lane runs as a coroutine on the request loop.

All offline (fake async LLM, mocked stores, no network, no spend):

1. ``aexecute`` returns exactly the recorded goldens of both characterization
   matrices (T7-01 stubs and T7-02 real LLM helpers): the conversion changed no
   outcome.
2. ``serve_first_person`` awaits the pipeline on the loop it was built on and
   never touches the sync entry point there; a duck-typed pipeline still goes
   through a worker thread.
3. A sync bridge called on its own loop thread raises instead of deadlocking.
4. Concurrency, the local stand-in for the staging c20 test (which needs live
   infrastructure): 20 concurrent requests, a 4-thread default executor and two
   0.5 s provider calls each. The async lane finishes in about one request's
   time; the pre-T7-02 shape (``to_thread(execute)``) needs five waves. Store
   calls sleep synchronously, so a sync call left on the loop would be logged
   as a slow callback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import MagicMock

import pytest

import services.first_person_pipeline as fpp
import tests.test_first_person_pipeline_golden as t701
import tests.test_first_person_pipeline_golden_llm as t702
from app.config import settings
from services.first_person_pipeline import serve_first_person
from tests.test_first_person_pipeline_golden import (  # noqa: F401 - autouse fixture import
    _deterministic_settings,
    _make_context,
    _make_span,
    _normalize,
    _RecordingPipeline,
    _store_summary,
)
from tests.test_first_person_pipeline_golden_llm import (  # noqa: F401 - autouse fixture import
    SPAN_TEXT_ONE,
    FakeLLM,
    _llm_settings,
)

pytestmark = [pytest.mark.answerability_real, pytest.mark.relevance_real]


def _restore_t701_stubs(monkeypatch) -> None:
    """The T7-01 goldens were recorded under the conftest stubs; reinstate them."""
    monkeypatch.setattr(
        fpp,
        "_answerability_check",
        lambda query, llm_service, request_loop=None, token_sink=None, **kw: True,
    )

    async def _stub_async(query, llm_service, token_sink=None, **kw):
        return True

    monkeypatch.setattr(fpp, "_async_answerability_check", _stub_async)

    def _stub_relevance(query, clips, llm_service, request_loop=None, token_sink=None, **kw):
        scores_out = kw.get("scores_out")
        if scores_out is not None:
            scores_out.extend([3] * len(clips))
        return 0

    monkeypatch.setattr(fpp, "_relevance_select", _stub_relevance)


@pytest.mark.parametrize("case", sorted(t701.SCENARIOS))
def test_aexecute_matches_t7_01_golden(case: str, monkeypatch) -> None:
    _restore_t701_stubs(monkeypatch)
    pipeline, execute_kwargs = t701.SCENARIOS[case](monkeypatch)
    kwargs = {"query_dense_vector": [1.0, 0.0], "cache_bypass": True, **execute_kwargs}
    calls = {"compound": 0}
    real_compound = pipeline._execute_compound

    def _compound(*args: Any, **kw: Any):
        calls["compound"] += 1
        return real_compound(*args, **kw)

    monkeypatch.setattr(pipeline, "_execute_compound", _compound)
    result = asyncio.run(pipeline.aexecute(**kwargs))
    observed = {
        "result": _normalize(result.to_dict()),
        "events": _normalize(pipeline.events),
        "store": _store_summary(pipeline),
        "compound_called": calls["compound"],
    }
    expected = json.loads((t701.GOLDEN_DIR / f"{case}.json").read_text(encoding="utf-8"))
    assert observed == expected, f"{case}: aexecute differs from the recorded golden"


@pytest.mark.parametrize("case", sorted(t702.SCENARIOS))
def test_aexecute_matches_t7_02_golden(case: str, monkeypatch) -> None:
    pipeline, kwargs = t702.SCENARIOS[case](monkeypatch)
    result = asyncio.run(
        pipeline.aexecute(query_dense_vector=[1.0, 0.0], cache_bypass=True, **kwargs)
    )
    observed = t702._observe(pipeline, result, case)
    expected = json.loads((t702.GOLDEN_DIR / f"{case}.json").read_text(encoding="utf-8"))
    assert observed == expected, f"{case}: aexecute differs from the recorded golden"


STORE_SLEEP_S = 0.05
LLM_DELAY_S = 0.5
CONCURRENCY = 20
EXECUTOR_THREADS = 4


def _loop_pipeline(loop: asyncio.AbstractEventLoop) -> _RecordingPipeline:
    """A harness pipeline built on ``loop``: gate + scorer calls, sync store sleeps."""
    context = _make_context(_make_span(SPAN_TEXT_ONE))

    def _retrieve(**_kw: Any) -> list[Any]:
        time.sleep(STORE_SLEEP_S)  # a sync Qdrant call: must never run on the loop
        return [context]

    context_store = MagicMock()
    context_store.retrieve.side_effect = _retrieve
    return _RecordingPipeline(
        store=MagicMock(),
        redis_client=MagicMock(get=MagicMock(return_value=None)),
        context_store=context_store,
        llm_service=FakeLLM(delay_s=LLM_DELAY_S),
        llm_loop=loop,
        calibration_profile={"threshold": 0.45, "score_kind": "cosine", "claims": "conformance"},
    )


@pytest.fixture
def harness_gates_on(monkeypatch):
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)


def _request() -> dict[str, Any]:
    return {
        "query": "What is the nature of suffering?",
        "query_dense_vector": [1.0, 0.0],
        "teacher_id": "krishnaji",
        "cache_bypass": True,
    }


def test_serve_awaits_on_the_build_loop_without_the_sync_entry(harness_gates_on) -> None:
    async def _run() -> Any:
        pipeline = _loop_pipeline(asyncio.get_running_loop())
        pipeline.execute = MagicMock(side_effect=AssertionError("sync entry used on the loop"))
        return await serve_first_person(pipeline, **_request())

    result = asyncio.run(_run())
    assert result.status in ("success", "weak_match")
    assert result.citations
    assert sorted(result.to_dict()) == sorted(result.to_dict())  # serialisable


def test_serve_uses_a_thread_for_a_duck_typed_pipeline() -> None:
    pipeline = MagicMock()
    pipeline.execute = MagicMock(return_value="served")
    assert asyncio.run(serve_first_person(pipeline, query="q")) == "served"
    pipeline.execute.assert_called_once_with(query="q")


def test_sync_bridge_on_its_own_loop_thread_raises_instead_of_deadlocking() -> None:
    async def _on_persistent_loop() -> None:
        fpp._stable_llm_loop(None)

    fut = asyncio.run_coroutine_threadsafe(_on_persistent_loop(), fpp._persistent_gate_loop())
    with pytest.raises(RuntimeError, match="own event loop thread"):
        fut.result(timeout=5)


def _timed_burst(use_async_lane: bool, caplog) -> tuple[float, list[str]]:
    async def _burst() -> float:
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=EXECUTOR_THREADS))
        loop.set_debug(True)
        loop.slow_callback_duration = 0.1
        pipeline = _loop_pipeline(loop)

        async def _one() -> Any:
            if use_async_lane:
                return await serve_first_person(pipeline, **_request())
            return await asyncio.to_thread(pipeline.execute, **_request())

        start = time.monotonic()
        results = await asyncio.gather(*(_one() for _ in range(CONCURRENCY)))
        elapsed = time.monotonic() - start
        assert all(r.status in ("success", "weak_match") for r in results)
        return elapsed

    with caplog.at_level(logging.WARNING, logger="asyncio"):
        elapsed = asyncio.run(_burst())
    slow = [r.getMessage() for r in caplog.records if "Executing" in r.getMessage()]
    return elapsed, slow


def test_c20_async_lane_does_not_starve_the_executor(harness_gates_on, caplog) -> None:
    one_request_s = 2 * LLM_DELAY_S + 2 * STORE_SLEEP_S
    async_s, slow = _timed_burst(True, caplog)
    caplog.clear()
    thread_s, _ = _timed_burst(False, caplog)
    print(
        f"\nc{CONCURRENCY}, {EXECUTOR_THREADS} executor threads, one request "
        f"~{one_request_s:.2f}s: async lane {async_s:.2f}s, to_thread(execute) {thread_s:.2f}s"
    )
    assert not slow, f"sync work blocked the loop: {slow[:3]}"
    # One wave plus scheduling slack, against five waves for the thread shape.
    assert async_s < 2.5 * one_request_s, async_s
    assert thread_s > (CONCURRENCY / EXECUTOR_THREADS - 1) * one_request_s, thread_s


def test_chat_bridge_stage_runs_the_pipeline_on_the_request_loop(harness_gates_on, monkeypatch):
    """The live chat route: the bridge stage awaits the pipeline built on its loop.

    The graph runs the ``first_person`` node with ``ainvoke`` on the request loop,
    and ``_pipeline`` captures that loop when the bridge first builds it. Here the
    pipeline is built on the stage's loop and its sync entry point raises, so a
    provider call proves the async branch ran.
    """
    import app.pipeline.stages.first_person_bridge as bridge_module
    from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
    from tests.test_first_person_bridge import _container, _ctx

    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)

    async def _run() -> _RecordingPipeline:
        pipeline = _loop_pipeline(asyncio.get_running_loop())
        pipeline._llm_service = FakeLLM()
        pipeline.execute = MagicMock(side_effect=AssertionError("sync entry used on the loop"))
        monkeypatch.setattr(bridge_module, "_fp_pipeline", lambda container: pipeline)
        await FirstPersonBridgeStage().run(
            _ctx(_container(), msg="What is the nature of suffering?")
        )
        return pipeline

    pipeline = asyncio.run(_run())
    assert pipeline.execute.call_count == 0
    assert "scorer" in pipeline._llm_service.calls, "the async harness lane did not run"
