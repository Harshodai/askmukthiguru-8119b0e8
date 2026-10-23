"""Tests for the personal-subgraph endpoint (Task 7: Per-User KG in Chat).

These tests call the endpoint function directly via FastAPI TestClient
but avoid importing app.main (which has a pre-existing FastAPI/Pydantic
compat issue in the test environment). Instead we test the kg router
in isolation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.kg import router
from services.auth_service import get_current_user_from_supabase
from services.tenant_context import TenantContext


def _authed_user():
    return {"id": "user-123", "email": "seeker@example.com", "is_superuser": False}


def _anon_user():
    return {"id": "anonymous", "is_anonymous": True}


def _make_app():
    """Create a minimal FastAPI app with just the kg router."""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield


# ── Anonymous / unauthenticated ──────────────────────────────────────────────


def test_personal_subgraph_anonymous_returns_empty():
    """Anonymous users get an empty personal graph, not a 401."""
    app = _make_app()
    app.dependency_overrides[get_current_user_from_supabase] = _anon_user
    client = TestClient(app)
    resp = client.get("/api/kg/personal-subgraph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["nodes"] == []
    assert body["edges"] == []
    assert body["count"] == 0


# ── Authenticated — memory_service available ─────────────────────────────────


def test_personal_subgraph_authed_uses_memory_service():
    """Authenticated user triggers build_personal_knowledge_graph."""
    app = _make_app()
    app.dependency_overrides[get_current_user_from_supabase] = _authed_user
    client = TestClient(app)

    fake_result = {
        "nodes": [
            {"id": "user:u1", "label": "You", "type": "User"},
            {"id": "concept:Beautiful State", "label": "Beautiful State", "type": "Concept"},
            {
                "id": "memory:m1",
                "label": "inner peace",
                "type": "Memory",
                "state_category": "Beautiful State",
            },
        ],
        "edges": [
            {"source": "user:u1", "target": "memory:m1", "type": "HAS_MEMORY"},
            {"source": "memory:m1", "target": "concept:Beautiful State", "type": "IN_STATE"},
        ],
    }

    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph = AsyncMock(return_value=fake_result)

    with patch("app.api.kg.get_container") as mock_get:
        container = MagicMock()
        container.memory_service = mock_svc
        mock_get.return_value = container

        resp = client.get("/api/kg/personal-subgraph?limit=50")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 3
        assert len(body["nodes"]) == 3
        assert len(body["edges"]) == 2

        mock_svc.build_personal_knowledge_graph.assert_called_once_with(
            "user-123", view="personal", limit=50, query=""
        )


def test_personal_subgraph_propagates_query_and_safe_node_context():
    app = _make_app()
    app.dependency_overrides[get_current_user_from_supabase] = _authed_user
    client = TestClient(app)

    fake_result = {
        "nodes": [
            {
                "id": "memory:m1",
                "label": "Stillness",
                "type": "Memory",
                "state_category": "Beautiful State",
                "content": "A private reflection about stillness.",
            }
        ],
        "edges": [],
    }
    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph = AsyncMock(return_value=fake_result)

    with patch("app.api.kg.get_container") as mock_get:
        container = MagicMock()
        container.memory_service = mock_svc
        mock_get.return_value = container

        resp = client.get("/api/kg/personal-subgraph?limit=24&query=stillness")
        assert resp.status_code == 200
        body = resp.json()
        assert body["nodes"][0]["state_category"] == "Beautiful State"
        assert body["nodes"][0]["content_preview"] == "A private reflection about stillness."
        mock_svc.build_personal_knowledge_graph.assert_called_once_with(
            "user-123", view="personal", limit=24, query="stillness"
        )


def test_personal_subgraph_authed_empty_personal_returns_empty():
    """When personal graph is empty, endpoint returns empty."""
    app = _make_app()
    app.dependency_overrides[get_current_user_from_supabase] = _authed_user
    client = TestClient(app)

    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph = AsyncMock(return_value={"nodes": [], "edges": []})

    with patch("app.api.kg.get_container") as mock_get:
        container = MagicMock()
        container.memory_service = mock_svc
        mock_get.return_value = container

        resp = client.get("/api/kg/personal-subgraph")
        assert resp.status_code == 200
        body = resp.json()
        assert body["nodes"] == []
        assert body["count"] == 0


# ── Authenticated — memory_service unavailable ───────────────────────────────


def test_personal_subgraph_no_memory_service_returns_empty():
    """Graceful degradation when memory_service is not wired."""
    app = _make_app()
    app.dependency_overrides[get_current_user_from_supabase] = _authed_user
    client = TestClient(app)

    with patch("app.api.kg.get_container") as mock_get:
        container = MagicMock()
        container.memory_service = None
        mock_get.return_value = container

        resp = client.get("/api/kg/personal-subgraph")
        assert resp.status_code == 200
        body = resp.json()
        assert body["nodes"] == []
        assert body["count"] == 0


# ── Authenticated — service exception ────────────────────────────────────────


def test_personal_subgraph_service_error_returns_empty():
    """Service exception returns empty graph, not a 500."""
    app = _make_app()
    app.dependency_overrides[get_current_user_from_supabase] = _authed_user
    client = TestClient(app)

    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph = AsyncMock(side_effect=RuntimeError("db down"))

    with patch("app.api.kg.get_container") as mock_get:
        container = MagicMock()
        container.memory_service = mock_svc
        mock_get.return_value = container

        resp = client.get("/api/kg/personal-subgraph")
        assert resp.status_code == 200
        body = resp.json()
        assert body["nodes"] == []
        assert body["count"] == 0


# ── Edge conversion ──────────────────────────────────────────────────────────


def test_personal_subgraph_maps_edge_type_to_label():
    """Edges from memory_service use 'type' key; endpoint maps to 'label'."""
    app = _make_app()
    app.dependency_overrides[get_current_user_from_supabase] = _authed_user
    client = TestClient(app)

    fake_result = {
        "nodes": [{"id": "n1", "label": "A", "type": "Concept"}],
        "edges": [{"source": "n1", "target": "n1", "type": "SELF"}],
    }

    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph = AsyncMock(return_value=fake_result)

    with patch("app.api.kg.get_container") as mock_get:
        container = MagicMock()
        container.memory_service = mock_svc
        mock_get.return_value = container

        resp = client.get("/api/kg/personal-subgraph")
        body = resp.json()
        assert body["edges"][0]["label"] == "SELF"


def test_personal_subgraph_unauthenticated_returns_401():
    """Unauthenticated caller without valid session gets 401."""
    from fastapi import HTTPException

    app = _make_app()

    def _unauthenticated():
        raise HTTPException(status_code=401, detail="Authentication required")

    app.dependency_overrides[get_current_user_from_supabase] = _unauthenticated
    client = TestClient(app)
    resp = client.get("/api/kg/personal-subgraph")
    assert resp.status_code == 401


def test_personal_subgraph_user_isolation_cannot_access_other_user():
    """User A cannot access User B's graph even if attempting param tampering."""
    app = _make_app()
    app.dependency_overrides[get_current_user_from_supabase] = lambda: {
        "id": "user-A",
        "email": "a@example.com",
    }
    client = TestClient(app)

    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph = AsyncMock(return_value={"nodes": [], "edges": []})

    with patch("app.api.kg.get_container") as mock_get:
        container = MagicMock()
        container.memory_service = mock_svc
        mock_get.return_value = container

        # Attempt to inject user-B via query parameters
        resp = client.get("/api/kg/personal-subgraph?user_id=user-B&userId=user-B")
        assert resp.status_code == 200
        # Verified that memory service is called strictly with authenticated user-A
        mock_svc.build_personal_knowledge_graph.assert_called_once_with(
            "user-A", view="personal", limit=50, query=""
        )


def test_user_a_cannot_read_user_b_subgraph():
    """Verify that User A's session exclusively reads User A's subgraph and cannot see User B's nodes."""
    app = _make_app()
    app.dependency_overrides[get_current_user_from_supabase] = lambda: {
        "id": "user-A",
        "email": "a@example.com",
    }
    client = TestClient(app)

    user_a_graph = {
        "nodes": [{"id": "user:user-A", "label": "User A Memory", "type": "Memory"}],
        "edges": [],
    }
    user_b_graph = {
        "nodes": [{"id": "user:user-B", "label": "User B Secret Memory", "type": "Memory"}],
        "edges": [],
    }

    async def mock_build(uid, **kwargs):
        if uid == "user-A":
            return user_a_graph
        elif uid == "user-B":
            return user_b_graph
        return {"nodes": [], "edges": []}

    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph = AsyncMock(side_effect=mock_build)

    with patch("app.api.kg.get_container") as mock_get:
        container = MagicMock()
        container.memory_service = mock_svc
        mock_get.return_value = container

        resp = client.get("/api/kg/personal-subgraph")
        assert resp.status_code == 200
        data = resp.json()

        # User A only receives User A nodes
        assert any(n["id"] == "user:user-A" for n in data["nodes"])
        # User A cannot see any of User B's nodes
        assert not any(n["id"] == "user:user-B" for n in data["nodes"])
        assert not any("User B" in n["label"] for n in data["nodes"])


def test_personal_subgraph_scopes_graph_query_to_authenticated_tenant():
    app = _make_app()
    app.dependency_overrides[get_current_user_from_supabase] = lambda: {
        "id": "user-tenant-kg",
        "email": "seeker@example.com",
        "tenant_id": "tenant-kg-a",
    }
    client = TestClient(app)
    observed = []

    async def build_graph(user_id, **kwargs):
        observed.append((user_id, TenantContext.get(), TenantContext.get_user_id()))
        return {"nodes": [], "edges": []}

    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph = AsyncMock(side_effect=build_graph)

    with patch("app.api.kg.get_container") as mock_get:
        container = MagicMock()
        container.memory_service = mock_svc
        mock_get.return_value = container
        response = client.get("/api/kg/personal-subgraph")

    assert response.status_code == 200
    assert observed == [("user-tenant-kg", "tenant-kg-a", "user-tenant-kg")]
