"""Tests for the personal-subgraph endpoint (Task 7: Per-User KG in Chat).

These tests call the endpoint function directly via FastAPI TestClient
but avoid importing app.main (which has a pre-existing FastAPI/Pydantic
compat issue in the test environment). Instead we test the kg router
in isolation.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.kg import router, get_optional_user, require_aal2
from app.api.kg import SubgraphResponse, KGNode, KGEdge


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
    app.dependency_overrides[require_aal2] = _anon_user
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
    app.dependency_overrides[require_aal2] = _authed_user
    client = TestClient(app)

    fake_result = {
        "nodes": [
            {"id": "user:u1", "label": "You", "type": "User"},
            {"id": "concept:Beautiful State", "label": "Beautiful State", "type": "Concept"},
            {"id": "memory:m1", "label": "inner peace", "type": "Memory", "state_category": "Beautiful State"},
        ],
        "edges": [
            {"source": "user:u1", "target": "memory:m1", "type": "HAS_MEMORY"},
            {"source": "memory:m1", "target": "concept:Beautiful State", "type": "IN_STATE"},
        ],
    }

    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph.return_value = fake_result

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
            "user-123", view="personal", limit=50
        )


def test_personal_subgraph_authed_empty_personal_returns_empty():
    """When personal graph is empty, endpoint returns empty."""
    app = _make_app()
    app.dependency_overrides[require_aal2] = _authed_user
    client = TestClient(app)

    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph.return_value = {"nodes": [], "edges": []}

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
    app.dependency_overrides[require_aal2] = _authed_user
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
    app.dependency_overrides[require_aal2] = _authed_user
    client = TestClient(app)

    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph.side_effect = RuntimeError("db down")

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
    app.dependency_overrides[require_aal2] = _authed_user
    client = TestClient(app)

    fake_result = {
        "nodes": [{"id": "n1", "label": "A", "type": "Concept"}],
        "edges": [{"source": "n1", "target": "n1", "type": "SELF"}],
    }

    mock_svc = MagicMock()
    mock_svc.build_personal_knowledge_graph.return_value = fake_result

    with patch("app.api.kg.get_container") as mock_get:
        container = MagicMock()
        container.memory_service = mock_svc
        mock_get.return_value = container

        resp = client.get("/api/kg/personal-subgraph")
        body = resp.json()
        assert body["edges"][0]["label"] == "SELF"
