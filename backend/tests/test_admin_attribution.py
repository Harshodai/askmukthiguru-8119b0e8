import pytest
from fastapi.testclient import TestClient

from app.main import app, get_current_user_from_supabase

client = TestClient(app)


def mock_admin():
    return {
        "id": "admin-user-id",
        "email": "admin@example.com",
        "is_superuser": True,
        "aal": "aal2",
    }


@pytest.fixture(autouse=True)
def setup_admin():
    orig = app.dependency_overrides.get(get_current_user_from_supabase)
    app.dependency_overrides[get_current_user_from_supabase] = mock_admin
    yield
    if orig is not None:
        app.dependency_overrides[get_current_user_from_supabase] = orig
    else:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


def test_get_attribution_queue():
    res = client.get("/api/admin/attribution/queue")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    if data:
        item = data[0]
        assert "video_id" in item
        assert "title" in item
        assert "total_conflicts" in item
        assert "crossover_count" in item
        assert "third_party_count" in item
        assert "status" in item


def test_get_attribution_video_detail():
    # Video MmiI3xo5Ju4 has 25 conflicts
    res = client.get("/api/admin/attribution/video/MmiI3xo5Ju4")
    assert res.status_code == 200
    data = res.json()
    assert data["video_id"] == "MmiI3xo5Ju4"
    assert "turns" in data
    assert len(data["turns"]) == 25
    turn = data["turns"][0]
    assert "span_id" in turn
    assert "cosine" in turn
    assert "margin" in turn
    assert "category" in turn
    assert "dialogue_role" in turn


def test_triage_attribution_span():
    payload = {
        "action": "convert_to_context_header",
        "interlocutor_role": "guest_leader",
        "notes": "Tagging as context header",
    }
    res = client.post(
        "/api/admin/attribution/span/13c161b02e65e7382642b26a5e145e21d77dc47bdfdaff630c74cda39972a507/triage",
        json=payload,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["decision"] == "mark_unknown"


def test_batch_triage_video():
    payload = {
        "video_id": "MmiI3xo5Ju4",
        "action": "reject_all_devotees",
        "span_ids": ["13c161b02e65e7382642b26a5e145e21d77dc47bdfdaff630c74cda39972a507"],
        "notes": "Batch test",
    }
    res = client.post("/api/admin/attribution/video/MmiI3xo5Ju4/batch-triage", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["affected_spans_count"] == 1
