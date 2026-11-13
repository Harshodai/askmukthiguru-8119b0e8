"""Security audit 2026-11-13: inspect-source gates, log redaction."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import search_routes
from app.dependencies import get_container_async
from rag.nodes import on_device_intent as odi
from services.auth_service import get_optional_user

VID = "abcDEF12345"
URL = f"https://www.youtube.com/watch?v={VID}"
SECRET = "SECRET-TRANSCRIPT-TEXT"


def _client(monkeypatch, *, blocked=False, rights="licensed", payloads=None):
    monkeypatch.setattr("services.first_person_video_decisions.video_is_blocked", lambda v: blocked)
    monkeypatch.setattr("services.qdrant.indexer.resolve_source_rights_status", lambda **kw: rights)
    monkeypatch.setattr(search_routes, "is_blocked_source", lambda p: False)
    points = [
        SimpleNamespace(id=i, payload=p)
        for i, p in enumerate(payloads or [{"text": SECRET, "chunk_index": 0}])
    ]
    qc = MagicMock()
    qc.scroll.return_value = (points, None)
    container = SimpleNamespace(qdrant=SimpleNamespace(get_client=lambda: qc, collection_name="c"))

    async def _container():
        return container

    async def _user():
        return None

    app = FastAPI()
    app.include_router(search_routes.router)
    app.dependency_overrides[get_container_async] = _container
    app.dependency_overrides[get_optional_user] = _user
    app.state.limiter = search_routes.limiter
    return TestClient(app)


def test_blocked_video_refused_without_text(monkeypatch):
    r = _client(monkeypatch, blocked=True).get("/api/search/inspect-source", params={"url": URL})
    assert r.status_code == 404
    assert SECRET not in r.text


@pytest.mark.parametrize(
    "url",
    [
        "https://m.youtube.com/watch?v=abcDEF12345",
        "https://music.youtube.com/watch?v=abcDEF12345",
        "https://www.youtube-nocookie.com/embed/abcDEF12345",
        "https://www.youtube.com/shorts/abcDEF12345",
    ],
)
def test_blocked_video_refused_on_every_youtube_host_and_path(monkeypatch, url):
    """Found by the test challenge pass: the route's own id extractor knew only
    www/youtube.com and youtu.be, so a blocked video reached through another
    host got no id, skipped the blocked-video gate and returned its transcript."""
    r = _client(monkeypatch, blocked=True).get("/api/search/inspect-source", params={"url": url})
    assert r.status_code == 404, (r.status_code, r.text[:200])
    assert SECRET not in r.text


def test_unlicensed_video_refused_without_text(monkeypatch):
    r = _client(monkeypatch, rights="unverified").get(
        "/api/search/inspect-source", params={"url": URL}
    )
    assert r.status_code == 403
    assert SECRET not in r.text


def test_allowed_video_shape_unchanged_and_quarantined_dropped(monkeypatch):
    payloads = [
        {"text": SECRET, "chunk_index": 0},
        {"text": "QUARANTINED", "chunk_index": 1, "quality_status": "quarantined"},
        {"text": "REASONED", "chunk_index": 2, "quarantine_reason": "x"},
    ]
    r = _client(monkeypatch, payloads=payloads).get(
        "/api/search/inspect-source", params={"url": URL}
    )
    assert r.status_code == 200
    body = r.json()
    assert {"url", "video_id", "title", "total_chunks", "chunks", "full_text", "matches"} <= set(
        body
    )
    assert body["total_chunks"] == 1
    assert "QUARANTINED" not in r.text and "REASONED" not in r.text


def test_on_device_intent_logs_no_user_text(caplog):
    text = "I am so depressed, please compare my health with sadness"
    with caplog.at_level(logging.INFO):
        odi.classify_with_reason(text)
        odi.classify_with_reason(" ".join(["private worry"] * 10))
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "depressed" not in joined and "private worry" not in joined
    assert "sha=" in joined
