from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import app.dependencies as _app_deps
from app.main import app

client = TestClient(app)


async def _async_true(*args, **kwargs):
    return True


def test_health_check(monkeypatch):
    """Verify the health endpoint returns a valid healthy response with mocked container."""
    monkeypatch.setattr(_app_deps, "startup_complete", True)
    monkeypatch.setattr("app.api.health._check_redis", lambda c: _async_true())
    monkeypatch.setattr("app.api.health._check_neo4j", lambda c: _async_true())

    mock_container = MagicMock()
    mock_container.qdrant.health_check.return_value = True
    mock_container.ollama.health_check = _async_true
    mock_container.ocr.health_check.return_value = True
    mock_container.embedding._encoder = MagicMock()
    mock_container.guardrails.is_available = True
    mock_container.guardrails.provider_name = "mock"
    mock_container.exact_cache = MagicMock()
    mock_container.exact_cache.is_available = True
    mock_container.semantic_cache = MagicMock()
    mock_container.semantic_cache.is_available = True
    mock_container.fast_graph = MagicMock()
    mock_container.standard_graph = MagicMock()
    mock_container.deep_graph = MagicMock()
    mock_container.lightrag_degraded = False
    mock_container.job_queue = MagicMock()
    mock_container.job_queue.queue_size = 0

    async def mock_get_container():
        return mock_container

    app.dependency_overrides[_app_deps.get_container] = mock_get_container

    try:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "services" in data
    finally:
        app.dependency_overrides.pop(_app_deps.get_container, None)


def test_metrics_admin_only():
    """Verify that the /metrics endpoint requires admin authentication (gated).

    Explicitly overrides get_current_user_from_supabase to a known non-admin
    identity rather than relying on ambient settings.is_production: that flag
    (and its "no token -> raise 401" vs "no token -> anonymous, then 403 from
    _require_admin" branching) depends on whichever other test module ran
    first in this process, which made this assertion flip between 401 and 403
    depending purely on test collection order.
    """
    from app.main import get_current_user_from_supabase

    app.dependency_overrides[get_current_user_from_supabase] = lambda: {"id": "u1", "is_superuser": False}
    try:
        response = client.get("/metrics")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)

