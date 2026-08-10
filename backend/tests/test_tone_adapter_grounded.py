"""ToneAdapterStage citation re-grounding tests (P1-AI-5).

The guru tone transform runs inside the pipeline (after citation resolution,
before output guardrails). When the transform drops citation markers, the
stage must clear citations and zero the faithfulness score so un-grounded
claims are never presented as sourced. Mirrors test_pipeline_stages.py.
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

RETOLD_GROUNDED = (
    "When the mind is restless, return to the breath. [[CITE:1]] "
    "Presence arises from that steadiness. [[CITE:1]]"
)

UNGROUNDED_CLAIM = (
    "Return to the breath when the mind is restless. "
    "The breath is the root of all healing."
)

DOCS = [
    {"id": "d1", "title": "Breath Awareness", "teacher": "Sri Preethaji",
     "source": "Ekam Discourse", "year": "2023", "url": "https://ekam.example/breath"},
    {"id": "d2", "title": "On Presence", "source": "Ekam Teaching", "year": "2022"},
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


class _GroundedAdapter:
    """Fake adapter that retells the answer while keeping citation markers."""

    def __init__(self, **kwargs):
        pass

    async def transform_tone(self, state_input):
        return {"final_answer": RETOLD_GROUNDED}


class _UngroundedAdapter:
    """Fake adapter that drops citation markers and adds an unsupported claim."""

    def __init__(self, **kwargs):
        pass

    async def transform_tone(self, state_input):
        return {"final_answer": UNGROUNDED_CLAIM}


@pytest.mark.asyncio
async def test_adapter_preserves_citations(monkeypatch):
    """A grounded citation survives the tone transform: references stay valid."""
    monkeypatch.setattr("rag.nodes.guru_tone_adapter.GuruToneAdapterNode", _GroundedAdapter)

    ctx = _build_ctx()
    result = await ToneAdapterStage().run(ctx)

    assert result is None, "ToneAdapterStage must not short-circuit"
    assert ctx.final_answer == RETOLD_GROUNDED
    assert ctx.citations == DOCS
    assert ctx.graph_result["faithfulness_score"] == 0.9


@pytest.mark.asyncio
async def test_adapter_introduces_ungrounded_claim(monkeypatch):
    """An ungrounded claim loses its citations and zeroes faithfulness."""
    monkeypatch.setattr("rag.nodes.guru_tone_adapter.GuruToneAdapterNode", _UngroundedAdapter)

    ctx = _build_ctx()
    result = await ToneAdapterStage().run(ctx)

    assert result is None, "ToneAdapterStage must not short-circuit"
    assert ctx.final_answer == UNGROUNDED_CLAIM
    assert ctx.citations == []
    assert ctx.graph_result["faithfulness_score"] == 0.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
