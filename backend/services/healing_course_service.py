"""Proactive healing-course assignment.

Detects sustained distress patterns in a seeker's turn history and assigns a
short healing course. The course curriculum itself lives on the frontend
(src/lib/healingCourses.ts); this backend service only references course slugs
and the SufferingSignal taxonomy — it never imports the TS module.

The evaluator is a pure function over turn dicts carrying distress metadata:

    {"distress_level": int (0-3), "signal": str, "timestamp": float}

Assignment triggers (checked in priority order, first match wins):
  - freq_3_of_5:     distress in >= frequency_threshold of the last
                      frequency_window turns.
  - consecutive_2:   >= consecutive_threshold distress turns in a row.
  - escalation:      distress severity rising across the last 3 turns
                      (levels[0] <= levels[1] < levels[2]), ending >= 2.
  - repeated_signal: the same suffering signal detected at least twice within
                      repeat_window_hours.

Assignment is idempotent: a user with an active course never receives a second
one (assign_course_if_needed returns None). All DB access is best-effort — a
Supabase failure logs a warning and skips the assignment rather than failing
the chat request.

Note on timing: the orchestrator hook evaluates the persisted turn history
(the current turn's assessment is written to memory after the response), so a
trigger fires on the request following the qualifying turn.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

from app.config import settings

logger = logging.getLogger(__name__)

TriggerPattern = Literal["consecutive_2", "freq_3_of_5", "escalation", "repeated_signal"]

DEFAULT_COURSE_SLUG = "end-of-suffering"

# SufferingSignal -> course slug. Course definitions (lessons, titles) live on
# the frontend (src/lib/healingCourses.ts); the backend only maps signals to
# slugs. Unknown signals fall back to DEFAULT_COURSE_SLUG.
SIGNAL_TO_SLUG: dict[str, str] = {
    "grief": "walking-through-grief",
    "anxiety": "quieting-anxiety",
    "anger": "dissolving-conflict",
    "loneliness": "walking-through-grief",
    "meaninglessness": "end-of-suffering",
}

# Keyword classifier mirroring the SufferingSignal taxonomy in
# src/lib/healingCourses.ts (the backend cannot import the TS module; the drift
# risk is confined to this single table). Matched as whole words so "distress"
# never trips the "stress" keyword. "general" is the fallback signal.
_SIGNAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "grief": (
        "grief", "grieving", "died", "death", "passed away", "funeral", "widow",
        "miscarriage", "heartbreak", "breakup", "divorce", "lost", "loss", "bereav",
    ),
    "anxiety": (
        "anxious", "anxiety", "panic", "worried", "worry", "worrying",
        "insomnia", "dread", "nervous", "overwhelmed", "overwhelm",
        "stress", "stressed", "tense", "tension",
    ),
    "anger": (
        "angry", "anger", "furious", "rage", "resent", "betrayed",
        "argument", "forgive", "conflict",
    ),
    "loneliness": (
        "lonely", "alone", "aloneness", "no one", "nobody", "isolated", "abandoned",
    ),
    "meaninglessness": (
        "pointless", "meaningless", "meaninglessness", "meaning", "no meaning",
        "no purpose", "empty inside", "numb", "why am i here", "why am i alive",
    ),
}


@dataclass(frozen=True)
class CourseTrigger:
    """A detected pattern that justifies assigning a healing course."""

    signal: str
    pattern: TriggerPattern
    reason: str


def _distress_level(turn: dict[str, Any]) -> int:
    try:
        return int(turn.get("distress_level", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _signal_of(turn: dict[str, Any]) -> str:
    signal = turn.get("signal") or turn.get("suffering_signal") or "general"
    return str(signal).lower().strip() or "general"


def _timestamp_of(turn: dict[str, Any], now: float) -> float:
    ts = turn.get("timestamp") or turn.get("created_at") or now
    try:
        return float(ts)
    except (TypeError, ValueError):
        return now


def suffering_signal_from_text(
    text: str, detected_signals: list[str] | None = None
) -> str:
    """Classify a message into a SufferingSignal; 'general' when calm/unknown."""
    if not text and not detected_signals:
        return "general"
    haystack = f"{text or ''} {' '.join(detected_signals or [])}".lower()
    for signal, keywords in _SIGNAL_KEYWORDS.items():
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", haystack):
                return signal
    return "general"


def course_slug_for_signal(signal: str) -> str:
    """Map a SufferingSignal to its healing course slug."""
    normalized = (signal or "general").lower().strip()
    return SIGNAL_TO_SLUG.get(normalized, DEFAULT_COURSE_SLUG)


def evaluate_course_trigger(
    history: list[dict[str, Any]],
    consecutive_threshold: int = 2,
    frequency_threshold: int = 3,
    frequency_window: int = 5,
    repeat_window_hours: int = 24,
) -> Optional[CourseTrigger]:
    """Evaluate recent turn history for a course-assignment trigger.

    Turns with distress_level >= 1 count as distress turns. Priority order
    (first match wins): freq_3_of_5, consecutive_2, escalation,
    repeated_signal.
    """
    if not history:
        return None

    window = history[-frequency_window:]
    distress_turns = [t for t in window if _distress_level(t) >= 1]
    if len(distress_turns) >= frequency_threshold:
        return CourseTrigger(
            signal=_signal_of(distress_turns[-1]),
            pattern="freq_3_of_5",
            reason=f"distress in {len(distress_turns)} of last {frequency_window} turns",
        )

    consecutive = 0
    last_signal = "general"
    for turn in reversed(history):
        if _distress_level(turn) >= 1:
            consecutive += 1
            last_signal = _signal_of(turn)
        else:
            break
    if consecutive >= consecutive_threshold:
        return CourseTrigger(
            signal=last_signal,
            pattern="consecutive_2",
            reason=f"{consecutive} consecutive distress turns",
        )

    levels = [_distress_level(t) for t in history[-3:]]
    if len(levels) >= 3 and levels[0] <= levels[1] < levels[2] and levels[2] >= 2:
        return CourseTrigger(
            signal=_signal_of(history[-1]),
            pattern="escalation",
            reason="escalating distress severity",
        )

    now = time.time()
    window_start = now - repeat_window_hours * 3600
    counts: dict[str, int] = {}
    for turn in history:
        if _distress_level(turn) < 1:
            continue
        if _timestamp_of(turn, now) < window_start:
            continue
        signal = _signal_of(turn)
        counts[signal] = counts.get(signal, 0) + 1
    for signal, count in counts.items():
        if count >= 2:
            return CourseTrigger(
                signal=signal,
                pattern="repeated_signal",
                reason=f"'{signal}' distress signal repeated {count}x within {repeat_window_hours}h",
            )

    return None


def trigger_payload(trigger: CourseTrigger, slug: str) -> dict[str, Any]:
    """JSON-safe recommendation payload for API/state surfaces."""
    return {"slug": slug, **asdict(trigger)}


async def assign_course_if_needed(
    supabase: Any,
    user_id: str,
    trigger: CourseTrigger,
) -> Optional[dict[str, Any]]:
    """Assign a healing course unless the user already has an active one.

    Returns the assignment payload ({"slug", "trigger"}) on a new assignment,
    None when skipped (active course exists, no Supabase client, or DB error).
    """
    if not supabase or not user_id or user_id == "anonymous":
        return None

    def _select_active():
        return (
            supabase.table("user_course_progress")
            .select("course_slug")
            .eq("user_id", user_id)
            .eq("status", "active")
            .maybe_single()
            .execute()
        )

    try:
        existing = await asyncio.to_thread(_select_active)
    except Exception as e:
        logger.warning(f"Healing course active-check failed for {user_id}: {e}")
        return None
    if existing and getattr(existing, "data", None):
        logger.info(f"Healing course skipped for {user_id} — active course already exists")
        return None

    slug = course_slug_for_signal(trigger.signal)
    row = {
        "user_id": user_id,
        "course_slug": slug,
        "completed_lessons": [],
        "current_lesson_index": 0,
        "status": "active",
        "assigned_reason": trigger.reason,
        "trigger_signal": trigger.signal,
    }

    def _upsert():
        return (
            supabase.table("user_course_progress")
            .upsert(row, on_conflict="user_id,course_slug")
            .execute()
        )

    try:
        await asyncio.to_thread(_upsert)
    except Exception as e:
        logger.warning(f"Healing course upsert failed for {user_id}: {e}")
        return None

    logger.info(f"Healing course '{slug}' assigned to {user_id} ({trigger.pattern})")
    return {"slug": slug, "trigger": trigger}


async def maybe_assign_healing_course(
    supabase: Any,
    user_id: str,
    history: list[dict[str, Any]],
    *,
    consecutive_threshold: Optional[int] = None,
    frequency_threshold: Optional[int] = None,
    frequency_window: Optional[int] = None,
    repeat_window_hours: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Evaluate turn history and assign a healing course when a trigger fires.

    Thresholds default to the proactive_course_* settings. Returns the
    assignment payload, or None when the feature is disabled, no trigger
    fired, or assignment was skipped (active course already exists).
    """
    if not settings.proactive_course_assignment_enabled:
        return None
    trigger = evaluate_course_trigger(
        history,
        consecutive_threshold=(
            consecutive_threshold or settings.proactive_course_consecutive_threshold
        ),
        frequency_threshold=(
            frequency_threshold or settings.proactive_course_frequency_threshold
        ),
        frequency_window=frequency_window or settings.proactive_course_frequency_window,
        repeat_window_hours=(
            repeat_window_hours or settings.proactive_course_repeat_window_hours
        ),
    )
    if trigger is None:
        return None
    return await assign_course_if_needed(supabase, user_id, trigger)


if __name__ == "__main__":
    sample = [
        {"distress_level": 0, "signal": "general", "timestamp": time.time() - 4000},
        {"distress_level": 2, "signal": "anxiety", "timestamp": time.time() - 3600},
        {"distress_level": 2, "signal": "anxiety", "timestamp": time.time() - 3000},
    ]
    result = evaluate_course_trigger(sample)
    print(f"Trigger: {result}")
    print(f"Slug for 'anxiety': {course_slug_for_signal('anxiety')}")
    print(f"Signal from text: {suffering_signal_from_text('I keep worrying at night')}")
