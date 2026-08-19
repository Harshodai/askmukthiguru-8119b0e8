"""Regression coverage for deterministic severe/crisis pipeline preemption."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.pipeline.stages.distress_stage import DistressStage
from services.serene_mind_engine import DistressAssessment, DistressLevel


@pytest.mark.asyncio
@pytest.mark.parametrize("level", [DistressLevel.SEVERE, DistressLevel.CRISIS])
async def test_severe_distress_preempts_before_proactive_or_graph(level):
    """High-acuity distress returns a reviewed response without later side effects."""
    stage = DistressStage()
    stage._detect_distress = AsyncMock(
        return_value=DistressAssessment(
            level=level,
            confidence=0.99,
            detected_signals=["test"],
            recommended_response_type="crisis",
        )
    )
    stage._maybe_trigger_proactive_serene_mind = AsyncMock()
    ctx = SimpleNamespace(
        state={"user_msg_en": "I need help now", "distress_history": []},
        user_msg="I need help now",
        trace_id="crisis-preemption-test",
        start_time=time.time(),
    )

    result = await stage.run(ctx)

    assert result is not None
    assert result.intent == "DISTRESS"
    assert result.route_decision == "crisis_preempted"
    assert result.model_used is None
    assert result.citations == []
    assert result.proactive_serene_mind["preempted"] is True
    assert result.proactive_serene_mind["level"] == level.name
    assert "crisis" in result.final_answer.lower() or "emergency" in result.final_answer.lower()
    stage._maybe_trigger_proactive_serene_mind.assert_not_awaited()


@pytest.mark.asyncio
async def test_moderate_distress_remains_on_compassionate_pipeline_path():
    """Only severe/crisis levels preempt; moderate support still reaches its normal path."""
    stage = DistressStage()
    stage._detect_distress = AsyncMock(
        return_value=DistressAssessment(
            level=DistressLevel.MODERATE,
            confidence=0.8,
            detected_signals=["test"],
            recommended_response_type="gentle",
        )
    )
    stage._maybe_trigger_proactive_serene_mind = AsyncMock(return_value={"triggered": False})
    ctx = SimpleNamespace(
        state={"user_msg_en": "I am anxious", "distress_history": []},
        user_msg="I am anxious",
        user_id="test-user",
        request=SimpleNamespace(),
    )

    result = await stage.run(ctx)

    assert result is None
    stage._maybe_trigger_proactive_serene_mind.assert_awaited_once()
