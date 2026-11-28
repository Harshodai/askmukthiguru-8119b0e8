"""Logging fixes of 2026-11-28: JSON-on-stdout bootstrap (opt-in), one posture line,
worker correlation id, no user id on the enqueue line."""

from __future__ import annotations

import json
import logging
import sys
from types import SimpleNamespace

import pytest

import app.main as main_module
from app import runtime_budget
from app.config import Settings, settings
from app.context import correlation_id_var
from app.services.job_queue import JobQueueService, JobStatus
from tests.test_job_queue import _MemoryRedis

_FIELDS = {name: False for name, _env in runtime_budget._EXPANSION_POSTURE}


def _record(level: int, msg: str = "hello") -> logging.LogRecord:
    return logging.LogRecord("t.logger", level, __file__, 1, msg, (), None)


# --- default state is unchanged -----------------------------------------------------


def test_new_settings_default_to_off():
    assert Settings.model_fields["log_json_stdout_enabled"].default is False


def test_default_formatter_keeps_python_level_names():
    out = json.loads(main_module.JSONFormatter().format(_record(logging.WARNING)))
    assert out["level"] == "WARNING"
    assert set(out) <= {"timestamp", "level", "logger", "message", "correlation_id", "request_id"}


def test_uvicorn_routing_is_untouched_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(settings, "log_json_stdout_enabled", False)
    lg = logging.getLogger("uvicorn.error")
    handler = logging.NullHandler()
    lg.addHandler(handler)
    before = (lg.propagate, list(lg.handlers))
    try:
        main_module.route_uvicorn_access_through_json()
        assert (lg.propagate, list(lg.handlers)) == before
    finally:
        lg.removeHandler(handler)


# --- opt-in bootstrap swap ----------------------------------------------------------


def _scratch_root() -> tuple[logging.Logger, logging.Handler, logging.Handler]:
    root = logging.Logger("scratch-root")
    bootstrap = logging.StreamHandler()  # stderr, like start_railway's basicConfig
    bootstrap._mg_bootstrap = True  # type: ignore[attr-defined]
    foreign = logging.NullHandler()  # stands in for pytest's capture handler
    root.addHandler(bootstrap)
    root.addHandler(foreign)
    return root, bootstrap, foreign


def test_swap_replaces_only_the_tagged_bootstrap_handler():
    root, bootstrap, foreign = _scratch_root()
    main_module.install_json_stdout_logging(root)
    assert bootstrap not in root.handlers
    assert foreign in root.handlers  # never a blanket force=True
    json_handlers = [h for h in root.handlers if getattr(h, "_mg_json_stdout", False)]
    assert len(json_handlers) == 1
    assert json_handlers[0].stream is sys.stdout
    assert isinstance(json_handlers[0].formatter, main_module.JSONFormatter)


def test_swap_is_idempotent():
    root, *_ = _scratch_root()
    main_module.install_json_stdout_logging(root)
    main_module.install_json_stdout_logging(root)
    assert sum(getattr(h, "_mg_json_stdout", False) for h in root.handlers) == 1


@pytest.mark.parametrize(
    "level,expected",
    [
        (logging.DEBUG, "debug"),
        (logging.INFO, "info"),
        (logging.WARNING, "warn"),
        (logging.ERROR, "error"),
        (logging.CRITICAL, "error"),
    ],
)
def test_swapped_handler_uses_railway_level_names(level, expected):
    root, *_ = _scratch_root()
    main_module.install_json_stdout_logging(root)
    handler = next(h for h in root.handlers if getattr(h, "_mg_json_stdout", False))
    assert json.loads(handler.format(_record(level)))["level"] == expected


def test_uvicorn_loggers_route_through_root_when_the_flag_is_on(monkeypatch):
    monkeypatch.setattr(settings, "log_json_stdout_enabled", True)
    names = ("uvicorn", "uvicorn.error", "uvicorn.access")
    saved = {
        n: (logging.getLogger(n).propagate, list(logging.getLogger(n).handlers)) for n in names
    }
    try:
        for n in names:
            logging.getLogger(n).propagate = False
            logging.getLogger(n).addHandler(logging.NullHandler())
        main_module.route_uvicorn_access_through_json()
        for n in names:
            assert logging.getLogger(n).propagate is True
            assert logging.getLogger(n).handlers == []
    finally:
        for n, (prop, handlers) in saved.items():
            logging.getLogger(n).propagate = prop
            logging.getLogger(n).handlers[:] = handlers


def test_caplog_still_captures_after_a_swap_on_the_real_root(caplog):
    """The swap must not close pytest's capture handler (the reason force=True is not used)."""
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        main_module.install_json_stdout_logging(root)
        with caplog.at_level(logging.INFO):
            logging.getLogger("x.y").info("still captured")
        assert "still captured" in caplog.text
    finally:
        for h in list(root.handlers):
            if getattr(h, "_mg_json_stdout", False):
                root.removeHandler(h)
        for h in before:
            if h not in root.handlers:
                root.addHandler(h)


# --- one posture line ---------------------------------------------------------------


def test_posture_drift_is_one_warning_listing_every_flag_and_the_fingerprint(caplog):
    names = [name for name, _env in runtime_budget._EXPANSION_POSTURE]
    envs = [env for _name, env in runtime_budget._EXPANSION_POSTURE]
    on = SimpleNamespace(**{n: True for n in names})
    with caplog.at_level(logging.INFO):
        runtime_budget.log_runtime_budget(logging.getLogger("test.posture.one"), on)
    drift = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "Context expansion posture" in r.getMessage()
    ]
    assert len(drift) == 1
    text = drift[0].getMessage()
    assert all(env in text for env in envs)
    assert f"fingerprint={runtime_budget.expansion_posture_fingerprint(on)}" in text
    assert f"{len(names)} flag(s)" in text


def test_no_posture_warning_when_the_documented_posture_holds(caplog):
    off = SimpleNamespace(**{name: False for name, _env in runtime_budget._EXPANSION_POSTURE})
    with caplog.at_level(logging.INFO):
        runtime_budget.log_runtime_budget(logging.getLogger("test.posture.off"), off)
    assert not [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "Context expansion posture" in r.getMessage()
    ]


# --- queue: no user id, worker correlation ------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_line_carries_no_user_id(caplog):
    import redis.exceptions

    class _Dead:
        def pipeline(self):
            raise redis.exceptions.ConnectionError("down")

    service = JobQueueService("redis://unused")
    service._redis = _Dead()
    with caplog.at_level(logging.INFO, logger="app.services.job_queue"):
        job_id, _ = await service.enqueue({"message": "hi"}, "anon:SECRETPAYLOAD")
    assert "SECRETPAYLOAD" not in caplog.text
    assert "user=" not in caplog.text
    assert f"enqueued {job_id}" in caplog.text


@pytest.mark.asyncio
async def test_worker_runs_under_the_enqueuing_requests_correlation_id():
    redis = _MemoryRedis()
    service = JobQueueService("redis://unused")
    service._redis = redis
    job_id = "job_corr"
    redis.hashes[f"job:{job_id}:meta"] = {
        "status": JobStatus.QUEUED.value,
        "is_stream": "0",
        "request_data": json.dumps({"message": "x"}),
        "created_at": "100.0",
        "correlation_id": "corr-xyz",
    }
    seen: list[str] = []

    async def worker_factory(request_data, is_stream, received_job_id):
        seen.append(correlation_id_var.get())
        return {"ok": True}

    outer = correlation_id_var.get()
    await service._process_job(job_id, worker_factory, worker_id=1)
    assert seen == ["corr-xyz"]
    assert correlation_id_var.get() == outer  # reset afterwards
    assert redis.hashes[f"job:{job_id}:meta"]["status"] == JobStatus.COMPLETED.value
