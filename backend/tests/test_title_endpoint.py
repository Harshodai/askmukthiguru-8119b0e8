from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_container
from app.main import app
from services.auth_service import get_current_user_from_supabase

# Create client without entering context manager to bypass lifespan qdrant startup
client = TestClient(app)

def _override_title_auth():
    return {"id": "test-user", "email": "test@example.com"}

def test_generate_title_endpoint_success(monkeypatch):
    mock_container = MagicMock()
    mock_container.ollama = AsyncMock()
    mock_container.ollama.generate.return_value = "Spiritual Healing Process"
    
    app.dependency_overrides[get_container] = lambda: mock_container
    app.dependency_overrides[get_current_user_from_supabase] = _override_title_auth
    
    response = client.post(
        "/api/chat/title",
        json={"first_message": "How do I heal my relationship from deep anger?"}
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
    
    app.dependency_overrides[get_container] = lambda: mock_container
    app.dependency_overrides[get_current_user_from_supabase] = _override_title_auth
    
    first_msg = "Short query"
    response = client.post(
        "/api/chat/title",
        json={"first_message": first_msg}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == first_msg
    
    app.dependency_overrides.clear()
