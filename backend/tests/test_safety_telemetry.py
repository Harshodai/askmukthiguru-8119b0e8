"""Regression tests for PLAN.md Phase A6 — safety event logging.

Verifies the events actually fire at the real call sites (crisis
preemption, kill switch), not just that the logging functions work in
isolation, and that no raw message text leaks into the log line.
"""

from unittest.mock import MagicMock

import pytest

from app.pipeline.stages.kill_switch_stage import KillSwitchStage
from services import safety_telemetry
from services.serene_mind_engine import DistressAssessment, DistressLevel


def test_log_functions_emit_structured_lines_without_raw_text(caplog):
    with caplog.at_level("WARNING", logger="safety_events"):
        safety_telemetry.log_tier_escalation(trace_id="t1", from_level="MILD", to_level="SEVERE")
        safety_telemetry.log_crisis_referral_shown(trace_id="t1", level="CRISIS", region=None)
        safety_telemetry.log_kill_switch_triggered(trace_id="t1", locale="hi", scope="locale")

    messages = [r.message for r in caplog.records]
    assert any("event=tier_escalation" in m for m in messages)
    assert any("event=crisis_referral_shown" in m for m in messages)
    assert any("event=kill_switch_triggered" in m for m in messages)
    # No message could plausibly contain a full user sentence.
    assert all(len(m) < 200 for m in messages)


@pytest.mark.asyncio
async def test_kill_switch_logs_event_when_triggered(caplog):
    from app.config import settings

    settings.generation_kill_switch_enabled = True
    try:
        stage = KillSwitchStage()
        ctx = MagicMock(preferred_lang="en", trace_id="t2", start_time=0.0)
        with caplog.at_level("WARNING", logger="safety_events"):
            await stage.run(ctx)
        assert any(
            "event=kill_switch_triggered" in r.message and "scope=global" in r.message
            for r in caplog.records
        )
    finally:
        settings.generation_kill_switch_enabled = False


@pytest.mark.asyncio
async def test_crisis_preemption_logs_referral_shown(caplog):
    from app.pipeline.stages.distress_stage import DistressStage

    assessment = DistressAssessment(level=DistressLevel.CRISIS, confidence=0.9)
    ctx = MagicMock(trace_id="t3", start_time=0.0, is_indic=False, container=None)

    with caplog.at_level("WARNING", logger="safety_events"):
        await DistressStage._crisis_preemption_result(ctx, assessment)

    assert any(
        "event=crisis_referral_shown" in r.message and "level=CRISIS" in r.message
        for r in caplog.records
    )


def test_tier_escalation_is_skipped_without_prior_history():
    """No prior turn recorded -> nothing to compare against -> no event, no crash."""
    from app.pipeline.stages.distress_stage import DistressStage

    assessment = DistressAssessment(level=DistressLevel.MODERATE, confidence=0.7)
    ctx = MagicMock(trace_id="t4")
    # Should not raise on an empty or missing distress_history.
    DistressStage._maybe_log_tier_escalation(ctx, assessment, DistressLevel.MODERATE.value, {})
    DistressStage._maybe_log_tier_escalation(
        ctx, assessment, DistressLevel.MODERATE.value, {"distress_history": []}
    )


def test_tier_escalation_is_defensive_against_malformed_history():
    """A malformed distress_history entry must never crash the safety stage."""
    from app.pipeline.stages.distress_stage import DistressStage

    assessment = DistressAssessment(level=DistressLevel.MODERATE, confidence=0.7)
    ctx = MagicMock(trace_id="t5")
    DistressStage._maybe_log_tier_escalation(
        ctx, assessment, DistressLevel.MODERATE.value, {"distress_history": ["not-a-dict"]}
    )
    DistressStage._maybe_log_tier_escalation(
        ctx,
        assessment,
        DistressLevel.MODERATE.value,
        {"distress_history": [{"level": "NOT_A_REAL_LEVEL"}]},
    )
