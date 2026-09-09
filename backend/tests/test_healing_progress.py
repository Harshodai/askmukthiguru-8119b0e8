"""Tests for healing course progression tracking and severity assessment.

Covers:
- assign_healing_course returns next step when progress exists
- Severity assessment maps to correct starting step
- Progress endpoint marks step completed
- Existing course not re-assigned
"""

import time
from unittest.mock import MagicMock

import pytest

from services.healing_course_service import (
    CourseTrigger,
    assess_severity,
    assign_course_if_needed,
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
    mock.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = resp
    return mock


# --- severity assessment ---


def test_assess_severity_empty_history():
    assert assess_severity(None) == "mild"
    assert assess_severity([]) == "mild"


def test_assess_severity_mild():
    history = [_turn(0), _turn(1, "anxiety"), _turn(0)]
    assert assess_severity(history) == "mild"


def test_assess_severity_moderate():
    history = [_turn(2, "anxiety"), _turn(0), _turn(2, "grief")]
    assert assess_severity(history) == "moderate"


def test_assess_severity_moderate_three():
    history = [_turn(1, "anger"), _turn(2, "anxiety"), _turn(1, "grief"), _turn(0)]
    assert assess_severity(history) == "moderate"


def test_assess_severity_severe():
    history = [_turn(3, "grief"), _turn(2, "anxiety"), _turn(2, "anger"), _turn(1, "loneliness")]
    assert assess_severity(history) == "severe"


# --- assign_course_if_needed: existing active course returns next step ---


@pytest.mark.asyncio
async def test_existing_active_course_returns_next_step():
    active_data = {
        "course_slug": "quieting-anxiety",
        "completed_lessons": ["ax-1"],
        "current_lesson_index": 1,
    }
    supabase = _fake_supabase(active_course_data=active_data)
    trigger = CourseTrigger(signal="anxiety", pattern="consecutive_2", reason="test")

    result = await assign_course_if_needed(supabase, "user-1", trigger)

    assert result is not None
    assert result["slug"] == "quieting-anxiety"
    assert result["already_active"] is True
    assert result["next_step"] == 1
    assert result["completed_lessons"] == ["ax-1"]
    supabase.table.return_value.upsert.assert_not_called()


# --- assign_course_if_needed: no active course assigns with severity ---


@pytest.mark.asyncio
async def test_new_assignment_includes_severity():
    supabase = _fake_supabase(active_course_data=None)
    trigger = CourseTrigger(signal="anxiety", pattern="freq_3_of_5", reason="distress in 3 of last 5")
    history = [_turn(2, "anxiety"), _turn(0), _turn(2, "anxiety")]

    result = await assign_course_if_needed(supabase, "user-1", trigger, history=history)

    assert result is not None
    assert result["slug"] == "quieting-anxiety"
    assert result["severity"] == "moderate"
    assert result["starting_step"] == 1
    row = supabase.table.return_value.upsert.call_args.args[0]
    assert row["current_lesson_index"] == 1


@pytest.mark.asyncio
async def test_severe_severity_starts_at_step_2():
    supabase = _fake_supabase(active_course_data=None)
    trigger = CourseTrigger(signal="grief", pattern="escalation", reason="escalating distress")
    history = [_turn(3, "grief"), _turn(3, "anxiety"), _turn(2, "anger"), _turn(2, "loneliness")]

    result = await assign_course_if_needed(supabase, "user-1", trigger, history=history)

    assert result is not None
    assert result["severity"] == "severe"
    assert result["starting_step"] == 2


@pytest.mark.asyncio
async def test_mild_severity_starts_at_step_0():
    supabase = _fake_supabase(active_course_data=None)
    trigger = CourseTrigger(signal="anxiety", pattern="consecutive_2", reason="test")
    history = [_turn(1, "anxiety")]

    result = await assign_course_if_needed(supabase, "user-1", trigger, history=history)

    assert result is not None
    assert result["severity"] == "mild"
    assert result["starting_step"] == 0


# --- no duplicate assignment ---


@pytest.mark.asyncio
async def test_no_duplicate_assignment():
    supabase = _fake_supabase(active_course_data={"course_slug": "walking-through-grief", "completed_lessons": [], "current_lesson_index": 0})
    trigger = CourseTrigger(signal="grief", pattern="freq_3_of_5", reason="test")

    result = await assign_course_if_needed(supabase, "user-1", trigger)

    assert result is not None
    assert result["already_active"] is True
    supabase.table.return_value.upsert.assert_not_called()


# --- anonymous user ---


@pytest.mark.asyncio
async def test_anonymous_user_skipped():
    supabase = _fake_supabase(active_course_data=None)
    trigger = CourseTrigger(signal="anxiety", pattern="consecutive_2", reason="test")
    result = await assign_course_if_needed(supabase, "anonymous", trigger)
    assert result is None


# --- None supabase ---


@pytest.mark.asyncio
async def test_none_supabase_returns_none():
    trigger = CourseTrigger(signal="anxiety", pattern="consecutive_2", reason="test")
    assert await assign_course_if_needed(None, "user-1", trigger) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
