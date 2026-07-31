"""Unit tests for services.healing_course_service.

Covers every assignment trigger (consecutive streak, 3-of-5 frequency,
escalation, repeated signal within 24h), the no-duplicate guarantee, signal
classification, and the settings-driven composition path.
"""

import time
from unittest.mock import MagicMock

import pytest

from services.healing_course_service import (
    DEFAULT_COURSE_SLUG,
    CourseTrigger,
    assign_course_if_needed,
    course_slug_for_signal,
    evaluate_course_trigger,
    maybe_assign_healing_course,
    suffering_signal_from_text,
    trigger_payload,
)


def _turn(level: int, signal: str = "general", ts: float | None = None) -> dict:
    return {
        "distress_level": level,
        "signal": signal,
        "timestamp": ts if ts is not None else time.time(),
    }


def _fake_supabase(active_course_data=None):
    mock = MagicMock()
    resp = MagicMock()
    resp.data = active_course_data
    mock.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        resp
    )
    return mock


# --- evaluate_course_trigger: no-trigger cases ---


def test_empty_history_no_trigger():
    assert evaluate_course_trigger([]) is None


def test_single_distress_turn_no_trigger():
    history = [_turn(2, "anxiety")]
    assert evaluate_course_trigger(history) is None


def test_single_distress_turn_with_calm_context_no_trigger():
    history = [_turn(0), _turn(1, "anxiety"), _turn(0)]
    assert evaluate_course_trigger(history) is None


# --- consecutive streak ---


def test_two_consecutive_distress_turns_triggers():
    history = [_turn(0), _turn(2, "grief"), _turn(3, "grief")]
    trigger = evaluate_course_trigger(history)
    assert trigger is not None
    assert trigger.pattern == "consecutive_2"
    assert trigger.signal == "grief"


def test_three_consecutive_distress_turns_triggers():
    # 3 distress turns also satisfy 3-of-5 frequency, which has higher
    # priority per the evaluator contract — the trigger reports freq_3_of_5.
    history = [_turn(0), _turn(1), _turn(2, "anxiety"), _turn(2, "anxiety")]
    trigger = evaluate_course_trigger(history)
    assert trigger is not None
    assert trigger.pattern == "freq_3_of_5"
    assert trigger.signal == "anxiety"


def test_streak_broken_by_calm_turn_no_trigger():
    # The two grief turns are >24h apart so the repeated-signal rule cannot
    # fire either.
    now = time.time()
    history = [
        _turn(2, "grief", ts=now - 30 * 3600),
        _turn(0, "general", ts=now - 29 * 3600),
        _turn(2, "grief", ts=now),
    ]
    assert evaluate_course_trigger(history) is None


# --- 3-of-5 frequency ---


def test_freq_3_of_5_triggers():
    history = [_turn(2, "anxiety"), _turn(0), _turn(1, "anxiety"), _turn(0), _turn(2, "anxiety")]
    trigger = evaluate_course_trigger(history)
    assert trigger is not None
    assert trigger.pattern == "freq_3_of_5"
    assert trigger.signal == "anxiety"


def test_freq_2_of_5_no_trigger():
    # Different signals keep the repeated-signal rule from firing.
    history = [
        _turn(2, "anxiety"),
        _turn(0),
        _turn(1, "grief"),
        _turn(0),
        _turn(0),
    ]
    assert evaluate_course_trigger(history) is None


def test_freq_outside_window_ignored():
    # 3 distress turns exist in history, but only 2 fall inside the last-5
    # window (and the old turns sit outside the 24h repeat window too).
    now = time.time()
    history = [
        _turn(2, "general", ts=now - 30 * 3600),
        _turn(2, "general", ts=now - 29 * 3600),
        _turn(0, "general", ts=now),
        _turn(1, "general", ts=now),
        _turn(0, "general", ts=now),
        _turn(0, "general", ts=now),
    ]
    assert evaluate_course_trigger(history) is None


# --- escalation ---


def test_escalation_triggers():
    history = [_turn(0), _turn(0), _turn(0), _turn(0), _turn(3, "loneliness")]
    trigger = evaluate_course_trigger(history)
    assert trigger is not None
    assert trigger.pattern == "escalation"
    assert trigger.signal == "loneliness"


def test_no_escalation_on_flat_severity():
    now = time.time()
    history = [
        _turn(0, "general", ts=now),
        _turn(0, "general", ts=now),
        _turn(1, "general", ts=now - 30 * 3600),
        _turn(0, "general", ts=now),
        _turn(2, "general", ts=now - 29 * 3600),
    ]
    assert evaluate_course_trigger(history) is None


# --- repeated signal within 24h ---


def test_repeated_signal_within_24h_triggers():
    now = time.time()
    history = [
        _turn(1, "anxiety", ts=now - 3600),
        _turn(0, "general", ts=now - 1800),
        _turn(2, "anxiety", ts=now - 100),
    ]
    trigger = evaluate_course_trigger(history)
    assert trigger is not None
    assert trigger.pattern == "repeated_signal"
    assert trigger.signal == "anxiety"


def test_repeated_signal_older_than_24h_no_trigger():
    now = time.time()
    history = [
        _turn(1, "anxiety", ts=now - 30 * 3600),
        _turn(0, "general", ts=now - 29 * 3600),
        _turn(2, "anxiety", ts=now - 28 * 3600),
    ]
    trigger = evaluate_course_trigger(history)
    assert trigger is None or trigger.pattern != "repeated_signal"


# --- signal classification & slug mapping ---


@pytest.mark.parametrize(
    "text,signal",
    [
        ("I am grieving my mother", "grief"),
        ("I keep worrying about everything", "anxiety"),
        ("I feel so angry at my brother", "anger"),
        ("I feel so alone these days", "loneliness"),
        ("Nothing has meaning anymore", "meaninglessness"),
        ("Namaste, what is the beautiful state?", "general"),
        ("", "general"),
    ],
)
def test_suffering_signal_from_text(text, signal):
    assert suffering_signal_from_text(text) == signal


def test_signal_from_detected_signals_fallback():
    assert suffering_signal_from_text("", ["panic attack"]) == "anxiety"
    assert suffering_signal_from_text("", ["Persistent distress over rolling window"]) == "general"


@pytest.mark.parametrize(
    "signal,slug",
    [
        ("grief", "walking-through-grief"),
        ("loneliness", "walking-through-grief"),
        ("anxiety", "quieting-anxiety"),
        ("anger", "dissolving-conflict"),
        ("meaninglessness", "end-of-suffering"),
        ("general", "end-of-suffering"),
        ("unknown-signal", DEFAULT_COURSE_SLUG),
    ],
)
def test_course_slug_for_signal(signal, slug):
    assert course_slug_for_signal(signal) == slug


# --- assignment: no duplicate when active course exists ---


@pytest.mark.asyncio
async def test_no_duplicate_assignment_when_active_course_exists():
    supabase = _fake_supabase(active_course_data=[{"course_slug": "quieting-anxiety"}])
    trigger = CourseTrigger(signal="anxiety", pattern="consecutive_2", reason="test")

    result = await assign_course_if_needed(supabase, "user-1", trigger)

    assert result is None
    supabase.table.return_value.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_assign_writes_course_and_returns_payload():
    supabase = _fake_supabase(active_course_data=None)
    trigger = CourseTrigger(signal="grief", pattern="freq_3_of_5", reason="distress in 3 of last 5")

    result = await assign_course_if_needed(supabase, "user-1", trigger)

    assert result is not None
    assert result["slug"] == "walking-through-grief"
    assert result["trigger"] == trigger
    row = supabase.table.return_value.upsert.call_args.args[0]
    assert row["user_id"] == "user-1"
    assert row["course_slug"] == "walking-through-grief"
    assert row["status"] == "active"
    assert row["completed_lessons"] == []
    assert row["current_lesson_index"] == 0
    assert row["assigned_reason"] == "distress in 3 of last 5"
    assert row["trigger_signal"] == "grief"


@pytest.mark.asyncio
async def test_assign_skips_anonymous_user():
    supabase = _fake_supabase(active_course_data=None)
    trigger = CourseTrigger(signal="anxiety", pattern="consecutive_2", reason="test")

    result = await assign_course_if_needed(supabase, "anonymous", trigger)

    assert result is None
    supabase.table.assert_not_called()


@pytest.mark.asyncio
async def test_assign_returns_none_when_supabase_missing():
    trigger = CourseTrigger(signal="anxiety", pattern="consecutive_2", reason="test")
    assert await assign_course_if_needed(None, "user-1", trigger) is None


@pytest.mark.asyncio
async def test_assign_returns_none_on_db_error():
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = Exception("Supabase down")

    result = await assign_course_if_needed(supabase, "user-1", CourseTrigger("anxiety", "consecutive_2", "test"))

    assert result is None


# --- composed path: settings-driven thresholds ---


@pytest.mark.asyncio
async def test_maybe_assign_uses_settings_thresholds(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "proactive_course_assignment_enabled", True)
    monkeypatch.setattr(settings, "proactive_course_consecutive_threshold", 2)
    monkeypatch.setattr(settings, "proactive_course_frequency_threshold", 3)
    monkeypatch.setattr(settings, "proactive_course_frequency_window", 5)
    monkeypatch.setattr(settings, "proactive_course_repeat_window_hours", 24)

    supabase = _fake_supabase(active_course_data=None)
    history = [_turn(0), _turn(2, "anger"), _turn(3, "anger")]

    result = await maybe_assign_healing_course(supabase, "user-1", history)

    assert result is not None
    assert result["slug"] == "dissolving-conflict"


@pytest.mark.asyncio
async def test_maybe_assign_no_trigger_no_db_call(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "proactive_course_assignment_enabled", True)
    supabase = _fake_supabase(active_course_data=None)
    history = [_turn(0), _turn(0)]

    result = await maybe_assign_healing_course(supabase, "user-1", history)

    assert result is None
    supabase.table.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_assign_disabled_flag(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "proactive_course_assignment_enabled", False)
    supabase = _fake_supabase(active_course_data=None)
    history = [_turn(2, "anxiety"), _turn(3, "anxiety")]

    result = await maybe_assign_healing_course(supabase, "user-1", history)

    assert result is None
    supabase.table.assert_not_called()


# --- payload helper ---


def test_trigger_payload_is_json_safe():
    trigger = CourseTrigger(signal="grief", pattern="consecutive_2", reason="2 consecutive distress turns")
    payload = trigger_payload(trigger, "walking-through-grief")
    assert payload == {
        "slug": "walking-through-grief",
        "signal": "grief",
        "pattern": "consecutive_2",
        "reason": "2 consecutive distress turns",
    }
