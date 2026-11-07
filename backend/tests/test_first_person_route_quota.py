"""Tests for T1-08: Auth, quota, and budget on /api/first-person/query and rights-gated video streaming (SEC-001, SEC-002, D-07)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import first_person as fp_api
from app.api import ingest as ingest_api
from app.config import settings
from app.dependencies import get_container_async
from app.main import app
from services.anon_quota_port import QuotaResult
from services.auth_service import get_optional_user
from services.first_person_pipeline import FirstPersonPipelineResult

client = TestClient(app)


class _PassRail:
    async def check_output(self, _text):
        return {"blocked": False, "reason": None}


def _mock_pipeline_result():
    return FirstPersonPipelineResult(
        answer_text="Teacher teaching verbatim quote.",
        citations=[
            {
                "video_id": "test_video",
                "start_time": 10.0,
                "end_time": 25.0,
                "verbatim_text": "Teacher teaching verbatim quote.",
                "speaker": "preethaji",
                "speaker_verified": True,
            }
        ],
        status="served",
        is_direct_answer=True,
        latency_ms=1.0,
    )


class _MockEmbedding:
    async def encode_single_full_async(self, text):
        return {"dense": [0.1] * 384, "sparse": {}}


class _MockQuotaService:
    def __init__(self, allowed=True, remaining=5, total_limit=5, retry_after=None):
        self._allowed = allowed
        self._remaining = remaining
        self._total_limit = total_limit
        self._retry_after = retry_after

    async def check_and_record(self, user):
        return QuotaResult(
            allowed=self._allowed,
            remaining=self._remaining,
            total_limit=self._total_limit,
            retry_after_seconds=self._retry_after,
        )


class _FakeContainer:
    embedding = _MockEmbedding()
    guardrails = _PassRail()
    translation = None
    anon_quota_service = _MockQuotaService()


@pytest.fixture(autouse=True)
def _setup_first_person(monkeypatch):
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "video_stream_rights_gate_enabled", True)
    fp_api._pipeline.cache_clear()
    yield
    fp_api._pipeline.cache_clear()


def test_anonymous_without_session_token_returns_401():
    """SEC-001: Anonymous call without a session token or auth token returns 401."""
    resp = client.post("/api/first-person/query", json={"query": "What is awareness?"})
    assert resp.status_code == 401
    assert "token required" in resp.json()["detail"].lower()


def test_anonymous_with_session_token_in_header_succeeds():
    """Anonymous call providing valid session token in header proceeds."""
    mock_pipe = MagicMock()
    mock_pipe.execute.return_value = _mock_pipeline_result()

    container = _FakeContainer()
    app.dependency_overrides[get_container_async] = lambda: container
    try:
        with patch.object(fp_api, "_pipeline", lambda *a, **k: mock_pipe):
            resp = client.post(
                "/api/first-person/query",
                json={"query": "What is awareness?"},
                headers={"X-Session-Id": "anon:test-token-123"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "served"
    finally:
        app.dependency_overrides.pop(get_container_async, None)


def test_anonymous_with_session_id_in_body_succeeds():
    """Anonymous call providing session_id in body proceeds."""
    mock_pipe = MagicMock()
    mock_pipe.execute.return_value = _mock_pipeline_result()

    container = _FakeContainer()
    app.dependency_overrides[get_container_async] = lambda: container
    try:
        with patch.object(fp_api, "_pipeline", lambda *a, **k: mock_pipe):
            resp = client.post(
                "/api/first-person/query",
                json={"query": "What is awareness?", "session_id": "anon:test-token-body"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "served"
    finally:
        app.dependency_overrides.pop(get_container_async, None)


def test_anonymous_exceeding_quota_returns_429():
    """Anonymous caller who exceeds their turn quota gets 429 quota_exceeded."""
    container = _FakeContainer()
    container.anon_quota_service = _MockQuotaService(
        allowed=False,
        remaining=0,
        total_limit=5,
        retry_after=3600,
    )

    app.dependency_overrides[get_container_async] = lambda: container
    try:
        resp = client.post(
            "/api/first-person/query",
            json={"query": "What is awareness?"},
            headers={"X-Session-Id": "anon:test-exhausted"},
        )
        assert resp.status_code == 429
        body = resp.json()
        assert body["quota_exceeded"] is True
        assert body["error"] == "Anonymous quota exceeded"
        assert resp.headers.get("retry-after") == "3600"
    finally:
        app.dependency_overrides.pop(get_container_async, None)


def test_user_over_daily_budget_returns_429():
    """Caller exceeding daily spend cap gets 429 budget exceeded."""
    container = _FakeContainer()
    app.dependency_overrides[get_container_async] = lambda: container
    try:
        with patch("app.api.first_person.get_cost_tracker") as mock_ct:
            mock_tracker = mock_ct.return_value
            mock_tracker.is_user_over_budget.return_value = True

            resp = client.post(
                "/api/first-person/query",
                json={"query": "What is awareness?"},
                headers={"X-Session-Id": "anon:test-over-budget"},
            )
            assert resp.status_code == 429
            assert "daily budget exceeded" in resp.json()["error"].lower()
    finally:
        app.dependency_overrides.pop(get_container_async, None)


def test_authenticated_user_bypasses_session_token_requirement():
    """Authenticated user does not require an anonymous session token."""
    mock_pipe = MagicMock()
    mock_pipe.execute.return_value = _mock_pipeline_result()

    container = _FakeContainer()
    app.dependency_overrides[get_container_async] = lambda: container
    app.dependency_overrides[get_optional_user] = lambda: {
        "id": "usr_authed_123",
        "email": "seeker@gmail.com",
        "is_anonymous": False,
    }
    try:
        with patch.object(fp_api, "_pipeline", lambda *a, **k: mock_pipe):
            resp = client.post(
                "/api/first-person/query",
                json={"query": "What is awareness?"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "served"
    finally:
        app.dependency_overrides.pop(get_container_async, None)
        app.dependency_overrides.pop(get_optional_user, None)


def test_video_streaming_rights_gate_unlicensed_returns_403(tmp_path, monkeypatch):
    """SEC-002: Video not cleared in rights register returns 403."""
    vid = "unlicensed_vid_999"
    video_file = tmp_path / f"{vid}.mp4"
    video_file.write_bytes(b"dummy video bytes")

    monkeypatch.setattr(ingest_api, "_resolve_video_file_path", lambda _v: str(video_file))
    monkeypatch.setattr(
        "services.qdrant.indexer.resolve_source_rights_status",
        lambda source_url="", video_id="": "unverified",
    )

    test_app = FastAPI()
    test_app.include_router(ingest_api.router, prefix="/api")
    test_client = TestClient(test_app)

    resp = test_client.get(f"/api/media/videos/{vid}")
    assert resp.status_code == 403
    assert "not cleared for streaming" in resp.json()["detail"]


def test_video_streaming_rights_gate_licensed_succeeds(tmp_path, monkeypatch):
    """SEC-002: Video cleared in rights register returns 200/206."""
    vid = "licensed_vid_001"
    video_file = tmp_path / f"{vid}.mp4"
    video_file.write_bytes(b"licensed content bytes " * 10)

    monkeypatch.setattr(ingest_api, "_resolve_video_file_path", lambda _v: str(video_file))
    monkeypatch.setattr(
        "services.qdrant.indexer.resolve_source_rights_status",
        lambda source_url="", video_id="": "licensed",
    )

    test_app = FastAPI()
    test_app.include_router(ingest_api.router, prefix="/api")
    test_client = TestClient(test_app)

    resp = test_client.get(f"/api/media/videos/{vid}")
    assert resp.status_code == 200
    assert resp.content == b"licensed content bytes " * 10
