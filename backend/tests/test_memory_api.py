import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.dependencies import ServiceContainer, get_container
from app.main import app, get_current_user_from_supabase
from services.user_profile_service import SpiritualLevel, LanguagePreference, UserProfile

client = TestClient(app)

def mock_get_current_user():
    return {
        "id": "test-user-id",
        "email": "test@example.com",
        "user_metadata": {"full_name": "Test Seeker"}
    }

@pytest.fixture
def mock_dependencies():
    container = MagicMock(spec=ServiceContainer)
    
    # Mock memory service
    container.memory_service = AsyncMock()
    
    # Mock user profile service
    container.user_profile = AsyncMock()

    app.dependency_overrides[get_current_user_from_supabase] = mock_get_current_user
    app.dependency_overrides[get_container] = lambda: container

    yield container

    app.dependency_overrides.clear()


def test_list_memories_endpoint(mock_dependencies):
    container = mock_dependencies
    
    now = datetime.now(timezone.utc)
    mock_result = {
        "total": 1,
        "memories": [
            {
                "id": "mem-123",
                "content": "Seeker wants to learn meditation",
                "source": "explicit",
                "created_at": now,
                "updated_at": now,
            }
        ]
    }
    container.memory_service.list_memories.return_value = mock_result

    response = client.get("/api/memory/list?page=1&page_size=10")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 10
    
    mem = data["memories"][0]
    assert mem["id"] == "mem-123"
    assert mem["claim"] == "Seeker wants to learn meditation"
    assert mem["source"] == "explicit"
    assert mem["confidence"] == 1.0
    assert mem["decay_score"] == 1.0
    assert "last_seen" in mem


def test_get_core_memory_endpoint(mock_dependencies):
    container = mock_dependencies

    # Mock user profile
    mock_profile = UserProfile(
        user_id="test-user-id",
        created_at=1234567.0,
        updated_at=1234567.0,
        preferred_language=LanguagePreference.HINDI,
        spiritual_level=SpiritualLevel.SEEKER,
        topics_of_interest=["breath", "detachment"]
    )
    container.user_profile.get_or_create_profile.return_value = mock_profile

    response = client.get("/api/memory/core")

    assert response.status_code == 200
    data = response.json()
    
    profile = data["profile"]
    assert profile["name"] == "Test Seeker"
    assert profile["language"] == "hi"
    assert profile["practice_level"] == "advanced"
    assert profile["dominant_themes"] == ["breath", "detachment"]
    assert "updated_at" in data


def test_add_memory_endpoint(mock_dependencies):
    container = mock_dependencies
    
    now = datetime.now(timezone.utc)
    mock_inserted = {
        "id": "new-mem-uuid",
        "content": "Meditation practice is daily",
        "source": "explicit",
        "created_at": now,
        "updated_at": now,
    }
    container.memory_service.add_explicit.return_value = mock_inserted

    response = client.post("/api/memory/add", json={"text": "Meditation practice is daily"})

    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == "new-mem-uuid"
    assert data["claim"] == "Meditation practice is daily"
    assert data["source"] == "explicit"
    container.memory_service.add_explicit.assert_called_once_with(
        "test-user-id", "Meditation practice is daily", is_core=False
    )


def test_forget_memory_endpoint(mock_dependencies):
    container = mock_dependencies
    
    container.memory_service.forget.return_value = True

    response = client.post("/api/memory/forget", json={"memory_id": "forget-me-id"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    container.memory_service.forget.assert_called_once_with(
        "test-user-id", "forget-me-id"
    )


def test_forget_memory_not_found(mock_dependencies):
    container = mock_dependencies
    
    container.memory_service.forget.return_value = False

    response = client.post("/api/memory/forget", json={"memory_id": "nonexistent-id"})

    assert response.status_code == 404
    assert "detail" in response.json()
