from types import SimpleNamespace

import pytest

from app.grounding import grounding_state_for
from app.pipeline.pipeline_coordinator import PipelineCoordinator


def test_grounded_partial_evidence_is_publicly_abstained_not_grounded():
    # Reversed 2026-10-11: verification.passed=False must never ship as grounded.
    result = SimpleNamespace(
        blocked=False,
        intent="QUERY",
        citations=["https://doc.example/teaching"],
        citations_verified=False,
        hallucination_flag=False,
        verification={
            "method": "grounded_partial_evidence",
            "partial": True,
            "passed": False,
        },
        answer_evidence=None,
    )

    assert grounding_state_for(result) == "abstained"


def test_failed_partial_without_citation_does_not_promote_to_grounded():
    result = SimpleNamespace(
        blocked=False,
        intent="QUERY",
        citations=[],
        citations_verified=True,
        hallucination_flag=False,
        verification={
            "method": "grounded_partial_evidence",
            "partial": True,
            "passed": False,
        },
        answer_evidence=None,
    )

    assert grounding_state_for(result) == "abstained"


def test_missing_citation_verification_does_not_promote_to_grounded():
    result = SimpleNamespace(
        blocked=False,
        intent="QUERY",
        citations=[{"url": "https://doc.example/teaching"}],
        citations_verified=None,
        hallucination_flag=False,
        verification={"passed": True},
        answer_evidence=SimpleNamespace(source_count=1),
    )

    assert grounding_state_for(result) == "abstained"


def test_pipeline_response_data_does_not_mark_partial_evidence_as_hallucination():
    response_data = PipelineCoordinator._build_response_data(
        {
            "confidence_score": 0.0,
            "faithfulness_score": 0.0,
            "is_faithful": False,
            "citations": ["https://doc.example/teaching"],
            "verification": {
                "passed": False,
                "method": "grounded_partial_evidence",
                "partial": True,
            },
            "reranked_docs": [],
        },
        "QUERY",
    )

    assert response_data["hallucination_flag"] is False
    assert response_data["faithfulness"] == 0.0


def _result(**kw):
    from types import SimpleNamespace

    base = {
        "blocked": False,
        "intent": "DISTRESS",
        "verification": {},
        "citations": [],
        "citations_verified": None,
        "hallucination_flag": False,
        "answer_evidence": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_distress_intent_with_a_cited_verified_answer_is_grounded():
    """Non-crisis distress runs the full pipeline; when it serves a cited, verified
    answer that answer is grounded. Run 1: "How does Breath Awareness shift the
    body out of stress?" was served a real teaching but labelled safety_redirect."""
    from app.grounding import grounding_state_for

    assert (
        grounding_state_for(_result(citations=[{"url": "u"}], citations_verified=True))
        == "grounded"
    )


def test_distress_intent_without_a_cited_answer_stays_a_safety_redirect():
    from app.grounding import grounding_state_for

    assert grounding_state_for(_result()) == "safety_redirect"


def test_crisis_intent_is_always_a_safety_redirect():
    from app.grounding import grounding_state_for

    assert (
        grounding_state_for(
            _result(intent="CRISIS", citations=[{"url": "u"}], citations_verified=True)
        )
        == "safety_redirect"
    )


def test_distress_safety_preemption_is_a_safety_redirect_even_with_internal_citations():
    """Live 2026-09-26: a distress pre-emption response carried internal citations
    (later stripped) and was labelled grounded with zero public sources."""
    from app.grounding import grounding_state_for

    r = _result(
        citations=[{"url": "u"}],
        citations_verified=True,
        verification={
            "passed": True,
            "method": "distress_safety_preemption",
            "citations_verified": True,
        },
    )
    assert grounding_state_for(r) == "safety_redirect"


def test_missing_faithfulness_score_is_none_not_fabricated_zero():
    """Defect 3: when verification never ran, `faithfulness_score` is simply
    ABSENT from the graph result (not explicitly 0.0) -- e.g. a grounded,
    non-hallucinated answer whose route skipped the LettuceDetect gate. The
    old `result.get("faithfulness_score", 0.0)` default fabricated a 0.0,
    indistinguishable from a real measured failure. It must come back as
    None ("not computed") so the anomaly job (`telemetry_db.py`) excludes it
    from the faithfulness percentile instead of reading it as a hallucination."""
    response_data = PipelineCoordinator._build_response_data(
        {
            "is_faithful": True,
            "hallucination_flag": False,
            "citations": ["https://doc.example/teaching"],
            "verification": {"passed": True, "method": "some_route_that_skips_verification"},
            "reranked_docs": [],
        },
        "QUERY",
    )
    assert response_data["faithfulness"] is None


def test_explicit_zero_faithfulness_score_is_preserved():
    """A REAL computed 0.0 (verification ran and failed) must still surface
    as 0.0, not be swallowed into "not computed" just because it's falsy."""
    response_data = PipelineCoordinator._build_response_data(
        {
            "faithfulness_score": 0.0,
            "is_faithful": False,
            "hallucination_flag": True,
            "citations": [],
            "verification": {"passed": False, "method": "lettuce_detect"},
            "reranked_docs": [],
        },
        "QUERY",
    )
    assert response_data["faithfulness"] == 0.0


def test_non_rag_intent_still_defaults_to_one():
    response_data = PipelineCoordinator._build_response_data(
        {"citations": [], "verification": {}, "reranked_docs": []},
        "CASUAL",
    )
    assert response_data["faithfulness"] == 1.0


def test_grounding_rejects_explicit_false_citations_verified_with_nested_true():
    result = SimpleNamespace(
        blocked=False,
        intent="QUERY",
        citations=[{"url": "https://doc.example/teaching"}],
        citations_verified=False,
        hallucination_flag=False,
        verification={"passed": True, "citations_verified": True},
        answer_evidence=SimpleNamespace(source_count=1),
    )
    assert grounding_state_for(result) == "abstained"


def test_distress_grounding_rejects_explicit_false_citations_verified_with_nested_true():
    result = _result(
        citations=[{"url": "u"}],
        citations_verified=False,
        verification={"passed": True, "citations_verified": True},
    )
    assert grounding_state_for(result) == "safety_redirect"


def test_distress_grounding_requires_explicit_passed_in_nonempty_verification_dict():
    # Non-empty verification dict without explicit passed=True must NOT pass
    result_missing_passed = _result(
        citations=[{"url": "u"}],
        citations_verified=True,
        verification={"method": "lettuce_detect"},
    )
    assert grounding_state_for(result_missing_passed) == "safety_redirect"

    # Non-empty verification dict with passed=False must NOT pass
    result_failed = _result(
        citations=[{"url": "u"}],
        citations_verified=True,
        verification={"method": "lettuce_detect", "passed": False},
    )
    assert grounding_state_for(result_failed) == "safety_redirect"

    # Non-empty verification dict with passed=True passes
    result_passed = _result(
        citations=[{"url": "u"}],
        citations_verified=True,
        verification={"method": "lettuce_detect", "passed": True},
    )
    assert grounding_state_for(result_passed) == "grounded"


def test_distress_grounding_accepts_empty_verification_dict():
    result_empty = _result(
        citations=[{"url": "u"}],
        citations_verified=True,
        verification={},
    )
    assert grounding_state_for(result_empty) == "grounded"


@pytest.mark.asyncio
async def test_short_circuit_terminal_fallback_grounded_partial_evidence():
    """terminal_fallback in short_circuit.py produces method='grounded_partial_evidence'
    and partial=True, which grounding_state_for labels 'grounded'."""
    from rag.nodes.short_circuit import handle_fallback

    state = {
        "question": "What is the practice?",
        "reranked_docs": [
            {
                "title": "Practice Teaching",
                "source_url": "https://doc.example/practice",
                "text": "The practice of breathing brings stillness to the mind and body.",
            }
        ],
    }
    result_dict = await handle_fallback(state)
    assert result_dict["verification"]["method"] == "grounded_partial_evidence"
    assert result_dict["verification"]["partial"] is True

    result_ns = SimpleNamespace(
        blocked=False,
        intent="QUERY",
        citations=result_dict.get("citations", []),
        citations_verified=result_dict.get("citations_verified"),
        hallucination_flag=False,
        verification=result_dict.get("verification", {}),
        answer_evidence=None,
    )
    assert grounding_state_for(result_ns) == "abstained"
