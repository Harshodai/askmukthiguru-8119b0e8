from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    """Verify the health endpoint returns a valid response."""
    response = client.get("/api/health")
    assert response.status_code in (200, 503)  # 503 if degraded, 200 if healthy
    data = response.json()
    assert "status" in data
    assert data["status"] in ("healthy", "degraded")
    assert "services" in data
    assert "total_chunks" in data


def test_metrics_admin_only():
    """Verify that the /metrics endpoint requires admin authentication (gated)."""
    response = client.get("/metrics")
    assert response.status_code == 403

