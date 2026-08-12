"""Tests for Task 4 admin write endpoints.

Covers promote/demote admin, alert-rule upsert/delete, prompt activation,
golden-question upsert/delete, generic reingest, and logs list.
All endpoints must enforce both `_require_admin` (superuser) and AAL2.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app, get_current_user_from_supabase
from services.auth_service import require_aal2

client = TestClient(app)


def _set_user(user: dict | None):
    if user is None:
        async def no_user():
            raise HTTPException(status_code=401, detail="Authentication required")

        app.dependency_overrides[get_current_user_from_supabase] = no_user
    else:
        async def fixed_user():
            return user

        app.dependency_overrides[get_current_user_from_supabase] = fixed_user


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_current_user_from_supabase, None)
    from app.dependencies import get_container
    app.dependency_overrides.pop(get_container, None)
    # Reset shared admin rate limiter state so tests do not 429 each other.
    from app.main import _ADMIN_RATE_LIMITER
    for _lim in (_ADMIN_RATE_LIMITER, getattr(_ADMIN_RATE_LIMITER, "_fallback", None)):
        if _lim is None:
            continue
        if hasattr(_lim, "_store"):
            _lim._store.clear()
        if hasattr(_lim, "_attempts"):
            _lim._attempts.clear()
    _redis = getattr(_ADMIN_RATE_LIMITER, "_redis", None)
    if _redis is not None:
        _kwargs = getattr(getattr(_redis, "connection_pool", None), "connection_kwargs", {}) or {}
        _host = str(_kwargs.get("host", "")).lower()
        _db = int(_kwargs.get("db", 0) or 0)
        if _db >= 1 or _host in ("localhost", "127.0.0.1", "::1"):
            try:
                for key in _redis.scan_iter("rl:*", count=100):
                    _redis.delete(key)
            except Exception:
                pass


@pytest.fixture
def normal_user():
    return {"id": "user-1", "email": "user@example.com", "is_superuser": False, "aal": "aal2"}


@pytest.fixture
def admin_user():
    return {"id": "admin-1", "email": "admin@example.com", "is_superuser": True, "aal": "aal2"}


@pytest.fixture
def admin_user_aal1():
    return {"id": "admin-1", "email": "admin@example.com", "is_superuser": True, "aal": "aal1"}


def _build_chain_mock():
    """Build a mock object that supports fluent .table().select().eq().limit().execute() chains."""
    return MagicMock()


def _mock_supabase_client():
    """Return a MagicMock configured with the common .table().select().eq().limit().execute() chain."""
    mock_client = MagicMock()

    def _make_return(value):
        m = MagicMock()
        for name in ("eq", "neq", "gte", "lte", "ilike", "limit", "order", "select", "insert", "update", "delete"):
            getattr(m, name).return_value = m
        m.execute.return_value = value
        return m

    # Default chain returns empty data on execute.
    empty_resp = MagicMock()
    empty_resp.data = []
    default_chain = _make_return(empty_resp)
    mock_client.table.return_value = default_chain
    return mock_client


# -----------------------------------------------------------------------------
# Structural: every new endpoint resolves to require_aal2
# -----------------------------------------------------------------------------


def _resolved_dep_names(func) -> set[str]:
    import inspect

    names: set[str] = set()
    for param in inspect.signature(func).parameters.values():
        dep = getattr(param.default, "dependency", None)
        if dep is None:
            continue
        name = getattr(dep, "__name__", str(dep))
        if name == "_require_admin":
            inner = getattr(inspect.signature(dep).parameters["user"].default, "dependency", None)
            name = getattr(inner, "__name__", str(inner))
        names.add(name)
    return names


@pytest.mark.parametrize(
    "endpoint_name",
    [
        "promote_admin",
        "demote_admin",
        "upsert_alert_rule",
        "delete_alert_rule",
        "activate_prompt_version",
        "upsert_golden_question",
        "delete_golden_question",
        "admin_reingest",
        "list_admin_logs",
    ],
)
def test_new_admin_endpoints_resolve_to_require_aal2(endpoint_name):
    import importlib

    mod = importlib.import_module("app.api.admin")
    fn = getattr(mod, endpoint_name)
    deps = _resolved_dep_names(fn)
    assert require_aal2.__name__ in deps, (
        f"REGRESSION: app.api.admin.{endpoint_name} must depend on require_aal2 "
        f"(resolved deps: {sorted(deps)})"
    )


# -----------------------------------------------------------------------------
# Promote admin
# -----------------------------------------------------------------------------


def test_promote_admin_forbidden_for_non_admin(normal_user):
    _set_user(normal_user)
    res = client.post("/api/admin/admins/promote", json={"email": "x@y.com"})
    assert res.status_code == 403


def test_promote_admin_requires_aal2(admin_user_aal1):
    _set_user(admin_user_aal1)
    res = client.post("/api/admin/admins/promote", json={"email": "x@y.com"})
    assert res.status_code == 403


@patch("app.telemetry_db._get_client")
def test_promote_admin_success(mock_get_client, admin_user):
    _set_user(admin_user)
    mock_client = _mock_supabase_client()
    mock_get_client.return_value = mock_client

    # auth_users lookup returns the target user id
    auth_resp = MagicMock()
    auth_resp.data = [{"id": "target-user-id"}]
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = auth_resp

    # user_roles existing check returns empty
    existing_resp = MagicMock()
    existing_resp.data = []
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = existing_resp

    insert_resp = MagicMock()
    insert_resp.data = [{"id": "role-id"}]
    mock_client.table.return_value.insert.return_value.execute.return_value = insert_resp

    res = client.post("/api/admin/admins/promote", json={"email": "target@example.com"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["user_id"] == "target-user-id"


@patch("app.telemetry_db._get_client")
def test_promote_admin_already_admin(mock_get_client, admin_user):
    _set_user(admin_user)
    mock_client = _mock_supabase_client()
    mock_get_client.return_value = mock_client

    auth_resp = MagicMock()
    auth_resp.data = [{"id": "target-user-id"}]
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = auth_resp

    existing_resp = MagicMock()
    existing_resp.data = [{"id": "existing-role"}]
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = existing_resp

    res = client.post("/api/admin/admins/promote", json={"email": "target@example.com"})
    assert res.status_code == 200
    assert res.json()["message"] == "User is already an admin"


# -----------------------------------------------------------------------------
# Demote admin
# -----------------------------------------------------------------------------


def test_demote_admin_forbidden_for_non_admin(normal_user):
    _set_user(normal_user)
    res = client.post("/api/admin/admins/demote", json={"user_id": "target-user-id"})
    assert res.status_code == 403


def test_demote_admin_requires_aal2(admin_user_aal1):
    _set_user(admin_user_aal1)
    res = client.post("/api/admin/admins/demote", json={"user_id": "target-user-id"})
    assert res.status_code == 403


@patch("app.telemetry_db._get_client")
def test_demote_admin_success(mock_get_client, admin_user):
    _set_user(admin_user)
    mock_client = _mock_supabase_client()
    mock_get_client.return_value = mock_client

    delete_resp = MagicMock()
    delete_resp.data = [{"id": "deleted-role"}]
    mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = delete_resp

    res = client.post("/api/admin/admins/demote", json={"user_id": "target-user-id"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["user_id"] == "target-user-id"


# -----------------------------------------------------------------------------
# Alert rules
# -----------------------------------------------------------------------------


def test_upsert_alert_rule_forbidden_for_non_admin(normal_user):
    _set_user(normal_user)
    res = client.post(
        "/api/admin/alert-rules",
        json={"name": "rule", "metric": "error_rate", "comparator": ">", "threshold": 0.5},
    )
    assert res.status_code == 403


def test_upsert_alert_rule_requires_aal2(admin_user_aal1):
    _set_user(admin_user_aal1)
    res = client.post(
        "/api/admin/alert-rules",
        json={"name": "rule", "metric": "error_rate", "comparator": ">", "threshold": 0.5},
    )
    assert res.status_code == 403


@patch("app.telemetry_db._get_client")
def test_upsert_alert_rule_create(mock_get_client, admin_user):
    _set_user(admin_user)
    mock_client = _mock_supabase_client()
    mock_get_client.return_value = mock_client

    insert_resp = MagicMock()
    insert_resp.data = [{"id": "new-rule-id"}]
    mock_client.table.return_value.insert.return_value.execute.return_value = insert_resp

    res = client.post(
        "/api/admin/alert-rules",
        json={"name": "rule", "metric": "error_rate", "comparator": ">", "threshold": 0.5},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["ok"] is True
    assert data["id"] == "new-rule-id"


@patch("app.telemetry_db._get_client")
def test_delete_alert_rule_success(mock_get_client, admin_user):
    _set_user(admin_user)
    mock_client = _mock_supabase_client()
    mock_get_client.return_value = mock_client

    mock_client.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

    res = client.delete("/api/admin/alert-rules/rule-1")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_delete_alert_rule_forbidden_for_non_admin(normal_user):
    _set_user(normal_user)
    res = client.delete("/api/admin/alert-rules/rule-1")
    assert res.status_code == 403


# -----------------------------------------------------------------------------
# Prompt activation
# -----------------------------------------------------------------------------


def test_activate_prompt_forbidden_for_non_admin(normal_user):
    _set_user(normal_user)
    res = client.post("/api/admin/prompts/prompt-1/activate")
    assert res.status_code == 403


def test_activate_prompt_requires_aal2(admin_user_aal1):
    _set_user(admin_user_aal1)
    res = client.post("/api/admin/prompts/prompt-1/activate")
    assert res.status_code == 403


@patch("app.telemetry_db._get_client")
def test_activate_prompt_success(mock_get_client, admin_user):
    _set_user(admin_user)
    mock_client = _mock_supabase_client()
    mock_get_client.return_value = mock_client

    target_resp = MagicMock()
    target_resp.data = [{"name": "system-prompt"}]
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = target_resp

    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

    res = client.post("/api/admin/prompts/prompt-1/activate")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["id"] == "prompt-1"


# -----------------------------------------------------------------------------
# Golden questions
# -----------------------------------------------------------------------------


def test_upsert_golden_question_forbidden_for_non_admin(normal_user):
    _set_user(normal_user)
    res = client.post(
        "/api/admin/golden-questions",
        json={"question": "What is meditation?", "active": True},
    )
    assert res.status_code == 403


def test_upsert_golden_question_requires_aal2(admin_user_aal1):
    _set_user(admin_user_aal1)
    res = client.post(
        "/api/admin/golden-questions",
        json={"question": "What is meditation?", "active": True},
    )
    assert res.status_code == 403


@patch("app.telemetry_db._get_client")
def test_upsert_golden_question_create(mock_get_client, admin_user):
    _set_user(admin_user)
    mock_client = _mock_supabase_client()
    mock_get_client.return_value = mock_client

    insert_resp = MagicMock()
    insert_resp.data = [{"id": "new-gq-id"}]
    mock_client.table.return_value.insert.return_value.execute.return_value = insert_resp

    res = client.post(
        "/api/admin/golden-questions",
        json={"question": "What is meditation?", "tags": ["intro"], "active": True},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["ok"] is True
    assert data["id"] == "new-gq-id"


@patch("app.telemetry_db._get_client")
def test_delete_golden_question_success(mock_get_client, admin_user):
    _set_user(admin_user)
    mock_client = _mock_supabase_client()
    mock_get_client.return_value = mock_client

    mock_client.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

    res = client.delete("/api/admin/golden-questions/gq-1")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_delete_golden_question_forbidden_for_non_admin(normal_user):
    _set_user(normal_user)
    res = client.delete("/api/admin/golden-questions/gq-1")
    assert res.status_code == 403


# -----------------------------------------------------------------------------
# Reingest
# -----------------------------------------------------------------------------


def test_reingest_forbidden_for_non_admin(normal_user):
    _set_user(normal_user)
    res = client.post("/api/admin/reingest", json={"source": "https://example.com", "mode": "url"})
    assert res.status_code == 403


def test_reingest_requires_aal2(admin_user_aal1):
    _set_user(admin_user_aal1)
    res = client.post("/api/admin/reingest", json={"source": "https://example.com", "mode": "url"})
    assert res.status_code == 403


@patch("app.api.admin._validate_and_normalize")
@patch("app.api.admin.ingest_url_task")
def test_reingest_url_success(mock_task, mock_validate, admin_user):
    _set_user(admin_user)
    from app.dependencies import get_container
    from types import SimpleNamespace
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(redis_client=None)

    mock_validate.return_value = "https://example.com/normalized"
    mock_task.delay.return_value.id = "task-123"

    res = client.post("/api/admin/reingest", json={"source": "https://example.com", "mode": "url"})
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "url"
    assert data["task_id"] == "task-123"


def test_reingest_invalid_mode(admin_user):
    _set_user(admin_user)
    from app.dependencies import get_container
    from types import SimpleNamespace
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(redis_client=None)
    res = client.post("/api/admin/reingest", json={"source": "x", "mode": "invalid"})
    assert res.status_code == 422


# -----------------------------------------------------------------------------
# Logs
# -----------------------------------------------------------------------------


def test_list_logs_forbidden_for_non_admin(normal_user):
    _set_user(normal_user)
    res = client.get("/api/admin/logs")
    assert res.status_code == 403


def test_list_logs_requires_aal2(admin_user_aal1):
    _set_user(admin_user_aal1)
    res = client.get("/api/admin/logs")
    assert res.status_code == 403


@patch("app.telemetry_db._get_client")
def test_list_logs_success(mock_get_client, admin_user):
    _set_user(admin_user)
    mock_client = _mock_supabase_client()
    mock_get_client.return_value = mock_client

    logs_resp = MagicMock()
    logs_resp.data = [{"id": 1, "level": "info", "message": "hello", "request_id": "r1", "created_at": "2026-01-01T00:00:00Z"}]
    mock_client.table.return_value.select.return_value.gte.return_value.lte.return_value.eq.return_value.ilike.return_value.order.return_value.limit.return_value.execute.return_value = logs_resp

    res = client.get("/api/admin/logs?level=info&search=hello")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert data[0]["message"] == "hello"


# -----------------------------------------------------------------------------
# Allowlist defense-in-depth
# -----------------------------------------------------------------------------


def test_promote_admin_denied_when_not_allowlisted(monkeypatch, admin_user):
    allowlisted = "00000000-0000-0000-0000-0000000000aa"
    monkeypatch.setattr(settings, "admin_user_ids", allowlisted)
    _set_user({**admin_user, "id": "99999999-9999-9999-9999-999999999999"})
    res = client.post("/api/admin/admins/promote", json={"email": "x@y.com"})
    assert res.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
