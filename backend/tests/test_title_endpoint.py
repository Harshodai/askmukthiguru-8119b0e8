from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_container
from app.main import app
from services.auth_service import get_current_user_from_supabase, issue_anon_session_token

# Create client without entering context manager to bypass lifespan qdrant startup
client = TestClient(app)


def _override_title_auth():
    return {"id": "test-user", "email": "test@example.com"}


def _mock_quota_service(quota_exceeded=False):
    mock_quota = MagicMock()
    if quota_exceeded:
        result = MagicMock(
            quota_exceeded=True, remaining=0, total_limit=5, retry_after_seconds=3600
        )
    else:
        result = MagicMock(
            quota_exceeded=False, remaining=4, total_limit=5, retry_after_seconds=0,
            reservation_id=None,
        )
    mock_quota.check_and_record = AsyncMock(return_value=result)
    mock_quota.claim = AsyncMock()
    mock_quota.release = AsyncMock()
    return mock_quota


def test_generate_title_endpoint_success(monkeypatch):
    mock_container = MagicMock()
    mock_container.ollama = AsyncMock()
    mock_container.ollama.generate.return_value = "Spiritual Healing Process"
    mock_container.anon_quota_service = _mock_quota_service()

    app.dependency_overrides[get_container] = lambda: mock_container
    app.dependency_overrides[get_current_user_from_supabase] = _override_title_auth

    response = client.post(
        "/api/chat/title", json={"first_message": "How do I heal my relationship from deep anger?"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Spiritual Healing Process"

    # Verify it was called with correct prompts
    mock_container.ollama.generate.assert_called_once()
    kwargs = mock_container.ollama.generate.call_args[1]
    assert "concise" in kwargs["system_prompt"]
    assert "How do I heal my relationship" in kwargs["user_prompt"]

    app.dependency_overrides.clear()


def test_generate_title_endpoint_fallback(monkeypatch):
    mock_container = MagicMock()
    mock_container.ollama = AsyncMock()
    mock_container.ollama.generate.side_effect = Exception("LLM connection timed out")
    mock_container.anon_quota_service = _mock_quota_service()

    app.dependency_overrides[get_container] = lambda: mock_container
    app.dependency_overrides[get_current_user_from_supabase] = _override_title_auth

    first_msg = "Short query"
    response = client.post("/api/chat/title", json={"first_message": first_msg})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == first_msg

    app.dependency_overrides.clear()


def test_generate_title_endpoint_anon_quota_exceeded():
    mock_container = MagicMock()
    mock_container.ollama = AsyncMock()
    mock_container.ollama.generate.return_value = "Should never be called"
    mock_container.anon_quota_service = _mock_quota_service(quota_exceeded=True)

    app.dependency_overrides[get_container] = lambda: mock_container
    app.dependency_overrides[get_current_user_from_supabase] = lambda: {
        "id": "anonymous",
        "email": None,
        "is_anonymous": True,
    }

    issued = issue_anon_session_token()

    try:
        response = client.post(
            "/api/chat/title",
            json={"first_message": "How do I heal my relationship?"},
            headers={"X-Session-Id": issued["token"]},
        )
        assert response.status_code == 429
        assert response.json().get("quota_exceeded") is True
        mock_container.ollama.generate.assert_not_called()
        mock_container.anon_quota_service.check_and_record.assert_called_once()
        called_user = mock_container.anon_quota_service.check_and_record.call_args[0][0]
        assert called_user["id"] == issued["session_id"]
        assert called_user["is_anonymous"] is True
    finally:
        app.dependency_overrides.clear()
