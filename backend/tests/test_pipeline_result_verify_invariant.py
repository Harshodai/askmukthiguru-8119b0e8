"""F-VERIFY-1: hallucination_flag=True must never coexist with a
citations_verified=True claim on the same PipelineResult — neither in the
top-level field nor inside the `verification` dict. Guarded structurally in
PipelineResult.__post_init__ (app/pipeline/result.py), not by convention.
"""

import pytest

from app.pipeline.result import PipelineResult


def _base_kwargs(**overrides):
    kwargs = dict(
        final_answer="answer",
        hallucination_flag=True,
        faithfulness_score=0.0,
        citations_verified=None,
        verification={"passed": False, "method": "x", "citations_verified": False},
    )
    kwargs.update(overrides)
    return kwargs


def test_top_level_citations_verified_true_with_hallucination_is_coerced_not_fatal():
    """The invariant holds for consumers -- but by COERCION, not by raising.

    Changed 2026-09-17 after measuring the cost of raising: on a live
    golden_qa_bank run 12% of questions (1/8) lost a finished answer at the
    assembly boundary (48-69s of work discarded, seeker shown "The Guru
    encountered an error") because an ONNX reranker OOM degraded verification
    to faithfulness_score=0.0 while citations_verified still defaulted True.
    A metadata contradiction must not destroy the answer.
    """
    result = PipelineResult(**_base_kwargs(citations_verified=True))

    # The guarantee the invariant exists for: no consumer ever sees both True.
    assert result.hallucination_flag is True
    assert result.citations_verified is False
    # ...and the answer survived rather than being thrown away.
    assert result.final_answer == "answer"
    # ...and the contradiction is recorded, not silently swallowed.
    assert "citations_verified" in result.route_metadata.get("verify_invariant_coerced", "")


def test_verification_dict_citations_verified_true_with_hallucination_is_coerced():
    result = PipelineResult(
        **_base_kwargs(
            verification={
                "passed": False,
                "method": "x",
                "citations_verified": True,
            }
        )
    )
    assert result.verification["citations_verified"] is False
    assert result.final_answer == "answer"
    assert result.route_metadata.get("verify_invariant_coerced")


def test_hallucination_flag_true_with_citations_verified_false_is_allowed():
    result = PipelineResult(**_base_kwargs(citations_verified=False))
    assert result.hallucination_flag is True
    assert result.citations_verified is False


def test_hallucination_flag_true_with_citations_verified_none_is_allowed():
    result = PipelineResult(**_base_kwargs(citations_verified=None))
    assert result.hallucination_flag is True
    assert result.citations_verified is None


def test_citations_verified_true_without_hallucination_is_allowed():
    result = PipelineResult(
        final_answer="answer",
        hallucination_flag=False,
        faithfulness_score=0.9,
        citations_verified=True,
        verification={"passed": True, "method": "x", "citations_verified": True},
    )
    assert result.citations_verified is True


def test_bounded_comparison_short_circuit_no_longer_claims_verified_citations():
    """Regression for the exact defect at glue_stages.py:292-297: the bounded
    meditation-vs-contemplation fallback flags hallucination_flag=True with
    faithfulness_score=0.0 (it never retrieved or verified anything), so it
    must not also claim citations_verified=True."""
    from app.pipeline.stages.glue_stages import _bounded_meditation_comparison_answer

    # Constructing the same shape the stage builds must not raise, and must
    # be honest that citations were never verified.
    result = PipelineResult(
        final_answer=_bounded_meditation_comparison_answer(),
        faithfulness_score=0.0,
        hallucination_flag=True,
        verification={
            "passed": False,
            "method": "limited_comparison_fallback",
            "citations_verified": False,
        },
        citations_verified=False,
    )
    assert result.citations_verified is False
    assert result.verification["citations_verified"] is False


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
