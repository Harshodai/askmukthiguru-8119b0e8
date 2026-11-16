"""L-02 (stage status) and L-04 (access-log / progress-bar noise) regressions."""

from __future__ import annotations

import logging
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.pipeline.stages.stage_runner import StageRunner


class _Stage:
    def __init__(self, name, *, set_error=False, result=None, raises=None):
        self.name = name
        self._set_error, self._result, self._raises = set_error, result, raises

    async def run(self, ctx):
        if self._raises:
            raise self._raises
        if self._set_error:
            ctx.last_stage_status = "error"
        return self._result


def _ctx():
    return SimpleNamespace(
        job_id="j",
        trace_id="t",
        last_stage_status="success",
        last_stage_metadata=None,
        stage_telemetry=[],
        start_time=0.0,
    )


async def _run(stage, caplog):
    ctx = _ctx()
    caplog.set_level(logging.INFO, logger="app.pipeline.stages.stage_runner")
    try:
        await StageRunner.run([stage], ctx)
    except RuntimeError:
        pass
    lines = [r.getMessage() for r in caplog.records if "PIPELINE_STAGE_TIMING" in r.getMessage()]
    return ctx, lines


@pytest.mark.asyncio
async def test_intended_short_circuit_logs_short_circuit(caplog):
    ctx, lines = await _run(_Stage("input_guardrails", set_error=True, result=object()), caplog)
    assert "status=short_circuit" in lines[0] and "status=error" not in lines[0]
    assert ctx.stage_telemetry[0]["status"] == "short_circuit"
    assert ctx.last_stage_status == "error"  # sticky field still read by cache/compliance


@pytest.mark.asyncio
async def test_raised_exception_still_logs_error(caplog):
    _, lines = await _run(_Stage("input_guardrails", raises=RuntimeError("boom")), caplog)
    assert "status=error" in lines[0]


@pytest.mark.asyncio
async def test_circuit_breaker_open_stays_error(caplog):
    _, lines = await _run(_Stage("circuit_breaker", set_error=True, result=object()), caplog)
    assert "status=error" in lines[0]


def test_sentence_transformer_encode_disables_progress_bar():
    from services.embedding_service import EmbeddingService

    svc = object.__new__(EmbeddingService)
    svc._inference_lock = threading.RLock()
    svc._circuit = MagicMock()
    svc._encoder = MagicMock()
    svc._encoder.encode.return_value = np.zeros((1, 4))
    with patch("services.embedding_service.settings", SimpleNamespace(embedding_model="x/e5")):
        svc._encode_torch(["hi"], 0.0)
    assert svc._encoder.encode.call_args.kwargs["show_progress_bar"] is False


def test_on_device_intent_encode_disables_progress_bar():
    from rag.nodes import on_device_intent as m

    enc = MagicMock()
    enc.encode.return_value = np.zeros((1, 4))
    with patch.object(m, "_get_encoder", return_value=enc), patch.object(m, "_CLASS_CENTROIDS", {}):
        m._build_centroids()
        m.classify_with_embeddings("hello")
    assert enc.encode.call_args_list
    assert all(c.kwargs.get("show_progress_bar") is False for c in enc.encode.call_args_list)


def test_uvicorn_access_logger_routes_to_root_json_handler():
    from app.main import route_uvicorn_access_through_json

    access = logging.getLogger("uvicorn.access")
    access.addHandler(logging.StreamHandler())
    access.propagate = False
    route_uvicorn_access_through_json()
    assert access.handlers == [] and access.propagate is True
