"""Tests for GET /api/metrics (backend metrics endpoint)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from services.auth_service import get_current_user_from_supabase

client = TestClient(app)


def _fake_table(name: str) -> MagicMock:
    """Return a supabase table builder with canned responses per table."""
    table = MagicMock()
    if name == "user_course_progress":
        table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        return table
    response = MagicMock()
    response.count = 3 if name == "conversations" else 5
    response.data = (
        [{"duration_seconds": 60}, {"duration_seconds": 120}]
        if name == "meditation_sessions"
        else []
    )
    table.select.return_value.eq.return_value.execute.return_value = response
    return table


def _fake_supabase_client(*_args, **_kwargs) -> MagicMock:
    client_mock = MagicMock()
    client_mock.table.side_effect = _fake_table
    return client_mock


def _override_user(user: dict | None) -> None:
    if user is None:
        async def reject():
            raise HTTPException(status_code=401, detail="Authentication required or session expired")

        app.dependency_overrides[get_current_user_from_supabase] = reject
    else:
        async def fixed_user():
            return user

        app.dependency_overrides[get_current_user_from_supabase] = fixed_user


def test_metrics_happy_path(monkeypatch):
    """Authenticated user gets aggregated metrics with the expected shape."""
    monkeypatch.setattr("supabase.create_client", _fake_supabase_client)
    monkeypatch.setattr("app.api.metrics.settings.supabase_url", "https://mock.supabase.co")
    monkeypatch.setattr("app.api.metrics.settings.supabase_key", "mock-key")
    _override_user({"id": "user-123", "email": "u@example.com", "is_anonymous": False})
    try:
        response = client.get("/api/metrics")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data == {
            "total_conversations": 3,
            "total_messages": 5,
            "total_meditation_minutes": 3.0,
            "average_distress_level": None,
            "distress_trend": "flat",
            "active_healing_course": None,
            "course_completion_percent": 0.0,
            "last_active_at": None,
        }
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


def test_metrics_anonymous_returns_zeros(monkeypatch):
    """Dev-mode anonymous fallback yields a zeroed payload instead of crashing."""
    monkeypatch.setattr("supabase.create_client", _fake_supabase_client)
    _override_user({"id": "anonymous", "email": None, "is_anonymous": True})
    try:
        response = client.get("/api/metrics")
        assert response.status_code == 200, response.text
        assert response.json()["total_conversations"] == 0
        assert response.json()["total_messages"] == 0
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


def test_metrics_unauthenticated_rejected(monkeypatch):
    """Missing/invalid credentials must be rejected with 401, never 200."""
    monkeypatch.setattr("supabase.create_client", _fake_supabase_client)
    _override_user(None)
    try:
        response = client.get("/api/metrics")
        assert response.status_code == 401, response.text
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
