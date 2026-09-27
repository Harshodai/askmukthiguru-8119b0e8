"""Distress LLM second opinion (flag-gated): may only lower SEVERE -> MODERATE.

The safety property under test is asymmetry: every uncertain path keeps the
regex verdict, CRISIS is never consulted, and a crash in the full distress check
falls back to the regex stage instead of silently skipping crisis pre-emption.
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
    return DistressAssessment(level=level, confidence=0.9, detected_signals=["regex"])


def _ctx(llm, message: str = "Can love heal a broken relationship?", **state_extra):
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


NOT_DISTRESS = "TOPIC"


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setattr(settings, "distress_llm_downgrade_enabled", True)
    monkeypatch.setattr(settings, "distress_llm_downgrade_timeout_s", 0.05)


@pytest.mark.asyncio
async def test_flag_off_by_default_keeps_severe_preemption_and_never_calls_llm():
    assert settings.distress_llm_downgrade_enabled is False
    llm = _llm(NOT_DISTRESS)
    result = await _stage(DistressLevel.SEVERE).run(_ctx(llm))
    assert result is not None and result.route_decision == "crisis_preempted"
    llm._generate_fast.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", ["TOPIC", " topic. ", "Topic"])
async def test_exact_topic_lowers_severe_to_moderate(flag_on, reply):
    result = await _stage(DistressLevel.SEVERE).run(_ctx(_llm(reply)))
    assert result is None  # not pre-empted; continues on the compassionate path


@pytest.mark.asyncio
async def test_crisis_is_never_sent_to_the_llm(flag_on):
    llm = _llm(NOT_DISTRESS)
    result = await _stage(DistressLevel.CRISIS).run(_ctx(llm, "I want to end my life"))
    assert result is not None and result.route_decision == "crisis_preempted"
    llm._generate_fast.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "llm",
    [
        _llm(exc=RuntimeError("provider down")),
        _llm(NOT_DISTRESS, delay=1.0),  # exceeds the 0.05s timeout
        _llm("PERSONAL"),
        _llm(""),
        _llm(None),
        _llm("TOPIC, but the writer may also be hurting"),  # anything beyond one word
        _llm("Not sure"),
    ],
    ids=["error", "timeout", "personal", "empty", "none", "extra_words", "unsure"],
)
async def test_every_uncertain_verdict_keeps_severe(flag_on, llm):
    result = await _stage(DistressLevel.SEVERE).run(_ctx(llm))
    assert result is not None and result.route_decision == "crisis_preempted"


@pytest.mark.asyncio
async def test_missing_llm_provider_keeps_severe(flag_on):
    result = await _stage(DistressLevel.SEVERE).run(_ctx(None))
    assert result is not None and result.route_decision == "crisis_preempted"


@pytest.mark.asyncio
async def test_prior_distress_in_conversation_blocks_downgrade(flag_on):
    llm = _llm(NOT_DISTRESS)
    ctx = _ctx(llm, chat_history_en=[{"role": "user", "content": "I feel hopeless and alone"}])
    result = await _stage(DistressLevel.SEVERE).run(ctx)
    assert result is not None and result.route_decision == "crisis_preempted"
    llm._generate_fast.assert_not_awaited()


@pytest.mark.asyncio
async def test_prior_distress_history_state_blocks_downgrade(flag_on):
    """A non-empty state['distress_history'] must also block the LLM second
    opinion, independent of the chat_history_en scan path above."""
    llm = _llm(NOT_DISTRESS)
    ctx = _ctx(llm, distress_history=[{"level": "MODERATE"}])
    result = await _stage(DistressLevel.SEVERE).run(ctx)
    assert result is not None and result.route_decision == "crisis_preempted"
    llm._generate_fast.assert_not_awaited()


@pytest.mark.asyncio
async def test_distress_check_crash_falls_back_to_regex_and_still_preempts():
    """A crash in analyze_with_history must not switch crisis pre-emption off."""
    stage = DistressStage()
    stage._maybe_trigger_proactive_serene_mind = AsyncMock(return_value=None)
    serene = SimpleNamespace(analyze_with_history=AsyncMock(side_effect=RuntimeError("boom")))
    ctx = _ctx(None, "I want to end my life")
    ctx.container = SimpleNamespace(serene_mind=serene, ollama=None)
    result = await stage.run(ctx)
    assert result is not None and result.route_decision == "crisis_preempted"


@pytest.mark.asyncio
async def test_missing_serene_engine_falls_back_to_regex_and_still_preempts():
    stage = DistressStage()
    stage._maybe_trigger_proactive_serene_mind = AsyncMock(return_value=None)
    ctx = _ctx(None, "I want to end my life")
    ctx.container = SimpleNamespace(serene_mind=None, ollama=None)
    result = await stage.run(ctx)
    assert result is not None and result.route_decision == "crisis_preempted"
