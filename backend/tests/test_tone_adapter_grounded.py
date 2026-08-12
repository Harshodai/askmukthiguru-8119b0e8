"""Regression tests for the retired post-generation tone adapter.

The production pipeline must never run a second LLM rewrite after citations are
attached. Grounded voice is composed once, during source-aware generation.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.tone_adapter_stage import ToneAdapterStage

GROUNDED_ANSWER = (
    "Return to the breath when the mind is restless. [[CITE:1]] "
    "From that steadiness, presence arises on its own. [[CITE:1]]"
)
DOCS = [
    {
        "id": "d1",
        "title": "Breath Awareness",
        "teacher": "Sri Preethaji",
        "source": "Ekam Discourse",
        "year": "2023",
        "url": "https://ekam.example/breath",
    }
]


def _build_ctx(**overrides) -> PipelineContext:
    defaults = dict(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg="How do I return to the breath?",
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-1",
        user={"id": "user-1"},
        is_benchmark=False,
        stream_queue=None,
        trace_id="trace-1",
        start_time=0.0,
        state={"user_msg_en": "How do I return to the breath?"},
        final_answer=GROUNDED_ANSWER,
        citations=list(DOCS),
        graph_result={"faithfulness_score": 0.9},
    )
    defaults.update(overrides)
    return PipelineContext(**defaults)


@pytest.mark.asyncio
async def test_stage_preserves_completed_answer_citations_and_faithfulness():
    """A completed answer must pass unchanged to output verification."""
    ctx = _build_ctx()

    result = await ToneAdapterStage().run(ctx)

    assert result is None
    assert ctx.final_answer == GROUNDED_ANSWER
    assert ctx.citations == DOCS
    assert ctx.graph_result["faithfulness_score"] == 0.9


@pytest.mark.asyncio
async def test_stage_never_constructs_or_calls_a_legacy_adapter(monkeypatch):
    """No post-generation call may manufacture a teacher-like response."""
    ctx = _build_ctx()
    stage = ToneAdapterStage()

    def unexpected_adapter_access(*_args, **_kwargs):
        raise AssertionError("post-generation tone adapter must remain unreachable")

    monkeypatch.setattr(stage, "_get_adapter", unexpected_adapter_access, raising=False)

    result = await stage.run(ctx)

    assert result is None
    assert ctx.final_answer == GROUNDED_ANSWER
