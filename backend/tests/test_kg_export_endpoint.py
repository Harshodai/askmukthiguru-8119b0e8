import sys

import pytest
from fastapi.testclient import TestClient
from app.main import app


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))


@pytest.fixture
def client():
    return TestClient(app)


def test_export_disabled_by_default(client):
    # Default settings have kg_export_enabled=False. In dev mode the auth
    # dependency falls back to anonymous, so we expect the feature-disabled
    # 501 to surface before auth is required.
    response = client.post("/api/memory/knowledge-graph/export", json={"view": "ontology", "title": "Test"})
    assert response.status_code == 501


def test_export_invalid_title_rejected(client):
    response = client.post(
        "/api/memory/knowledge-graph/export",
        json={"view": "ontology", "title": "Test<script>alert(1)</script>"},
    )
    assert response.status_code == 422
