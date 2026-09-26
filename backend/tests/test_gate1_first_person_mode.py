"""Unit tests for the --mode first-person extension to gate1_load_test.py.

Covers the parts that don't need a live server or a live Qdrant: question-file
loading, dry-run config validation, and the worker's request/response parsing
against a mocked HTTP client. The end-to-end sweep (real traffic, container
watch) is an ops procedure, not a unit test — see docs/operations/drills.md.
"""

from __future__ import annotations

import json

import pytest

from scripts.ops import gate1_load_test as g1

# ─── load_first_person_questions ─────────────────────────────────────────────


def _write_questions(tmp_path, questions):
    path = tmp_path / "questions.json"
    path.write_text(json.dumps({"questions": questions}), encoding="utf-8")
    return path


def test_load_first_person_questions_parses_rows(tmp_path):
    path = _write_questions(
        tmp_path,
        [
            {"id": "q001", "question": "Why do I suffer?", "video_id": "abc"},
            {"id": "q002", "question": "What is the beautiful state?", "video_id": "def"},
        ],
    )
    rows = g1.load_first_person_questions(path)
    assert rows == [
        {"id": "q001", "question": "Why do I suffer?", "video_id": "abc"},
        {"id": "q002", "question": "What is the beautiful state?", "video_id": "def"},
    ]


def test_load_first_person_questions_respects_limit(tmp_path):
    path = _write_questions(tmp_path, [{"id": f"q{i}", "question": f"Q{i}"} for i in range(10)])
    rows = g1.load_first_person_questions(path, limit=3)
    assert len(rows) == 3


def test_load_first_person_questions_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        g1.load_first_person_questions(tmp_path / "nope.json")


def test_load_first_person_questions_empty_array_raises(tmp_path):
    path = _write_questions(tmp_path, [])
    with pytest.raises(ValueError):
        g1.load_first_person_questions(path)


# ─── dry_run_first_person ─────────────────────────────────────────────────────


def test_dry_run_first_person_ok_with_valid_file(tmp_path):
    path = _write_questions(tmp_path, [{"id": "q1", "question": "Q?"}])
    report = g1.dry_run_first_person(path, sweep=[1, 8])
    assert report["ok"] is True
    assert report["problems"] == []
    assert report["n_questions"] == 1


def test_dry_run_first_person_fails_on_bad_file(tmp_path):
    report = g1.dry_run_first_person(tmp_path / "missing.json", sweep=[1, 8])
    assert report["ok"] is False
    assert any("questions file invalid" in p for p in report["problems"])


def test_dry_run_first_person_fails_on_empty_sweep(tmp_path):
    path = _write_questions(tmp_path, [{"id": "q1", "question": "Q?"}])
    report = g1.dry_run_first_person(path, sweep=[])
    assert report["ok"] is False


def test_dry_run_first_person_never_touches_network(tmp_path, monkeypatch):
    """Dry run must not import httpx or open a socket — validate config only."""
    path = _write_questions(tmp_path, [{"id": "q1", "question": "Q?"}])

    def _boom(*a, **kw):
        raise AssertionError("dry-run must never construct a network client")

    monkeypatch.setattr(g1, "run_first_person_load_test", _boom)
    g1.dry_run_first_person(path, sweep=[1])  # must not raise


# ─── first_person_worker (mocked HTTP client) ────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


class _FakeClient:
    """Mocked HTTP client: returns one canned response per call, in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url, json=None, headers=None):
        self.calls.append((url, json))
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


async def _run_worker(client, items):
    import asyncio

    queue: asyncio.Queue = asyncio.Queue()
    for idx, item in enumerate(items):
        queue.put_nowait((idx, item))
    results: list = []
    stop_event = asyncio.Event()
    await g1.first_person_worker(
        worker_id=0,
        client=client,
        endpoint_url="/api/first-person/query",
        headers={"X-Test-Key": "x"},
        queue=queue,
        results=results,
        stop_event=stop_event,
    )
    return results


@pytest.mark.asyncio
async def test_first_person_worker_parses_success_response():
    client = _FakeClient([_FakeResponse(200, {"status": "success", "citations": [{"a": 1}, {"b": 2}]})])
    results = await _run_worker(client, [{"id": "q1", "question": "Why suffer?", "video_id": "v1"}])
    assert len(results) == 1
    r = results[0]
    assert r.status_code == 200
    assert r.passed is True
    assert r.grounding_state == "success"
    assert r.citations_count == 2
    assert client.calls[0][1] == {"query": "Why suffer?", "teacher_id": "both", "max_clips": 3}


@pytest.mark.asyncio
async def test_first_person_worker_marks_429_as_not_passed():
    client = _FakeClient([_FakeResponse(429, text="rate limited")])
    results = await _run_worker(client, [{"id": "q1", "question": "Q?"}])
    assert results[0].status_code == 429
    assert results[0].passed is False
    assert "429" in results[0].error_msg


@pytest.mark.asyncio
async def test_first_person_worker_marks_5xx_as_not_passed():
    client = _FakeClient([_FakeResponse(503, text="unavailable")])
    results = await _run_worker(client, [{"id": "q1", "question": "Q?"}])
    assert results[0].status_code == 503
    assert results[0].passed is False


@pytest.mark.asyncio
async def test_first_person_worker_handles_transport_exception():
    client = _FakeClient([ConnectionError("boom")])
    results = await _run_worker(client, [{"id": "q1", "question": "Q?"}])
    assert results[0].status_code == 500
    assert results[0].passed is False
    assert "ConnectionError" in results[0].error_msg


@pytest.mark.asyncio
async def test_first_person_worker_processes_all_queued_items_in_order():
    client = _FakeClient(
        [
            _FakeResponse(200, {"status": "success", "citations": []}),
            _FakeResponse(200, {"status": "abstained", "citations": []}),
        ]
    )
    results = await _run_worker(
        client, [{"id": "q1", "question": "Q1?"}, {"id": "q2", "question": "Q2?"}]
    )
    assert len(results) == 2
    assert {r.grounding_state for r in results} == {"success", "abstained"}


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
