from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.pipeline.stages import BoundedComparisonShortCircuitStage
from app.pipeline.stages.context import PipelineContext


@pytest.mark.asyncio
async def test_bounded_comparison_short_circuits_english_without_model() -> None:
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg="What is the difference between meditation and contemplation?",
        preferred_lang="en",
        trace_id="trace-test",
        start_time=time.time(),
        state={
            "user_msg_en": "What is the difference between meditation and contemplation?"
        },
    )

    result = await BoundedComparisonShortCircuitStage().run(ctx)

    assert result is not None
    assert result.route_decision == "bounded_comparison_short_circuit"
    assert result.intent == "COMPARATIVE"
    assert result.model_used is None
    assert result.citations == []
    assert result.verification["method"] == "limited_comparison_fallback"
    assert len(result.final_answer) > 200


@pytest.mark.asyncio
async def test_bounded_comparison_does_not_bypass_indic_translation() -> None:
    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg="What is the difference between meditation and contemplation?",
        preferred_lang="hi",
        trace_id="trace-test",
        start_time=time.time(),
        state={
            "user_msg_en": "What is the difference between meditation and contemplation?"
        },
    )

    result = await BoundedComparisonShortCircuitStage().run(ctx)

    assert result is None
