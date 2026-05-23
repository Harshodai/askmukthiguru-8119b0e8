import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app, get_current_user_from_supabase

client = TestClient(app)

def mock_get_current_admin():
    return {"id": "admin-user-id", "email": "admin@example.com", "is_superuser": True}

@pytest.fixture(autouse=True)
def setup_admin_override():
    # Save original override if any
    original_override = app.dependency_overrides.get(get_current_user_from_supabase)
    # Apply override for this test module
    app.dependency_overrides[get_current_user_from_supabase] = mock_get_current_admin
    yield
    # Restore/cleanup
    if original_override is not None:
        app.dependency_overrides[get_current_user_from_supabase] = original_override
    else:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)

@patch('routers.admin.get_recent_traces')
def test_fetch_telemetry_traces_success(mock_get_recent):
    mock_get_recent.return_value = [{"id": "trace-1", "user_message": "test"}]
    response = client.get("/api/admin/traces?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "trace-1"
    mock_get_recent.assert_called_once_with(10)

@patch('routers.admin.get_query_trace')
def test_fetch_query_trace_success(mock_get_query_trace):
    mock_get_query_trace.return_value = {
        "query": {"id": "trace-1", "user_message": "test"},
        "response": {"id": "resp-1", "response_text": "resp"},
        "retrieval": None,
        "spans": [],
        "triggers": [],
        "safety": []
    }
    response = client.get("/api/admin/traces/trace-1")
    assert response.status_code == 200
    data = response.json()
    assert data["query"]["id"] == "trace-1"
    mock_get_query_trace.assert_called_once_with("trace-1")

@patch('routers.admin.get_query_trace')
def test_fetch_query_trace_not_found(mock_get_query_trace):
    mock_get_query_trace.return_value = None
    response = client.get("/api/admin/traces/trace-not-found")
    assert response.status_code == 404
