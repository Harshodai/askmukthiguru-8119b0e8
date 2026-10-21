from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import ServiceContainer, get_container
from app.main import app, get_current_user_from_supabase
from services.user_profile_service import LanguagePreference, SpiritualLevel, UserProfile

client = TestClient(app)


def mock_get_current_user():
    return {
        "id": "test-user-id",
        "email": "test@example.com",
        "user_metadata": {"full_name": "Test Seeker"},
    }


@pytest.fixture
def mock_dependencies():
    container = MagicMock(spec=ServiceContainer)

    # Mock memory service and the exact-answer cache whose personalized
    # responses must be invalidated after memory mutations.
    container.memory_service = AsyncMock()
    container.exact_cache = MagicMock()
    container.exact_cache.invalidate_user.return_value = 1

    # Every write path must read a current server-side consent receipt.
    container.memory_outbox = AsyncMock()
    container.memory_outbox.active_consent.return_value = {
        "id": "consent-test", "granted": True, "consent_version": "memory-v1"
    }

    # Mock user profile service
    container.user_profile = AsyncMock()

    app.dependency_overrides[get_current_user_from_supabase] = mock_get_current_user
    app.dependency_overrides[get_container] = lambda: container

    yield container

    app.dependency_overrides.clear()


def test_list_memories_endpoint(mock_dependencies):
    container = mock_dependencies

    now = datetime.now(UTC)
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
        ],
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
        topics_of_interest=["breath", "detachment"],
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

    now = datetime.now(UTC)
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
    container.exact_cache.invalidate_user.assert_called_once_with("test-user-id")


def test_add_memory_requires_active_server_consent(mock_dependencies):
    container = mock_dependencies
    container.memory_outbox.active_consent.return_value = None

    response = client.post("/api/memory/add", json={"text": "Meditation practice is daily"})

    assert response.status_code == 403
    container.memory_service.add_explicit.assert_not_called()


def test_add_memory_fails_closed_when_consent_store_is_unavailable(mock_dependencies):
    container = mock_dependencies
    container.memory_outbox.active_consent.side_effect = RuntimeError("storage offline")

    response = client.post("/api/memory/add", json={"text": "Meditation practice is daily"})

    assert response.status_code == 503
    container.memory_service.add_explicit.assert_not_called()


def test_upsert_core_memory_requires_server_consent(mock_dependencies):
    container = mock_dependencies
    container.memory_outbox.active_consent.return_value = {"id": "consent-test"}
    query = MagicMock()
    query.upsert.return_value = query
    query.select.return_value = query
    query.single.return_value = query
    query.execute.return_value = type("Result", (), {
        "data": {"id": "core-1", "content": "Be concise", "updated_at": "2026-10-21T00:00:00+00:00"}
    })()
    container.supabase_client = MagicMock()
    container.supabase_client.table.return_value = query

    response = client.put("/api/memory/core", json={"content": "Be concise"})

    assert response.status_code == 200, response.text
    assert response.json()["content"] == "Be concise"
    payload = query.upsert.call_args.args[0]
    assert payload["user_id"] == "test-user-id"
    assert payload["tenant_id"] == "oneness"


def test_upsert_core_memory_denies_without_consent(mock_dependencies):
    container = mock_dependencies
    container.memory_outbox.active_consent.return_value = None

    response = client.put("/api/memory/core", json={"content": "Be concise"})

    assert response.status_code == 403
    container.supabase_client.table.assert_not_called()


def test_forget_memory_endpoint(mock_dependencies):
    container = mock_dependencies

    container.memory_service.forget.return_value = True

    response = client.post("/api/memory/forget", json={"memory_id": "forget-me-id"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    container.memory_service.forget.assert_called_once_with("test-user-id", "forget-me-id")
    container.exact_cache.invalidate_user.assert_called_once_with("test-user-id")


def test_forget_memory_not_found(mock_dependencies):
    container = mock_dependencies

    container.memory_service.forget.return_value = False

    response = client.post("/api/memory/forget", json={"memory_id": "nonexistent-id"})

    assert response.status_code == 404
    assert "detail" in response.json()


def test_personal_knowledge_graph_requires_authenticated_identity(mock_dependencies, monkeypatch):
    from app.api import memory as memory_api

    monkeypatch.setattr(memory_api, "_resolve_kg_user_id", AsyncMock(return_value=None))
    response = client.get("/api/memory/knowledge-graph?view=personal")

    assert response.status_code == 401


def test_public_knowledge_graph_allows_anonymous_ontology_view(mock_dependencies, monkeypatch):
    from app.api import memory as memory_api

    monkeypatch.setattr(memory_api, "_resolve_kg_user_id", AsyncMock(return_value=None))
    mock_dependencies.memory_service.build_personal_knowledge_graph.return_value = {
        "nodes": [],
        "edges": [],
    }

    response = client.get("/api/memory/knowledge-graph?view=ontology")

    assert response.status_code == 200
    assert response.json() == {"nodes": [], "edges": [], "count": 0}
