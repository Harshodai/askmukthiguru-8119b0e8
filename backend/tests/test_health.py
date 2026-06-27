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


def test_metrics_unauthenticated():
    """Verify that the /metrics endpoint is public and accessible without authentication."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "process_cpu_seconds_total" in response.text or "guru_" in response.text

