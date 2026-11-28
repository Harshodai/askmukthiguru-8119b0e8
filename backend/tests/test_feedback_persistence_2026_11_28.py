"""Faculty-preview feedback capture must persist or fail loudly (2026-11-28).

Before: /api/feedback returned fake-success `fallback_data` when the Supabase
insert failed, and /api/feedback/clip-report only wrote a local JSONL (lost on
redeploy). Now both write feedback_events and surface 503 on failure.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import feedback as feedback_api
from services import feedback_service
from services.auth_service import get_current_user_from_supabase

POINT = "0b6f1d52-6a7c-5f3e-9d3a-1c2b3d4e5f60"


class _Table:
    def __init__(self, store: list[dict], fail: bool) -> None:
        self._store, self._fail, self._row = store, fail, None

    def insert(self, row):
        self._row = row
        return self

    def execute(self):
        if self._fail:
            raise RuntimeError("boom SECRET-USER-TEXT")
        self._store.append(self._row)
        return MagicMock(data=[{"id": "row-1", **self._row}])


def _client(monkeypatch, tmp_path, *, user, fail=False, supabase=True):
    rows: list[dict] = []
    client = MagicMock()
    client.table.side_effect = lambda name: (
        _Table(rows, fail) if name == "feedback_events" else None
    )
    monkeypatch.setattr(feedback_service, "_get_client", lambda: client if supabase else None)
    jsonl = tmp_path / "reports.jsonl"
    monkeypatch.setattr(feedback_api.settings, "feedback_clip_reports_path", str(jsonl))

    async def _user():
        return user

    app = FastAPI()
    app.include_router(feedback_api.router, prefix="/api")
    app.dependency_overrides[get_current_user_from_supabase] = _user
    app.state.limiter = feedback_api.limiter
    return TestClient(app), rows, jsonl


_REPORT = {
    "served_point_id": POINT,
    "question": "A clip",
    "reason": "wrong topic: not about grief",
    "reason_category": "wrong topic",
    "video_id": "abc123XYZ_-",
}


def test_clip_report_persists_to_feedback_events_and_jsonl(monkeypatch, tmp_path):
    c, rows, jsonl = _client(monkeypatch, tmp_path, user={"id": "u-1"})
    r = c.post("/api/feedback/clip-report", json=_REPORT)
    assert r.status_code == 201, r.text
    assert len(rows) == 1
    row = rows[0]
    assert row["user_id"] == "u-1" and row["rating"] == -1
    assert row["metadata_json"] == {
        "kind": "clip_report",
        "served_point_id": POINT,
        "reason_category": "wrong topic",
        "video_id": "abc123XYZ_-",
    }
    assert json.loads(jsonl.read_text().splitlines()[0])["served_point_id"] == POINT


@pytest.mark.parametrize("supabase", [True, False])
def test_clip_report_returns_503_when_supabase_fails(monkeypatch, tmp_path, caplog, supabase):
    c, rows, jsonl = _client(
        monkeypatch, tmp_path, user={"id": "u-1"}, fail=supabase, supabase=supabase
    )
    with caplog.at_level("ERROR"):
        r = c.post("/api/feedback/clip-report", json=_REPORT)
    assert r.status_code == 503
    assert rows == [] and not jsonl.exists()
    assert "feedback_store_failed reason=" in caplog.text
    assert "SECRET-USER-TEXT" not in caplog.text and "SECRET-USER-TEXT" not in r.text


def test_clip_report_still_requires_sign_in(monkeypatch, tmp_path):
    c, rows, _ = _client(monkeypatch, tmp_path, user=None)
    assert c.post("/api/feedback/clip-report", json=_REPORT).status_code == 401
    assert rows == []


def test_clip_report_survives_jsonl_failure_after_supabase_success(monkeypatch, tmp_path):
    c, rows, _ = _client(monkeypatch, tmp_path, user={"id": "u-1"})
    monkeypatch.setattr(
        feedback_api.settings, "feedback_clip_reports_path", str(tmp_path / "f" / "x" / "r.jsonl")
    )
    (tmp_path / "f").write_text("a file, so makedirs under it fails")
    assert c.post("/api/feedback/clip-report", json=_REPORT).status_code == 201
    assert len(rows) == 1


_FEEDBACK = {"query": "q", "answer": "a", "rating": -1, "feedback_text": "not quite"}


def test_feedback_stores_row_and_returns_it(monkeypatch, tmp_path):
    c, rows, _ = _client(monkeypatch, tmp_path, user={"id": "u-1"})
    monkeypatch.setattr(feedback_api.jsonl_store, "record_feedback", _noop)
    monkeypatch.setattr("app.core.refiner.mine_failed_session", _noop, raising=False)
    r = c.post("/api/feedback/", json=_FEEDBACK)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "row-1" and rows[0]["user_id"] == "u-1"


@pytest.mark.parametrize("fail,supabase", [(True, True), (False, False)])
def test_feedback_returns_503_not_fake_success(monkeypatch, tmp_path, fail, supabase):
    c, rows, _ = _client(monkeypatch, tmp_path, user={"id": "u-1"}, fail=fail, supabase=supabase)
    monkeypatch.setattr(feedback_api.jsonl_store, "record_feedback", _noop)
    monkeypatch.setattr("app.core.refiner.mine_failed_session", _noop, raising=False)
    r = c.post("/api/feedback/", json={**_FEEDBACK, "rating": 1})
    assert r.status_code == 503
    assert rows == []


async def _noop(*_a, **_k):
    return None
