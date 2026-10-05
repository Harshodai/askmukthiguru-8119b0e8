"""Distress LLM escalation (flag-gated, OFF by default, 2026-09-28 owner-approved
"escalate-only + re-tier"): may only RAISE a regex level (NONE/MILD/MODERATE ->
SEVERE/CRISIS, or SEVERE -> CRISIS). Regex is the floor and is never lowered.

Mirrors the style of tests/test_distress_llm_downgrade.py — same asymmetry
discipline, opposite direction.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.pipeline.stages.distress_stage import DistressStage
from services.serene_mind_engine import DistressAssessment, DistressLevel


def _assessment(level: DistressLevel) -> DistressAssessment:
    return DistressAssessment(level=level, confidence=0.5, detected_signals=["regex"])


def _ctx(llm, message: str = "I feel a bit off today", **state_extra):
    return SimpleNamespace(
        state={"user_msg_en": message, "distress_history": [], **state_extra},
        user_msg=message,
        user_id="u",
        request=SimpleNamespace(),
        trace_id="t",
        start_time=time.time(),
        container=SimpleNamespace(ollama=llm),
    )


def _stage(level: DistressLevel) -> DistressStage:
    stage = DistressStage()
    stage._detect_distress = AsyncMock(return_value=_assessment(level))
    stage._maybe_trigger_proactive_serene_mind = AsyncMock(return_value=None)
    return stage


def _llm(reply=None, exc=None, delay=0.0):
    async def generate(_system, _user):
        if delay:
            await asyncio.sleep(delay)
        if exc:
            raise exc
        return reply

    llm = SimpleNamespace()
    llm._generate_fast = AsyncMock(side_effect=generate)
    return llm


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setattr(settings, "distress_llm_escalation_enabled", True)
    monkeypatch.setattr(settings, "distress_llm_escalation_timeout_s", 0.05)


@pytest.mark.asyncio
async def test_flag_off_by_default_never_calls_llm():
    assert settings.distress_llm_escalation_enabled is False
    llm = _llm("CRISIS")
    result = await _stage(DistressLevel.MODERATE).run(_ctx(llm))
    assert result is None  # MODERATE doesn't preempt; continues on compassionate path
    llm._generate_fast.assert_not_awaited()


@pytest.mark.asyncio
async def test_crisis_regex_never_calls_the_llm(flag_on):
    """The instant crisis response must never be delayed by an LLM call."""
    llm = _llm("CRISIS")
    result = await _stage(DistressLevel.CRISIS).run(_ctx(llm, "I want to end my life"))
    assert result is not None and result.route_decision == "crisis_preempted"
    llm._generate_fast.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "start_level,verdict,expect_final",
    [
        (DistressLevel.NONE, "SEVERE", DistressLevel.SEVERE),
        (DistressLevel.MILD, "CRISIS", DistressLevel.CRISIS),
        (DistressLevel.MODERATE, "SEVERE", DistressLevel.SEVERE),
        (DistressLevel.SEVERE, "CRISIS", DistressLevel.CRISIS),
    ],
)
async def test_escalation_raises_level(flag_on, start_level, verdict, expect_final):
    llm = _llm(verdict)
    ctx = _ctx(llm)
    result = await _stage(start_level).run(ctx)
    assert ctx.assessment.level == expect_final
    if expect_final >= DistressLevel.SEVERE:
        assert result is not None and result.route_decision == "crisis_preempted"
    else:
        assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verdict",
    ["NONE", "MILD", "MODERATE"],
)
async def test_escalation_never_lowers_a_higher_regex_level(flag_on, verdict):
    """Regex is the floor: an LLM verdict at or below the current level must
    never lower it, even though the LLM was consulted."""
    llm = _llm(verdict)
    ctx = _ctx(llm)
    result = await _stage(DistressLevel.MODERATE).run(ctx)
    assert ctx.assessment.level == DistressLevel.MODERATE
    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "llm",
    [
        _llm(exc=RuntimeError("provider down")),
        _llm("CRISIS", delay=1.0),  # exceeds the 0.05s timeout
        _llm(""),
        _llm(None),
        _llm("maybe crisis?"),  # not an exact enum word
        _llm("EMERGENCY"),  # not a real level name
    ],
    ids=["error", "timeout", "empty", "none", "malformed_prose", "unknown_word"],
)
async def test_every_failure_mode_keeps_regex_level_unchanged(flag_on, llm):
    ctx = _ctx(llm)
    result = await _stage(DistressLevel.MODERATE).run(ctx)
    assert ctx.assessment.level == DistressLevel.MODERATE
    assert result is None


@pytest.mark.asyncio
async def test_missing_llm_provider_keeps_regex_level(flag_on):
    ctx = _ctx(None)
    result = await _stage(DistressLevel.MODERATE).run(ctx)
    assert ctx.assessment.level == DistressLevel.MODERATE
    assert result is None


@pytest.mark.asyncio
async def test_escalated_severe_gets_checkin_response_type(flag_on):
    llm = _llm("SEVERE")
    ctx = _ctx(llm)
    await _stage(DistressLevel.MODERATE).run(ctx)
    assert ctx.assessment.recommended_response_type == "severe_ideation_checkin"


@pytest.mark.asyncio
async def test_escalated_crisis_gets_crisis_response_type(flag_on):
    llm = _llm("CRISIS")
    ctx = _ctx(llm)
    await _stage(DistressLevel.MODERATE).run(ctx)
    assert ctx.assessment.recommended_response_type == "crisis"


@pytest.mark.asyncio
async def test_third_party_assessment_is_never_escalated_further(flag_on):
    """Third-party concern already has its own dedicated response — nothing
    to escalate it to, and the flag must not overwrite that marker."""
    assessment = DistressAssessment(
        level=DistressLevel.CRISIS,
        confidence=0.9,
        detected_signals=["[third_party]"],
        recommended_response_type="third_party_crisis",
    )
    stage = DistressStage()
    stage._detect_distress = AsyncMock(return_value=assessment)
    stage._maybe_trigger_proactive_serene_mind = AsyncMock(return_value=None)
    llm = _llm("CRISIS")
    result = await stage.run(_ctx(llm, "she said she wants to kill herself"))
    assert result is not None and result.route_decision == "crisis_preempted"
    llm._generate_fast.assert_not_awaited()  # already CRISIS, never called
    assert result.final_answer  # sanity: a real response was built


@pytest.mark.asyncio
async def test_downgrade_and_escalation_flags_are_fully_independent():
    """Enabling escalation must not turn the (still-OFF) downgrade path on,
    and vice versa."""
    assert settings.distress_llm_downgrade_enabled is False
    assert settings.distress_llm_escalation_enabled is False
