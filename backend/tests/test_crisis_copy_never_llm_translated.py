"""Translation safety check (2026-09-28, owner decision): crisis/SEVERE/
third-party copy must NEVER be run through the live LLM translator
(ctx.container.translation.translate_text) — it is always the fixed,
reviewed English string, for every seeker, every language.

Root cause this guards: once the other session made translation real on
LLM_PROVIDER=openrouter (gemini_translation_enabled=True by default, live
via Gemini-through-OpenRouter), the pre-existing is_indic branch in
DistressStage._crisis_preemption_result started running safety-critical
copy ("Are you safe right now, or are you thinking about harming yourself?")
through a live, nondeterministic LLM call with no review gate, every time.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.pipeline.stages.distress_stage import DistressStage
from services.serene_mind_engine import DistressAssessment, DistressLevel


def _ctx_indic(preferred_lang: str = "hi"):
    translation = AsyncMock()
    # If translate_text is EVER called, return something obviously different
    # so a regression is loud and unmistakable in a failing assertion.
    translation.translate_text = AsyncMock(return_value="__LLM_TRANSLATED__")
    return SimpleNamespace(
        container=SimpleNamespace(translation=translation),
        is_indic=True,
        preferred_lang=preferred_lang,
        trace_id="t",
        start_time=time.time(),
        has_distress_keywords=True,
        routing_chain=[],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "assessment",
    [
        DistressAssessment(level=DistressLevel.CRISIS, confidence=1.0, detected_signals=["x"]),
        DistressAssessment(level=DistressLevel.SEVERE, confidence=0.9, detected_signals=["x"]),
        DistressAssessment(
            level=DistressLevel.SEVERE,
            confidence=0.9,
            detected_signals=["x"],
            recommended_response_type="severe_ideation_checkin",
        ),
        DistressAssessment(
            level=DistressLevel.CRISIS,
            confidence=0.9,
            detected_signals=["x"],
            recommended_response_type="third_party_crisis",
        ),
    ],
    ids=["crisis", "severe_generic", "severe_ideation_checkin", "third_party"],
)
async def test_crisis_copy_never_calls_translate_text(assessment):
    ctx = _ctx_indic()
    result = await DistressStage._crisis_preemption_result(ctx, assessment)

    ctx.container.translation.translate_text.assert_not_awaited()
    assert "__LLM_TRANSLATED__" not in result.final_answer


@pytest.mark.asyncio
async def test_crisis_copy_is_the_fixed_english_string_for_indic_seeker():
    ctx = _ctx_indic(preferred_lang="hi")
    assessment = DistressAssessment(
        level=DistressLevel.CRISIS, confidence=1.0, detected_signals=["x"]
    )
    result = await DistressStage._crisis_preemption_result(ctx, assessment)
    # The fixed English safety-question text must appear verbatim, untouched
    # by any translation step.
    assert "Are you safe right now" in result.final_answer


@pytest.mark.asyncio
async def test_helpline_numbers_survive_verbatim_regardless_of_language():
    ctx = _ctx_indic(preferred_lang="mr")
    assessment = DistressAssessment(
        level=DistressLevel.CRISIS, confidence=1.0, detected_signals=["x"]
    )
    result = await DistressStage._crisis_preemption_result(ctx, assessment)
    assert "Tele-MANAS" in result.final_answer
    assert "112" in result.final_answer  # National Emergency Services number
