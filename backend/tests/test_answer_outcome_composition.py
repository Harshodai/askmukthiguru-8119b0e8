"""NEW-ANS-1 (ANS-011, AC-ANS-15): the real served-clip outcome composition.

The bridge result is built by ``FirstPersonBridgeStage`` with a fake pipeline
(no LLM, no store), then passed through ``grounding_state_for`` and
``build_answer_outcome`` exactly as ``PipelineCoordinator._emit_answer_outcome``
does. ``test_answer_outcome_telemetry.py`` builds ``grounding_state`` by hand,
so it never saw what a served "Related, not a direct answer" clip reports.
"""

from __future__ import annotations

import pytest

import tests.test_first_person_bridge as _bridge_tests
from app.answer_outcome import build_answer_outcome
from app.config import settings
from app.grounding import grounding_state_for
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from tests.test_first_person_bridge import _CLIP_TEXT, _container, _ctx, _fp_result

# The bridge suite's fixtures: its gates (autouse) and the fake pipeline.
_bridge_gates = _bridge_tests._bridge_gates
fp_pipeline = _bridge_tests.fp_pipeline


def _outcome(result) -> dict:
    return build_answer_outcome(
        request_id=result.trace_id,
        route_decision=result.route_decision,
        route_reason=None,
        grounding_state=grounding_state_for(result),
        citations=result.citations,
        verification=result.verification,
        cache_hit=False,
        latency_ms=result.latency_ms,
        model_used=result.model_used,
        blocked=bool(result.blocked),
        errored=result.route_decision in ("error", "timeout"),
    )


@pytest.mark.asyncio
async def test_served_related_clip_counts_as_served(fp_pipeline, monkeypatch):
    monkeypatch.setattr(settings, "first_person_serve_weak_match", True)
    fp_pipeline.execute.return_value = _fp_result(
        answer=f"**Sri Preethaji**\n\n{_CLIP_TEXT}", status="weak_match", is_direct=False
    )

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None and result.route_decision == "first_person_bridge"
    assert result.citations, "a clip was served"
    # The label stays honest: a related clip is not a certified direct answer.
    assert result.verification["passed"] is False
    assert result.verification["direct"] is False
    record = _outcome(result)
    assert record["outcome"] == "served", record


@pytest.mark.asyncio
async def test_served_direct_clip_counts_as_served(fp_pipeline):
    fp_pipeline.execute.return_value = _fp_result(is_direct=True)

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None and result.citations
    assert _outcome(result)["outcome"] == "served"


@pytest.mark.asyncio
async def test_no_match_abstain_counts_as_abstained(fp_pipeline):
    fp_pipeline.execute.return_value = _fp_result(citations=[], status="abstained")

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None and not result.citations
    assert _outcome(result)["outcome"] == "abstained"


def test_bridge_route_without_verified_citations_is_not_served():
    """A bridge-route record with no verified clip never counts as served."""
    record = build_answer_outcome(
        request_id="t",
        route_decision="first_person_bridge",
        route_reason=None,
        grounding_state="abstained",
        citations=[{"point_id": "p1"}],
        verification={"passed": False, "citations_verified": False},
        cache_hit=False,
        latency_ms=1,
        model_used=None,
    )
    assert record["outcome"] == "abstained"
