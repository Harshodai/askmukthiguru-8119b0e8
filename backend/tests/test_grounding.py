from types import SimpleNamespace

from app.grounding import grounding_state_for
from app.pipeline.pipeline_coordinator import PipelineCoordinator


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
