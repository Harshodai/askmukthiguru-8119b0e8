"""Startup retrieval canary: success, timeout and failure paths with fakes (no network, no models)."""

from __future__ import annotations

import asyncio
import logging
import threading
from types import SimpleNamespace

import pytest

from app import fp_startup_canary as canary
from app.config import settings

LOGGER = "app.fp_startup_canary"


class _Embedding:
    def __init__(self, delay_s: float = 0.0, dense_len: int | None = None) -> None:
        self.delay_s = delay_s
        self.dense_len = dense_len if dense_len is not None else settings.embedding_dimension

    async def encode_single_full_async(self, text: str) -> dict:
        await asyncio.sleep(self.delay_s)
        return {"dense": [0.1] * self.dense_len, "sparse": {"7": 0.5, "9": 0.25}}


class _Store:
    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.threads: dict[str, int] = {}
        self.calls: list[str] = []

    def retrieve(self, **kwargs):
        self.calls.append("retrieve")
        self.threads["retrieve"] = threading.get_ident()
        if self.fail is not None:
            raise self.fail
        span = SimpleNamespace(source_span_id="s1")
        return [SimpleNamespace(spans=(span,))]

    def dense_vectors_for_spans(self, span_ids):
        self.calls.append("dense_vectors_for_spans")
        return {sid: [0.0] for sid in span_ids}


class _Pipeline:
    def __init__(self, store: _Store) -> None:
        self.store = store

    def _get_context_store(self):
        return self.store

    def _get_context_harness(self):
        return object()

    def _expand_context_candidates(self, contexts, **kwargs):
        self.store.calls.append("expand")
        self.store.threads["expand"] = threading.get_ident()
        return list(contexts)


@pytest.fixture
def wired(monkeypatch):
    """Patch the route's pipeline factory and turn graph sizing off (needs Memgraph)."""
    import app.pipeline.stages.first_person_bridge as bridge

    store = _Store()
    monkeypatch.setattr(bridge, "_fp_pipeline", lambda container: _Pipeline(store))
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_enabled", False)
    return store


@pytest.fixture
def applicable(monkeypatch):
    """Canary-applicable flags, and startup state restored after the test."""
    import app.dependencies as deps

    for key, value in {
        "startup_retrieval_canary_enabled": True,
        "first_person_route_enabled": True,
        "first_person_context_harness_enabled": True,
        "first_person_context_collection": "first_person_test",
    }.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(deps, "startup_complete", True)
    monkeypatch.setattr(deps, "startup_error", None)
    return deps


def _run(container, **kw):
    return asyncio.run(canary.run_first_person_retrieval_canary(container, **kw))


def test_success_warms_each_component_off_the_event_loop(wired, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    main_thread = threading.get_ident()

    steps = _run(SimpleNamespace(embedding=_Embedding()))

    assert [s.ok for s in steps] == [True] * 5
    assert [s.name.split("(")[0] for s in steps] == [
        "embed",
        "pipeline+context_store+harness",
        "context_store.retrieve",
        "expand_context_candidates",
        "context_store.dense_vectors_for_spans",
    ]
    assert wired.calls == ["retrieve", "expand", "dense_vectors_for_spans"]
    # blocking store work must not run on the event-loop (here: the asyncio.run) thread
    assert wired.threads["retrieve"] != main_thread
    assert wired.threads["expand"] != main_thread
    # one INFO line per warmed component, each with a duration
    warmed = [r.getMessage() for r in caplog.records if "warmed in" in r.getMessage()]
    assert len(warmed) == 5 and all(m.endswith("ms") for m in warmed)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_component_failure_is_a_loud_warning_and_never_raises(wired, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    wired.fail = RuntimeError("qdrant unreachable")

    steps = _run(SimpleNamespace(embedding=_Embedding()))

    assert steps[-1].name.startswith("context_store.retrieve") and not steps[-1].ok
    assert "qdrant unreachable" in steps[-1].detail
    assert wired.calls == ["retrieve"]  # nothing downstream of the failed step ran
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "FAILED" in warnings[0].getMessage()
    assert "context_store.retrieve" in warnings[0].getMessage()


def test_dense_contract_violation_stops_before_retrieval(wired, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)

    steps = _run(SimpleNamespace(embedding=_Embedding(dense_len=3)))

    assert len(steps) == 1 and not steps[0].ok
    assert wired.calls == []
    assert any("FAILED" in r.getMessage() for r in caplog.records)


def test_open_embedding_circuit_is_a_warning_not_a_startup_crash(wired, caplog):
    from services.circuit_breaker import CircuitOpenException

    class _OpenCircuit:
        async def encode_single_full_async(self, text):
            raise CircuitOpenException(provider="embedding", message="open")

    caplog.set_level(logging.INFO, logger=LOGGER)

    steps = _run(SimpleNamespace(embedding=_OpenCircuit()))

    assert len(steps) == 1 and not steps[0].ok
    assert any("FAILED" in r.getMessage() for r in caplog.records)


def test_timeout_warns_with_completed_steps_and_never_raises(wired, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)

    steps = _run(SimpleNamespace(embedding=_Embedding(delay_s=5)), timeout_s=0.05)

    assert steps == []
    timed_out = [r.getMessage() for r in caplog.records if "TIMED OUT" in r.getMessage()]
    assert len(timed_out) == 1 and "completed: none" in timed_out[0]
    assert wired.calls == []


def test_missing_context_store_is_reported_not_raised(monkeypatch, caplog):
    import app.pipeline.stages.first_person_bridge as bridge

    caplog.set_level(logging.INFO, logger=LOGGER)
    store = _Store()
    pipeline = _Pipeline(store)
    pipeline._get_context_store = lambda: None
    monkeypatch.setattr(bridge, "_fp_pipeline", lambda container: pipeline)

    steps = _run(SimpleNamespace(embedding=_Embedding()))

    assert steps[-1].name == "pipeline+context_store+harness" and not steps[-1].ok
    assert any("no context store configured" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, True),
        ({"startup_retrieval_canary_enabled": False}, False),
        ({"first_person_route_enabled": False}, False),
        ({"first_person_context_harness_enabled": False}, False),
        ({"first_person_context_collection": ""}, False),
    ],
)
def test_canary_applicable_follows_flags(monkeypatch, overrides, expected):
    base = {
        "startup_retrieval_canary_enabled": True,
        "first_person_route_enabled": True,
        "first_person_context_harness_enabled": True,
        "first_person_context_collection": "first_person_test",
    }
    for key, value in {**base, **overrides}.items():
        monkeypatch.setattr(settings, key, value)
    assert canary.canary_applicable() is expected


def test_default_is_on():
    assert type(settings).model_fields["startup_retrieval_canary_enabled"].default is True


class Fail(Exception):  # same shape as onnxruntime.capi.onnxruntime_pybind11_state.Fail
    pass


def test_unlisted_exception_class_ends_only_the_canary_task(wired, applicable, caplog):
    """An onnxruntime-style plain Exception must not touch startup state or chat readiness."""
    deps = applicable

    class _OnnxFail:
        async def encode_single_full_async(self, text):
            raise Fail("onnx session failed")

    assert not issubclass(Fail, canary._CANARY_ERRORS)

    async def go():
        holder = SimpleNamespace()
        task = canary.schedule_first_person_retrieval_canary(
            SimpleNamespace(embedding=_OnnxFail()), holder
        )
        assert task is not None and holder.fp_canary_task is task
        await asyncio.wait([task])
        await asyncio.sleep(0)  # let the done-callback run
        return task

    caplog.set_level(logging.INFO, logger=LOGGER)
    task = asyncio.run(go())

    assert isinstance(task.exception(), Fail)
    assert deps.startup_complete is True and deps.startup_error is None
    assert any(
        r.levelno == logging.ERROR and "chat readiness is unaffected" in r.getMessage()
        for r in caplog.records
    )


def test_canary_runs_after_startup_complete_is_set(wired, applicable):
    deps = applicable

    seen: list[bool] = []

    class _Embed(_Embedding):
        async def encode_single_full_async(self, text):
            seen.append(deps.startup_complete)
            return await super().encode_single_full_async(text)

    async def go():
        task = canary.schedule_first_person_retrieval_canary(
            SimpleNamespace(embedding=_Embed()), SimpleNamespace()
        )
        return await task

    steps = asyncio.run(go())
    assert seen == [True] and all(s.ok for s in steps)


def test_startup_body_schedules_canary_after_startup_complete():
    """Ordering guard: nothing the canary does may precede ``startup_complete = True``."""
    import inspect

    from app import main

    src = inspect.getsource(main._background_startup_body)
    assert src.index("startup_complete = True") < src.index(
        "schedule_first_person_retrieval_canary("
    )


def test_schedule_is_a_noop_when_not_applicable(applicable, monkeypatch):
    monkeypatch.setattr(settings, "startup_retrieval_canary_enabled", False)

    async def go():
        holder = SimpleNamespace()
        return canary.schedule_first_person_retrieval_canary(SimpleNamespace(), holder), holder

    task, holder = asyncio.run(go())
    assert task is None and not hasattr(holder, "fp_canary_task")
