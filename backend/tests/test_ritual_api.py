"""Daily ritual API — deterministic teaching pick, streak transitions, Redis-down fallback.

Covers GET /api/ritual/today and POST /api/ritual/checkin (backend/app/api/ritual.py).
Auth is faked the same way test_healing_course_endpoint.py does it: FastAPI
dependency overrides on the shared app.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from services.auth_service import get_current_user_from_supabase, get_optional_user

client = TestClient(app)

# Fixed clock: every test sees the same UTC date, so a run crossing midnight
# cannot flip a streak assertion.
TODAY = "2026-10-04"
YESTERDAY = (date.fromisoformat(TODAY) - timedelta(days=1)).isoformat()
DAY_BEFORE = (date.fromisoformat(TODAY) - timedelta(days=2)).isoformat()

_AUTHED = {"id": "user-ritual-1", "email": "u@example.com", "is_anonymous": False}
_ANON = {"id": "anonymous", "email": None, "is_anonymous": True}
_KEY = "mukthiguru:ritual:streak:user-ritual-1"


class FakeRedis:
    """Minimal sync-redis stand-in: get/setex against a dict."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str):
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        self.ttls[key] = ttl
        return True


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("app.api.ritual._utc_today", lambda: TODAY)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_current_user_from_supabase, None)
    app.dependency_overrides.pop(get_optional_user, None)


def _override(dep, user) -> None:
    async def accept():
        return user

    app.dependency_overrides[dep] = accept


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("app.api.ritual._get_redis", lambda: fake)
    return fake


@pytest.fixture
def redis_down(monkeypatch):
    monkeypatch.setattr("app.api.ritual._get_redis", lambda: None)


def _seed(fake: FakeRedis, count: int, last_date: str) -> None:
    fake.store[_KEY] = json.dumps({"count": count, "last_date": last_date})


# --- Today's Teaching -------------------------------------------------------


def test_same_date_pick_is_deterministic(fake_redis):
    """Same UTC date must yield byte-identical teaching on every call."""
    _override(get_optional_user, _AUTHED)
    first = client.get("/api/ritual/today")
    second = client.get("/api/ritual/today")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["teaching"] == second.json()["teaching"]
    assert first.json()["date"] == TODAY


def test_teaching_is_verbatim_quote_with_provenance(fake_redis):
    """The served item must be a repo verbatim quote, not model output."""
    from app.api.ritual import _teaching_for

    teaching = _teaching_for(TODAY)
    assert teaching["kind"] == "verbatim_quote"
    assert teaching["attribution"] == "Sri Preethaji & Sri Krishnaji"
    assert teaching["speaker"]
    assert 30 <= len(teaching["text"]) <= 400
    assert "youtube.com/watch?v=" in teaching["url"]
    assert "&t=" in teaching["url"]  # per-quote start offset preserved


def test_pick_covers_pool_and_stays_stable(fake_redis):
    """Date-seeded index is a pure function of the date string."""
    from app.api.ritual import _teaching_for, _teaching_pool

    pool = _teaching_pool()
    assert len(pool) >= 5
    picks = {
        _teaching_for((date(2026, 1, 1) + timedelta(days=i)).isoformat())["text"] for i in range(60)
    }
    assert picks <= {item["text"] for item in pool}
    assert _teaching_for(TODAY) == _teaching_for(TODAY)


def test_missing_artifact_falls_back_to_practice_copy(monkeypatch):
    """No OKF artifact → product-approved practice copy, honestly labelled."""
    from app.api.ritual import _teaching_for, _teaching_pool

    monkeypatch.setattr("app.api.ritual._load_verbatim_quotes", lambda: [])
    _teaching_pool.cache_clear()
    try:
        teaching = _teaching_for(TODAY)
        assert teaching["kind"] == "practice_prompt"
        assert teaching["attribution"] == "AskMukthiGuru practice guide"
        assert "Sri Preethaji" not in teaching["attribution"]
        assert teaching["text"]
    finally:
        _teaching_pool.cache_clear()


def test_get_today_without_session_has_teaching_and_null_streak(fake_redis):
    """Public read: teaching always served, streak null (not 0) when unknown."""
    _override(get_optional_user, _ANON)
    res = client.get("/api/ritual/today")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["teaching"]["text"]
    assert body["streak"] is None
    assert body["checked_in_today"] is False


def test_get_today_reports_checked_in_state(fake_redis):
    _override(get_optional_user, _AUTHED)
    _seed(fake_redis, count=4, last_date=TODAY)
    body = client.get("/api/ritual/today").json()
    assert body["streak"] == 4
    assert body["checked_in_today"] is True
    assert body["last_date"] == TODAY


def test_get_today_streak_breaks_after_gap(fake_redis):
    """A stale last_date is an honest 0, not a carried-over count."""
    _override(get_optional_user, _AUTHED)
    _seed(fake_redis, count=9, last_date=DAY_BEFORE)
    body = client.get("/api/ritual/today").json()
    assert body["streak"] == 0
    assert body["checked_in_today"] is False


# --- Streak transitions -----------------------------------------------------


def test_first_checkin_starts_streak_at_one(fake_redis):
    _override(get_current_user_from_supabase, _AUTHED)
    res = client.post("/api/ritual/checkin")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["streak"] == 1
    assert body["last_date"] == TODAY
    assert body["teaching"]["text"]
    assert fake_redis.ttls[_KEY] == 400 * 24 * 60 * 60  # 400-day TTL
    assert json.loads(fake_redis.store[_KEY]) == {"count": 1, "last_date": TODAY}


def test_yesterday_checkin_increments(fake_redis):
    _override(get_current_user_from_supabase, _AUTHED)
    _seed(fake_redis, count=3, last_date=YESTERDAY)
    body = client.post("/api/ritual/checkin").json()
    assert body["streak"] == 4
    assert body["last_date"] == TODAY


def test_gap_checkin_resets_to_one(fake_redis):
    _override(get_current_user_from_supabase, _AUTHED)
    _seed(fake_redis, count=7, last_date=DAY_BEFORE)
    body = client.post("/api/ritual/checkin").json()
    assert body["streak"] == 1
    assert body["last_date"] == TODAY


def test_same_day_checkin_is_noop(fake_redis):
    _override(get_current_user_from_supabase, _AUTHED)
    _seed(fake_redis, count=5, last_date=TODAY)
    body = client.post("/api/ritual/checkin").json()
    assert body["streak"] == 5
    assert body["last_date"] == TODAY
    assert json.loads(fake_redis.store[_KEY])["count"] == 5  # not double-counted


def test_unreadable_streak_state_recovers_as_new_streak(fake_redis):
    _override(get_current_user_from_supabase, _AUTHED)
    fake_redis.store[_KEY] = "{not-json"
    body = client.post("/api/ritual/checkin").json()
    assert body["streak"] == 1


# --- Redis-down fallback ----------------------------------------------------


def test_get_today_redis_down_never_500(redis_down):
    _override(get_optional_user, _AUTHED)
    res = client.get("/api/ritual/today")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["teaching"]["text"]
    assert body["streak"] is None
    assert body["last_date"] is None


def test_checkin_redis_down_returns_teaching_with_null_streak(redis_down):
    _override(get_current_user_from_supabase, _AUTHED)
    res = client.post("/api/ritual/checkin")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["teaching"]["text"]
    assert body["streak"] is None
    assert body["last_date"] is None
    assert body["checked_in_today"] is False


def test_redis_read_error_is_swallowed(monkeypatch):
    """A failing GET on a live client degrades to streak=null, not a 500."""
    _override(get_optional_user, _AUTHED)

    class BrokenRedis:
        def get(self, key):
            raise ConnectionError("redis gone")

        def setex(self, key, ttl, value):
            raise ConnectionError("redis gone")

    monkeypatch.setattr("app.api.ritual._get_redis", lambda: BrokenRedis())
    res = client.get("/api/ritual/today")
    assert res.status_code == 200, res.text
    assert res.json()["streak"] is None


# --- Auth -------------------------------------------------------------------


def test_checkin_requires_auth():
    async def reject():
        raise HTTPException(status_code=401, detail="Authentication required or session expired")

    app.dependency_overrides[get_current_user_from_supabase] = reject
    res = client.post("/api/ritual/checkin")
    assert res.status_code == 401, res.text
    assert "teaching" not in res.json()


def test_checkin_rejects_anonymous_identity():
    """Dev-mode anonymous fallback must never mint a shared streak."""
    _override(get_current_user_from_supabase, _ANON)
    res = client.post("/api/ritual/checkin")
    assert res.status_code == 401, res.text
