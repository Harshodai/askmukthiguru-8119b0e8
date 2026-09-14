"""services/vector_optimizer.py existed with zero callers anywhere in the
repo — a complete Qdrant index-health/optimizer utility that was never
wired in. Pins the two admin endpoints that now expose it.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_container
from app.main import app, get_current_user_from_supabase


def mock_get_current_admin():
    return {"id": "admin-user-id", "email": "admin@example.com", "is_superuser": True, "aal": "aal2"}


@pytest.fixture(autouse=True)
def _admin_override():
    app.dependency_overrides[get_current_user_from_supabase] = mock_get_current_admin
    yield
    app.dependency_overrides.pop(get_current_user_from_supabase, None)


@pytest.fixture
def client_with_fake_container(monkeypatch):
    fake_optimizer = MagicMock()
    fake_optimizer.get_index_health.return_value = {
        "status": "green",
        "points_count": 12904,
        "segments_count": 4,
    }
    fake_optimizer.run_optimization = AsyncMock(return_value={"triggered": True})
    monkeypatch.setattr(
        "services.vector_optimizer.VectorIndexOptimizer", lambda qdrant_service: fake_optimizer
    )

    fake_container = MagicMock()
    fake_container.qdrant = MagicMock()
    app.dependency_overrides[get_container] = lambda: fake_container
    yield TestClient(app), fake_optimizer
    app.dependency_overrides.pop(get_container, None)


def test_qdrant_health_endpoint_wired(client_with_fake_container):
    client, fake_optimizer = client_with_fake_container
    resp = client.get("/api/admin/qdrant/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "green"
    fake_optimizer.get_index_health.assert_called_once()


def test_qdrant_optimize_endpoint_wired(client_with_fake_container):
    client, fake_optimizer = client_with_fake_container
    resp = client.post("/api/admin/qdrant/optimize")
    assert resp.status_code == 200
    assert resp.json()["triggered"] is True
    fake_optimizer.run_optimization.assert_awaited_once()


def test_qdrant_endpoints_require_admin():
    app.dependency_overrides.pop(get_current_user_from_supabase, None)
    client = TestClient(app)
    resp = client.get("/api/admin/qdrant/health")
    assert resp.status_code in (401, 403)
