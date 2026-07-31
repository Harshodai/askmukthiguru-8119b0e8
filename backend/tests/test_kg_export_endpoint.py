"""Tests for the KG export endpoint.

Note: TestClient(app) triggers the app lifespan which requires Qdrant. These
tests are skipped when Qdrant is not reachable (host dev without Docker).
"""

import sys
import socket

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))


def _qdrant_available() -> bool:
    try:
        host = settings.qdrant_url.split("//")[-1].split(":")[0]
        port = int(settings.qdrant_url.split(":")[-1].rstrip("/")) if ":" in settings.qdrant_url.split("//")[-1] else 6333
        socket.create_connection((host, port), timeout=1).close()
        return True
    except Exception:
        return False


requires_qdrant = pytest.mark.skipif(
    not _qdrant_available(),
    reason="Qdrant not reachable (run inside Docker or set QDRANT_URL=http://localhost:6333)",
)


@pytest.fixture
def client(monkeypatch):
    # Explicitly force kg_export_enabled=False so the 501 guard is active
    # regardless of any KG_EXPORT_ENABLED env override.
    monkeypatch.setattr(settings, "kg_export_enabled", False)
    return TestClient(app)


@requires_qdrant
def test_export_disabled_by_default(client):
    # kg_export_enabled is explicitly False (forced by fixture, not env-default).
    # The 501 check fires before auth or any service call.
    response = client.post("/api/memory/knowledge-graph/export", json={"view": "ontology", "title": "Test"})
    assert response.status_code == 501


@requires_qdrant
def test_export_invalid_title_rejected():
    # Pydantic 422 fires at request-body validation, before kg_export_enabled or
    # auth are evaluated, so no monkeypatch needed here.
    with TestClient(app) as c:
        response = c.post(
            "/api/memory/knowledge-graph/export",
            json={"view": "ontology", "title": "Test<script>alert(1)</script>"},
        )
    assert response.status_code == 422
