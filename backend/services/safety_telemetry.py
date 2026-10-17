"""Safety event logging — PLAN.md Phase A6.

Counts of tier escalations, crisis referrals shown, and kill-switch trips,
logged as structured lines Railway's log aggregation already captures (see
CLAUDE.md's "Error Tracking & GlitchTip Decision" — this repo deliberately
uses log aggregation over a dedicated events table for the pilot). No raw
user text, no message content, no identifying fields beyond an opaque
region/level/trace_id ever cross this module — that boundary is enforced by
the typed function signatures below, not by caller discipline.

Phase H1 will eventually want these as queryable rows for a dashboard
(escalation rate, night-time share, etc.) — this module's event *names* are
chosen to match that future schema so H1 can add a sink without renaming
anything here.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("safety_events")


def _count_distress_detection(level: str) -> None:
    """Increment DISTRESS_DETECTIONS with a level-only label (no text, no ids).

    Lazily imported so this log-only module never pays import-time cost and can
    never wedge a safety response on a metrics failure: a counter that cannot
    increment logs a warning instead of raising.
    """
    try:
        from app.metrics import DISTRESS_DETECTIONS

        DISTRESS_DETECTIONS.labels(level=level).inc()
    except Exception as e:
        logger.warning("SAFETY_EVENT event=metric_error what=distress_detections err=%s", e)


def log_tier_escalation(*, trace_id: str, from_level: str, to_level: str) -> None:
    """A conversation's assessed distress level increased turn-over-turn."""
    logger.warning(
        "SAFETY_EVENT event=tier_escalation trace_id=%s from=%s to=%s",
        trace_id,
        from_level,
        to_level,
    )


def log_crisis_referral_shown(*, trace_id: str, level: str, region: str | None) -> None:
    """A crisis/distress response including helpline resources was shown."""
    logger.warning(
        "SAFETY_EVENT event=crisis_referral_shown trace_id=%s level=%s region=%s",
        trace_id,
        level,
        region or "unfiltered",
    )
    # RP-C3: the level label is the caller's DistressLevel name (bounded enum
    # vocabulary), upper-cased defensively — never message text or an id.
    _count_distress_detection(str(level).upper())


def log_kill_switch_triggered(*, trace_id: str, locale: str, scope: str) -> None:
    """The generation kill switch fired for a request (scope: "global" | "locale")."""
    logger.warning(
        "SAFETY_EVENT event=kill_switch_triggered trace_id=%s locale=%s scope=%s",
        trace_id,
        locale,
        scope,
    )
    # RP-C3: the switch has no distress level of its own; it counts under one
    # fixed label (locale/scope stay in the log line only, never in a label).
    _count_distress_detection("KILL_SWITCH")


if __name__ == "__main__":
    # ponytail: quick self-check — confirm calls don't raise, nothing else to assert
    # against a log-only sink without capturing stdlib logging output.
    log_tier_escalation(from_level="MILD", to_level="MODERATE", trace_id="t1")
    log_crisis_referral_shown(trace_id="t1", level="CRISIS", region=None)
    log_kill_switch_triggered(trace_id="t1", locale="en", scope="global")
    print("safety_telemetry self-checks passed")
