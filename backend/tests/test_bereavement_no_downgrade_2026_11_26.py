"""SEVERE distress must not be downgraded by a bereavement/grief intent.

2026-11-26 audit: a lexical "grief_bereavement" intent plus a short substring
classifier downgraded SEVERE -> MODERATE for passive-ideation messages. Any future
de-escalation of SEVERE needs clinician review first.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.pipeline.stages.distress_stage import DistressStage
from services.serene_mind_engine import DistressAssessment, DistressLevel, SereneMindEngine

PASSIVE_IDEATION_BEREAVEMENT = [
    "My mother passed away last month and I can't go on without her",
    "My husband passed away and I wish I could disappear and not exist",
    "My mother passed away and I don't want to exist anymore",
    "My wife passed away. I feel hopeless and want to be with her",
]


@pytest.mark.parametrize("message", PASSIVE_IDEATION_BEREAVEMENT)
def test_engine_rates_these_messages_severe_or_higher(message):
    """Guards the premise: the assessor itself flags them, so nothing may lower it."""
    level = SereneMindEngine().assess_distress(message).level
    assert level >= DistressLevel.SEVERE


@pytest.mark.asyncio
@pytest.mark.parametrize("message", PASSIVE_IDEATION_BEREAVEMENT)
async def test_stage_keeps_severe_for_bereavement_with_passive_ideation(message):
    stage = DistressStage()
    stage._detect_distress = AsyncMock(
        return_value=DistressAssessment(
            level=DistressLevel.SEVERE,
            confidence=0.9,
            detected_signals=["test"],
            recommended_response_type="crisis",
        )
    )
    stage._maybe_trigger_proactive_serene_mind = AsyncMock()
    ctx = SimpleNamespace(
        state={"user_msg_en": message, "distress_history": []},
        user_msg=message,
        trace_id="bereavement-no-downgrade-test",
        start_time=time.time(),
    )

    result = await stage.run(ctx)

    assert result is not None
    assert result.route_decision == "crisis_preempted"
    assert result.proactive_serene_mind["level"] == DistressLevel.SEVERE.name


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
