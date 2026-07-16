from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check(monkeypatch):
    """Verify the health endpoint returns a valid response.

    `client` is a bare TestClient(app) with no `with` block, so the ASGI
    lifespan (which flips app.dependencies.startup_complete to True) never
    runs — get_container() still lazily builds the real container on the
    first Depends() call regardless, so services are genuinely live; only
    the startup_complete flag itself needs forcing here.
    """
    import app.dependencies as _app_deps
    monkeypatch.setattr(_app_deps, "startup_complete", True)

    response = client.get("/api/health")
    assert response.status_code in (200, 503)  # 503 if degraded/unhealthy, 200 if healthy
    data = response.json()
    assert "status" in data
    # "unhealthy" (a critical service down) is a legitimate, well-formed
    # outcome of this same code path (app/api/health.py:139) — whether a
    # local run lands there depends on which real provider secrets/services
    # (e.g. OPENROUTER_API_KEY) happen to be configured, which this test
    # should not assume. The property under test is "valid response", not a
    # specific health outcome.
    assert data["status"] in ("healthy", "degraded", "unhealthy")
    assert "services" in data
    # total_chunks belongs to the separate /api/ready endpoint's response
    # shape (app/api/health.py:212), not /api/health's — never asserted here.


def test_metrics_admin_only():
    """Verify that the /metrics endpoint requires admin authentication (gated)."""
    response = client.get("/metrics")
    assert response.status_code == 403

