"""Tests for the healing-course API routes (POST /api/healing-course/*)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from services.auth_service import get_current_user_from_supabase

client = TestClient(app)


def _fake_supabase(active_course: dict | None = None) -> MagicMock:
    """A supabase client whose active-course lookup returns the given row."""
    client_mock = MagicMock()
    table = MagicMock()
    active_check = (
        table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value
    )
    active_check.data = active_course
    client_mock.table.return_value = table
    return client_mock


def _patch_supabase(monkeypatch, active_course: dict | None = None) -> MagicMock:
    fake = _fake_supabase(active_course)
    monkeypatch.setattr("supabase.create_client", lambda *_a, **_k: fake)
    monkeypatch.setattr("app.api.healing_course.settings.supabase_url", "https://mock.supabase.co")
    monkeypatch.setattr("app.api.healing_course.settings.supabase_key", "mock-key")
    return fake


def _override_user(user: dict | None) -> None:
    if user is None:
        async def reject():
            raise HTTPException(status_code=401, detail="Authentication required or session expired")

        app.dependency_overrides[get_current_user_from_supabase] = reject
    else:
        async def fixed_user():
            return user

        app.dependency_overrides[get_current_user_from_supabase] = fixed_user


_AUTHED = {"id": "user-123", "email": "u@example.com", "is_anonymous": False}
_ANON = {"id": "anonymous", "email": None, "is_anonymous": True}

_DISTRESS_HISTORY = [
    {"distress_level": 2, "signal": "anxiety", "timestamp": 1000.0},
    {"distress_level": 2, "signal": "anxiety", "timestamp": 2000.0},
]


def test_assign_unauthenticated_rejected(monkeypatch):
    """Missing/invalid credentials must be rejected with 401, never 200."""
    monkeypatch.setattr("supabase.create_client", lambda *_a, **_k: _fake_supabase())
    _override_user(None)
    try:
        response = client.post("/api/healing-course/assign", json={"history": _DISTRESS_HISTORY})
        assert response.status_code == 401, response.text
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


def test_assign_happy_path(monkeypatch):
    """Distress trigger fires and a course is assigned to the user."""
    fake = _patch_supabase(monkeypatch, active_course=None)
    _override_user(_AUTHED)
    try:
        response = client.post("/api/healing-course/assign", json={"history": _DISTRESS_HISTORY})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["assigned"] is True
        assert data["course"]["slug"] == "quieting-anxiety"
        assert data["course"]["trigger"]["signal"] == "anxiety"
        row = fake.table.return_value.upsert.call_args[0][0]
        assert row["user_id"] == "user-123"
        assert row["course_slug"] == "quieting-anxiety"
        assert row["status"] == "active"
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


def test_assign_no_trigger(monkeypatch):
    """Calm history produces no assignment."""
    fake = _patch_supabase(monkeypatch)
    _override_user(_AUTHED)
    try:
        response = client.post(
            "/api/healing-course/assign",
            json={"history": [{"distress_level": 0, "signal": "general"}]},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"assigned": False}
        fake.table.return_value.upsert.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


def test_assign_skips_when_active_course_exists(monkeypatch):
    """No-duplicate rule: an active course suppresses a second assignment."""
    fake = _patch_supabase(monkeypatch, active_course={"course_slug": "quieting-anxiety"})
    _override_user(_AUTHED)
    try:
        response = client.post("/api/healing-course/assign", json={"history": _DISTRESS_HISTORY})
        assert response.status_code == 200, response.text
        assert response.json() == {"assigned": False, "course": None}
        fake.table.return_value.upsert.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


def test_assign_anonymous_never_assigned(monkeypatch):
    """Anonymous (dev-mode fallback) identity gets no course."""
    _patch_supabase(monkeypatch)
    _override_user(_ANON)
    try:
        response = client.post("/api/healing-course/assign", json={"history": _DISTRESS_HISTORY})
        assert response.status_code == 200, response.text
        assert response.json() == {"assigned": False, "course": None}
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


def test_progress_happy_path(monkeypatch):
    """Progress upsert persists scoped to the caller's user_id."""
    fake = _patch_supabase(monkeypatch)
    _override_user(_AUTHED)
    try:
        response = client.post(
            "/api/healing-course/progress",
            json={
                "course_slug": "quieting-anxiety",
                "completed_lessons": ["ax-1"],
                "current_lesson_index": 1,
                "status": "active",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"ok": True}
        table = fake.table.return_value
        row = table.upsert.call_args[0][0]
        assert row["user_id"] == "user-123"
        assert row["course_slug"] == "quieting-anxiety"
        assert row["completed_lessons"] == ["ax-1"]
        assert row["current_lesson_index"] == 1
        assert row["status"] == "active"
        assert table.upsert.call_args[1]["on_conflict"] == "user_id,course_slug"
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


def test_progress_anonymous_rejected(monkeypatch):
    """Anonymous identity must not write to a shared progress row."""
    _patch_supabase(monkeypatch)
    _override_user(_ANON)
    try:
        response = client.post(
            "/api/healing-course/progress",
            json={"course_slug": "quieting-anxiety"},
        )
        assert response.status_code == 403, response.text
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


def test_progress_missing_course_slug_rejected(monkeypatch):
    """Missing required field yields 422, not a silent partial write."""
    _patch_supabase(monkeypatch)
    _override_user(_AUTHED)
    try:
        response = client.post("/api/healing-course/progress", json={})
        assert response.status_code == 422, response.text
    finally:
        app.dependency_overrides.pop(get_current_user_from_supabase, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
