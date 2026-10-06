"""Root-cause class: an unmeasured or partially-matched state reported as a pass.

Faculty-readiness review 2026-10-05, under the Manus audit rule "a fabricated
optimistic score is P0". Each test pins one instance of the same class:

1. A refusal marker ANYWHERE in an answer made verification skip the whole
   answer and report passed=True, and exempted the whole answer from the
   attribution floor. Only a pure refusal may skip.
2. PipelineResult / TraceRecord defaulted faithfulness, relevancy, precision
   and recall to 1.0, so every path without a verifier wrote a perfect score
   to telemetry. Relevancy/precision/recall are never computed at serve time.
3. format_final_answer gave an unmeasured fast-tier answer confidence 8.0
   (rendered as "Strong retrieved and verified support") and score 1.0.
4. A missing confidence became 5.0 and cleared the soft-pass gate.
"""

from __future__ import annotations

import pytest

from app.pipeline.result import PipelineResult
from app.telemetry_sink import QueryTrace
from rag.nodes import verification as verification_module
from rag.nodes.generation import format_final_answer
from rag.states import GraphState
from services.voice.register import (
    FALLBACK_RESPONSE,
    NO_TEACHING_FOUND,
    is_pure_refusal_text,
    is_refusal_text,
    strip_unsourced_attributions,
)

_MIXED = (
    "I don't have enough information on that exact wording. "
    "Sri Preethaji teaches that suffering ends the moment you observe it "
    "without judgement and return to a beautiful state of connection."
)


# ── 1. Pure refusal vs a refusal marker inside a real answer ────────────────


def test_canonical_refusals_are_pure():
    assert is_pure_refusal_text(FALLBACK_RESPONSE)
    assert is_pure_refusal_text(NO_TEACHING_FOUND)
    assert is_pure_refusal_text("Thank you for asking. " + NO_TEACHING_FOUND)


def test_marker_plus_doctrine_is_not_a_pure_refusal():
    assert is_refusal_text(_MIXED)  # the substring matcher still sees it (cache must)
    assert not is_pure_refusal_text(_MIXED)


def test_marker_plus_teacher_name_residue_is_not_pure():
    assert not is_pure_refusal_text(FALLBACK_RESPONSE + " Sri Krishnaji agrees.")


def test_attribution_floor_strips_claims_next_to_a_refusal_marker():
    surviving, removed = strip_unsourced_attributions(_MIXED)
    assert removed == 1
    assert "Sri Preethaji teaches" not in surviving


def test_attribution_floor_leaves_a_pure_refusal_untouched():
    assert strip_unsourced_attributions(NO_TEACHING_FOUND) == (NO_TEACHING_FOUND, 0)


def _verify_state(answer: str) -> dict:
    return {
        "answer": answer,
        "question": "How do I end suffering?",
        "relevant_docs": [{"text": "Observe suffering without judgement.", "source_url": "u"}],
        "query_tier": "standard",
        "intent": "QUERY",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("node", ["verify_answer", "combined_grade_and_verify"])
async def test_mixed_answer_is_not_auto_passed_by_the_abstention_skip(node, monkeypatch):
    """A mixed answer must go past the skip branch into real verification."""
    fn = getattr(verification_module, node)
    reached = []

    def _record(*_a, **_k):
        reached.append(True)
        raise RuntimeError("scorer reached")

    monkeypatch.setattr(verification_module, "_verification_docs", _record)
    result = await fn(GraphState(**_verify_state(_MIXED)))
    assert reached, "mixed refusal+doctrine answer skipped verification"
    assert result["verification"]["passed"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "node", ["reflect_on_answer", "verify_answer", "combined_grade_and_verify"]
)
async def test_a_crashing_verifier_abstains_instead_of_keeping_a_prior_pass(node, monkeypatch):
    """The node error boundary used to return no verdict, so an earlier pass
    in state (fast-tier check, reflection) survived a verifier crash."""
    fn = getattr(verification_module, node)

    def _boom(*_a, **_k):
        raise RuntimeError("verifier down")

    monkeypatch.setattr(verification_module, "_verification_docs", _boom)
    monkeypatch.setattr(verification_module, "_BOUNDED_ABSTENTION_RE", None)  # force a crash early
    state = _verify_state(_MIXED)
    state.update(
        is_faithful=True, verification={"passed": True, "method": "lettuce_detect_fast_tier"}
    )
    result = await fn(GraphState(**state))
    assert result["fallback"] is True
    assert result["is_faithful"] is False
    assert result["verification"]["passed"] is False
    assert result["verification"]["citations_verified"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("node", ["verify_answer", "combined_grade_and_verify"])
async def test_pure_refusal_still_skips_verification(node):
    fn = getattr(verification_module, node)
    result = await fn(GraphState(**_verify_state(FALLBACK_RESPONSE)))
    assert "abstention" in result["verification"]["details"]
    assert result["faithfulness_score"] == 0.0


# ── 2. Unmeasured scores are None, not 1.0 ──────────────────────────────────


def test_pipeline_result_does_not_default_to_perfect_scores():
    result = PipelineResult(final_answer="x", intent="CASUAL")
    assert result.faithfulness_score is None
    assert result.answer_relevancy is None
    assert result.context_precision is None
    assert result.context_recall is None


def test_query_trace_does_not_default_to_perfect_scores():
    trace = QueryTrace()
    assert trace.faithfulness is None
    assert trace.answer_relevancy is None
    assert trace.context_precision is None
    assert trace.context_recall is None


# ── 3/4. format_final_answer never invents confidence ───────────────────────

_ANSWER = (
    "Meditation is the practice of resting attention on the breath. "
    "When the mind settles, stillness arises on its own."
)


def _final_state(**overrides) -> GraphState:
    base = dict(
        answer=_ANSWER,
        citations=["https://doc.example/teaching"],
        relevant_docs=[{"title": "Doc One", "source_url": "https://doc.example/teaching"}],
        is_faithful=True,
        verification={"passed": True},
        intent="QUERY",
        query_tier="tier2_simple",
        retry_count=1,
    )
    base.update(overrides)
    return GraphState(**base)


@pytest.mark.asyncio
async def test_unmeasured_fast_tier_answer_gets_no_invented_confidence():
    result = await format_final_answer(_final_state())
    assert result["faithfulness_score"] is None
    assert result["confidence_score"] is None
    assert result["verification"]["measured"] is False


@pytest.mark.asyncio
async def test_measured_fast_tier_answer_reports_its_real_score():
    result = await format_final_answer(
        _final_state(
            faithfulness_score=0.9,
            verification={"passed": True, "method": "lettuce_detect_fast_tier", "score": 0.9},
        )
    )
    assert result["faithfulness_score"] == 0.9
    assert result["confidence_score"] == pytest.approx(9.0)


@pytest.mark.asyncio
async def test_missing_confidence_does_not_become_a_middling_score():
    result = await format_final_answer(_final_state(query_tier="standard"))
    assert result.get("confidence_score") != 5.0
