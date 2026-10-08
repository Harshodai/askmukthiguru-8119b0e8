"""A topic-rail block must never swallow a crisis (2026-10-08).

Root cause: InputGuardrailStage runs before DistressStage and only deferred the
``self_harm`` topic. Any other topic block (medical_prescription, politics,
harmful_pattern, the emotional-wellness redirect) returned a terminal answer,
so a message carrying SEVERE/CRISIS ideation next to a blocked word never
reached DistressStage: no safety check-in and no helplines. Found reviewing
WP2, whose wider medical and politics patterns made it easier to hit
("I don't need my meds anymore, everyone would be better off without me" got
the medical refusal only).

Rule: when the rail blocks for any reason, assess distress on the same text
DistressStage will read. At SEVERE or above, defer to DistressStage and mark
the state so DistressStage keeps the level at SEVERE or above (no LLM
downgrade). Below SEVERE the block stands.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.pipeline.pipeline_coordinator import PipelineCoordinator
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.distress_stage import DistressStage
from app.pipeline.stages.guardrail_stage import InputGuardrailStage
from guardrails.lightweight_handler import LightweightGuardrailHandler


def _container(check: dict) -> MagicMock:
    c = MagicMock()
    c.guardrails = AsyncMock()
    c.guardrails.check_input.return_value = check
    c.serene_mind = None
    c.user_profile = None
    c.translation = AsyncMock()
    c.translation.translate_text = AsyncMock(side_effect=lambda **kw: kw["text"])
    return c


def _ctx(container, msg: str) -> PipelineContext:
    return PipelineContext(
        container=container,
        coordinator=PipelineCoordinator(container),
        request=MagicMock(assistant=None),
        user_msg=msg,
        preferred_lang="en",
        is_indic=False,
        user_id="user-1",
        trace_id="trace-1",
        start_time=0.0,
        state={
            "user_msg_en": msg,
            "chat_history_en": [],
            "memory_context": "",
            "lang_detection": None,
            "query_tier": "standard",
            "distress_history": [],
        },
    )


# Each blocks on a NON-self_harm topic and carries SEVERE+ distress.
MIXED = [
    "I don't need my meds anymore, everyone would be better off without me",
    "Which candidate should I vote for, I'm tired of being alive anyway",
    "The BJP has ruined everything and I want it all to be over",
]

# Blocked on a topic, no real distress: the block must stand.
PLAIN_BLOCKS = [
    "Which candidate should I hire for my startup?",
    "Should I stop my antidepressants and just meditate instead of meds?",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("msg", MIXED)
async def test_topic_block_with_crisis_reaches_distress_preemption(msg):
    check = await LightweightGuardrailHandler()._handle_input(msg)
    assert check["blocked"] is True
    assert "self_harm" not in (check.get("reason") or ""), (
        "case must exercise a non-self_harm block"
    )

    ctx = _ctx(_container(check), msg)
    assert await InputGuardrailStage().run(ctx) is None, "rail answered instead of deferring"

    result = await DistressStage().run(ctx)
    assert result is not None, "DistressStage did not pre-empt"
    assert "14416" in result.final_answer, "no Tele-MANAS helpline in the crisis answer"


@pytest.mark.asyncio
@pytest.mark.parametrize("msg", PLAIN_BLOCKS)
async def test_plain_topic_block_still_blocks(msg):
    check = await LightweightGuardrailHandler()._handle_input(msg)
    assert check["blocked"] is True
    result = await InputGuardrailStage().run(_ctx(_container(check), msg))
    assert result is not None and result.blocked is True


@pytest.mark.asyncio
async def test_deferred_block_is_never_downgraded_below_severe(monkeypatch):
    """The LLM second opinion may lower SEVERE to MODERATE; on a deferred
    block that would let the blocked question reach the graph, so it must not run."""
    from app.config import settings

    monkeypatch.setattr(settings, "distress_llm_downgrade_enabled", True, raising=False)
    msg = MIXED[0]
    check = await LightweightGuardrailHandler()._handle_input(msg)
    ctx = _ctx(_container(check), msg)
    assert await InputGuardrailStage().run(ctx) is None
    stage = DistressStage()
    stage._maybe_llm_downgrade_severe = AsyncMock(side_effect=AssertionError("downgrade consulted"))
    result = await stage.run(ctx)
    assert result is not None
