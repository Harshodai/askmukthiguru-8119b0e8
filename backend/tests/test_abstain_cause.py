"""NEW-ANS-2 (ANS-010, RET-17; AC-ANS-23, AC-RET-17): honest abstain causes.

The bridge used to pass only ``status`` to ``_abstain``. The pipeline's
``abstain_reason`` and answerability verdict were dropped, so "no teaching
found" and "the check could not run" looked the same, and a store error still
reported ``verification.passed=True``. Copy is unchanged here (D-PQ9 is open):
only the cause, the honest ``passed`` flag, the outcome and the metric change.
"""

from __future__ import annotations

import pytest

import tests.test_first_person_bridge as _bridge_tests
from app.answer_contract import abstain_cause
from app.answer_outcome import build_answer_outcome
from app.grounding import grounding_state_for
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from tests.test_first_person_bridge import _container, _ctx, _fp_result

_bridge_gates = _bridge_tests._bridge_gates
fp_pipeline = _bridge_tests.fp_pipeline


@pytest.mark.parametrize(
    ("status", "reason", "answerability", "cause"),
    [
        ("abstained", "no_verified_clips", None, "no_evidence"),
        ("abstained", "relevance_below_min", "yes", "no_evidence"),
        ("abstained", "answerability_withheld", "no", "no_evidence"),
        ("abstained", "answerability_withheld", "indeterminate", "system_unavailable"),
        ("abstained", "relevance_indeterminate", "relevance_indeterminate", "system_unavailable"),
        ("abstained", "serving_contract_violation", None, "system_unavailable"),
        ("error", None, None, "system_unavailable"),
        ("abstained", "topic_blocked", None, "topic_boundary"),
    ],
)
def test_reason_to_cause(status, reason, answerability, cause):
    assert abstain_cause(status, reason, answerability) == cause


def _outcome(result) -> str:
    return build_answer_outcome(
        request_id="t",
        route_decision=result.route_decision,
        route_reason=None,
        grounding_state=grounding_state_for(result),
        citations=result.citations,
        verification=result.verification,
        cache_hit=False,
        latency_ms=1,
        model_used=None,
    )["outcome"]


def _pipeline_says(fp_pipeline, *, status, reason=None, answerability=None):
    res = _fp_result(citations=[], status=status, is_direct=False)
    res.abstain_reason = reason
    res.answerability = answerability
    fp_pipeline.execute.return_value = res


@pytest.mark.asyncio
async def test_store_error_is_not_a_pass(fp_pipeline):
    _pipeline_says(fp_pipeline, status="error")

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result.route_decision == "first_person_abstain"
    assert result.verification["passed"] is False
    assert result.verification["abstain_cause"] == "system_unavailable"
    assert _outcome(result) == "error"


@pytest.mark.asyncio
async def test_scorer_failure_is_reported_as_system_unavailable(fp_pipeline):
    _pipeline_says(
        fp_pipeline,
        status="abstained",
        reason="relevance_indeterminate",
        answerability="relevance_indeterminate",
    )

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result.verification["passed"] is False
    assert result.route_metadata["abstain_reason"] == "relevance_indeterminate"
    assert result.route_metadata["abstain_cause"] == "system_unavailable"
    assert _outcome(result) == "error"


@pytest.mark.asyncio
async def test_no_evidence_abstain_stays_a_truthful_pass(fp_pipeline):
    _pipeline_says(fp_pipeline, status="abstained", reason="relevance_below_min")

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result.verification["passed"] is True
    assert result.route_metadata["abstain_cause"] == "no_evidence"
    assert _outcome(result) == "abstained"


@pytest.mark.asyncio
async def test_bridge_exception_is_not_a_pass(fp_pipeline):
    fp_pipeline.execute.side_effect = RuntimeError("qdrant down")

    result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result.route_decision == "first_person_abstain"
    assert result.verification["passed"] is False
    assert _outcome(result) == "error"


@pytest.mark.asyncio
async def test_abstain_cause_metric_is_counted(fp_pipeline):
    from app.metrics import ABSTAIN_CAUSE_TOTAL

    before = ABSTAIN_CAUSE_TOTAL.labels(cause="system_unavailable")._value.get()
    _pipeline_says(fp_pipeline, status="error")

    await FirstPersonBridgeStage().run(_ctx(_container()))

    assert ABSTAIN_CAUSE_TOTAL.labels(cause="system_unavailable")._value.get() == before + 1
