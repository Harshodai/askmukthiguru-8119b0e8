"""Regression coverage for the benchmark harness' asynchronous chat contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).parents[2] / "scripts" / "benchmarks" / "load_test.py"
_SPEC = importlib.util.spec_from_file_location("askmukthi_load_test", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_load_test = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_load_test)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, chunks: tuple[str, ...] = ()) -> None:
        self.status_code = status_code
        self._payload = payload
        self._chunks = chunks
        self.read_called = False

    def json(self) -> dict:
        return self._payload

    async def aread(self) -> bytes:
        self.read_called = True
        return b"{}"

    async def aiter_text(self):
        for chunk in self._chunks:
            yield chunk

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *_args) -> None:
        return None


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response

    async def post(self, *_args, **_kwargs) -> _FakeResponse:
        return self.response

    def stream(self, *_args, **_kwargs) -> _FakeResponse:
        return self.response


@pytest.mark.asyncio
async def test_non_stream_202_is_successful_queue_admission(monkeypatch) -> None:
    response = _FakeResponse(202, {"job_id": "job-1", "status": "queued"})
    result = await _load_test.run_single_query(
        _FakeClient(response), "http://backend", "hello", stream=False
    )

    assert result["success"] is True
    assert result["accepted"] is True
    assert result["status_code"] == 202
    assert result["tokens"] == 0
    assert result["error"] == ""


@pytest.mark.asyncio
async def test_stream_200_remains_completion_success(monkeypatch) -> None:
    response = _FakeResponse(200, {}, chunks=("data: hello", " world"))
    result = await _load_test.run_single_query(
        _FakeClient(response), "http://backend", "hello", stream=True
    )

    assert result["success"] is True
    assert result["accepted"] is False
    assert result["status_code"] == 200
    assert result["tokens"] > 0
    assert result["error"] == ""


@pytest.mark.asyncio
async def test_stream_202_consumes_json_ack_without_calling_it_an_sse_failure() -> None:
    response = _FakeResponse(202, {"job_id": "job-2", "status": "queued"})
    result = await _load_test.run_single_query(
        _FakeClient(response), "http://backend", "hello", stream=True
    )

    assert result["success"] is True
    assert result["accepted"] is True
    assert result["status_code"] == 202
    assert response.read_called is True
    assert result["error"] == ""
