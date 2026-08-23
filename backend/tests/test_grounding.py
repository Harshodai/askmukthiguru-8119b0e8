from types import SimpleNamespace

from app.grounding import grounding_state_for


def test_grounded_partial_evidence_is_publicly_grounded():
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

    assert grounding_state_for(result) == "grounded"


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
