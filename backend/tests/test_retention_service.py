"""Tests for retention_service.py — streak engine + lifecycle tracker.

Covers StreakEngine, _retention_curve, and RetentionService API shape.
"""

from __future__ import annotations

from datetime import date, timedelta

from services.retention_service import (
    STREAK_MILESTONES,
    StreakEngine,
    StreakState,
    _retention_curve,
)


def test_streak_starts_at_zero():
    eng = StreakEngine()
    s = StreakState()
    assert s.current == 0
    assert s.longest == 0
    assert s.total_days == 0


def test_first_practice_starts_streak():
    eng = StreakEngine()
    s = eng.record_practice(StreakState(), date(2026, 7, 1))
    assert s.current == 1
    assert s.longest == 1
    assert s.last_active == "2026-07-01"


def test_consecutive_day_increments():
    eng = StreakEngine()
    d = date(2026, 7, 1)
    s = eng.record_practice(StreakState(), d)
    s = eng.record_practice(s, d + timedelta(days=1))
    assert s.current == 2
    assert s.longest == 2


def test_freeze_consumed_on_one_day_gap():
    eng = StreakEngine()
    d = date(2026, 7, 1)
    s = eng.record_practice(StreakState(), d)
    s = eng.record_practice(s, d + timedelta(days=1))
    s = eng.record_practice(s, d + timedelta(days=3))
    assert s.current == 3
    assert s.freezes_available == 0


def test_long_gap_resets_streak():
    eng = StreakEngine()
    d = date(2026, 7, 1)
    s = eng.record_practice(StreakState(), d)
    s = eng.record_practice(s, d + timedelta(days=20))
    assert s.current == 1


def test_freeze_regenerates_after_14_days():
    eng = StreakEngine()
    d = date(2026, 7, 1)
    s = StreakState(freezes_available=0)
    for i in range(14):
        s = eng.record_practice(s, d + timedelta(days=i))
    assert s.freezes_available == 1


def test_latest_streak_updates():
    eng = StreakEngine()
    d = date(2026, 7, 1)
    s = eng.record_practice(StreakState(), d)
    s = eng.record_practice(s, d + timedelta(days=1))
    assert s.longest == 2
    s = eng.record_practice(s, d + timedelta(days=20))
    assert s.longest == 2


def test_at_risk_false_when_no_activity():
    eng = StreakEngine()
    assert not eng.at_risk(StreakState())


def test_at_risk_true_after_two_day_gap():
    eng = StreakEngine()
    d = date(2026, 7, 1)
    s = eng.record_practice(StreakState(), d)
    assert eng.at_risk(s, today=d + timedelta(days=2))


def test_at_risk_false_same_day():
    eng = StreakEngine()
    d = date(2026, 7, 1)
    s = eng.record_practice(StreakState(), d)
    assert not eng.at_risk(s, today=d)


def test_retention_curve_all_retained():
    signups = [{"user_id": "a", "ts": 0}, {"user_id": "b", "ts": 0}]
    activity = [
        {"user_id": "a", "ts": 2 * 86400},
        {"user_id": "b", "ts": 2 * 86400},
    ]
    curve = _retention_curve(signups, activity, horizons=(1, 7))
    assert curve[1] == 1.0
    assert curve[7] == 0.0


def test_retention_curve_half_retained():
    signups = [{"user_id": "a", "ts": 0}, {"user_id": "b", "ts": 0}]
    activity = [{"user_id": "a", "ts": 2 * 86400}]
    curve = _retention_curve(signups, activity, horizons=(1,))
    assert curve[1] == 0.5


def test_retention_curve_empty():
    curve = _retention_curve([], [])
    assert curve[1] == 0.0
    assert curve[7] == 0.0
    assert curve[30] == 0.0


def test_retention_curve_single_user():
    signups = [{"user_id": "a", "ts": 0}]
    activity = [{"user_id": "a", "ts": 8 * 86400}]
    curve = _retention_curve(signups, activity, horizons=(7, 30))
    assert curve[7] == 1.0
    assert curve[30] == 0.0


def test_duplicate_practice_same_day_does_not_increment():
    eng = StreakEngine()
    d = date(2026, 7, 1)
    s = eng.record_practice(StreakState(), d)
    before_current = s.current
    before_total = s.total_days
    s2 = eng.record_practice(s, d)
    assert s2.current == before_current
    assert s2.total_days == before_total


def test_milestones_are_spiritually_resonant():
    assert 3 in STREAK_MILESTONES
    assert 7 in STREAK_MILESTONES
    assert 40 in STREAK_MILESTONES
    assert 108 in STREAK_MILESTONES


def test_no_double_count_on_freeze_day():
    eng = StreakEngine()
    d = date(2026, 7, 1)
    s = eng.record_practice(StreakState(), d)
    s = eng.record_practice(s, d + timedelta(days=1))
    s = eng.record_practice(s, d + timedelta(days=3))
    s = eng.record_practice(s, d + timedelta(days=4))
    assert s.current == 4
    assert s.total_days == 4
