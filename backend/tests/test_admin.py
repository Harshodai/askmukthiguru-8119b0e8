from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_current_user_from_supabase

client = TestClient(app)


def mock_get_current_admin():
    # aal2 required since P1-SEC-1: admin endpoints are MFA-gated.
    return {
        "id": "admin-user-id",
        "email": "admin@example.com",
        "is_superuser": True,
        "aal": "aal2",
    }


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


@patch("app.api.admin.get_recent_traces")
def test_fetch_telemetry_traces_success(mock_get_recent):
    mock_get_recent.return_value = [{"id": "trace-1", "user_message": "test"}]
    response = client.get("/api/admin/traces?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "trace-1"
    mock_get_recent.assert_called_once_with(
        10, search=None, prompt_version_id=None, model=None, min_judge_score=None
    )


@patch("app.api.admin.get_query_trace")
def test_fetch_query_trace_success(mock_get_query_trace):
    mock_get_query_trace.return_value = {
        "query": {"id": "trace-1", "user_message": "test"},
        "response": {"id": "resp-1", "response_text": "resp"},
        "retrieval": None,
        "spans": [],
        "triggers": [],
        "safety": [],
    }
    response = client.get("/api/admin/traces/trace-1")
    assert response.status_code == 200
    data = response.json()
    assert data["query"]["id"] == "trace-1"
    mock_get_query_trace.assert_called_once_with("trace-1")


@patch("app.api.admin.get_query_trace")
def test_fetch_query_trace_not_found(mock_get_query_trace):
    mock_get_query_trace.return_value = None
    response = client.get("/api/admin/traces/trace-not-found")
    assert response.status_code == 404


@patch("app.api.admin.get_eval_runs")
def test_fetch_evaluations_success(mock_get_eval_runs):
    mock_get_eval_runs.return_value = [{"id": "eval-1", "score": 0.98}]
    response = client.get("/api/admin/evaluations")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "eval-1"
    mock_get_eval_runs.assert_called_once()


@patch("app.telemetry_db._get_client")
def test_fetch_prompts_success(mock_get_client):
    from unittest.mock import MagicMock

    mock_supabase = MagicMock()
    mock_get_client.return_value = mock_supabase

    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table

    mock_select = MagicMock()
    mock_table.select.return_value = mock_select

    mock_execute = MagicMock()
    mock_select.execute.return_value = mock_execute

    mock_execute.data = [{"id": "prompt-1", "name": "System Prompt"}]

    response = client.get("/api/admin/prompts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "prompt-1"
    mock_supabase.table.assert_called_once_with("prompt_versions")


@patch("app.telemetry_db._get_client")
def test_list_staging_queue_success(mock_get_client):
    from unittest.mock import MagicMock

    mock_supabase = MagicMock()
    mock_get_client.return_value = mock_supabase
    chain = mock_supabase.table.return_value
    chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "stg-1", "source_url": "https://example.com/x", "quality_score": 42}
    ]

    response = client.get("/api/admin/staging?status=pending")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "stg-1"
    mock_supabase.table.assert_called_once_with("staging_quality_queue")


@patch("app.telemetry_db._get_client")
def test_review_staging_item_approve(mock_get_client):
    from unittest.mock import MagicMock

    mock_supabase = MagicMock()
    mock_get_client.return_value = mock_supabase
    update_call = mock_supabase.table.return_value.update
    update_call.return_value.eq.return_value.execute.return_value.data = [{"id": "stg-1"}]

    response = client.post(
        "/api/admin/staging/stg-1/review", json={"action": "approve", "notes": "looks fine"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    update_call.assert_called_once()
    payload = update_call.call_args[0][0]
    assert payload["status"] == "approved"
    assert payload["reviewer_notes"] == "looks fine"


@patch("app.telemetry_db._get_client")
def test_review_staging_item_not_found(mock_get_client):
    from unittest.mock import MagicMock

    mock_supabase = MagicMock()
    mock_get_client.return_value = mock_supabase
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = []

    response = client.post("/api/admin/staging/missing/review", json={"action": "reject"})
    assert response.status_code == 404


@patch("app.telemetry_db._get_client")
def test_reject_okf_entry_reads_notes_from_json_body(mock_get_client):
    """Regression: reviewer_notes used to be an unannotated query param, so a
    JSON body (what the frontend actually sends) never reached it and every
    rejection silently recorded reviewer_notes=None."""
    from unittest.mock import MagicMock

    mock_supabase = MagicMock()
    mock_get_client.return_value = mock_supabase
    update_call = mock_supabase.table.return_value.update
    update_call.return_value.eq.return_value.execute.return_value = MagicMock()

    response = client.post(
        "/api/admin/okf/review/rev-1/reject", json={"reviewer_notes": "not doctrinal"}
    )
    assert response.status_code == 200
    payload = update_call.call_args[0][0]
    assert payload["reviewer_notes"] == "not doctrinal"
