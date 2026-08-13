"""Regressions for typed answer evidence and its transport paths."""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.coalescer import RedisCoalescer
from app.pipeline.result import AnswerEvidence, PipelineResult
from app.pipeline.stages.glue_stages import _answer_evidence


def context(corpus_id="preethaji-approved"):
    return SimpleNamespace(state={"corpus_id": corpus_id})


def test_evidence_uses_structured_retrieval_facts_only():
    evidence = _answer_evidence(
        context(),
        {
            "citations_verified": True,
            "corpus_release_version": 2,
        },
        [
            {
                "source_url": "https://example.org/talk",
                "source_version": 3,
                "score": 0.91,
            },
            {
                "source_url": "https://example.org/second",
                "metadata": {"source_version": 2, "score": 0.84},
            },
        ],
        {"confidence_score": 8.4},
    )
    assert evidence.corpus_id == "preethaji-approved"
    assert evidence.release_version == 3
    assert evidence.source_count == 2
    assert evidence.top_source_score == 0.91
    assert evidence.citations_verified is True
    assert evidence.evidence_support_label == "Teaching-supported"


def test_no_retrieval_never_manufactures_support():
    evidence = _answer_evidence(
        context(),
        {"citations_verified": False},
        [],
        {"confidence_score": 9.9},
    )
    assert evidence.source_count == 0
    assert evidence.top_source_score is None
    assert evidence.release_version is None
    assert evidence.evidence_support_label == "Limited support"


def test_result_serialisation_and_latency_keep_typed_evidence():
    evidence = AnswerEvidence(
        corpus_id="askmukthiguru",
        release_version=4,
        model_policy_id="gemini-flash-budget-v1",
        evidence_support_label="Partially supported",
        source_count=1,
        top_source_score=0.73,
        citations_verified=True,
    )
    result = PipelineResult(final_answer="Namaste", answer_evidence=evidence)
    assert result.with_latency(42).answer_evidence == evidence
    response = result.to_chat_response()
    assert response["answer_evidence"]["release_version"] == 4
    payload = json.loads(RedisCoalescer._serialize_result(result))
    round_trip = RedisCoalescer._deserialize_result(payload)
    assert isinstance(round_trip.answer_evidence, AnswerEvidence)
    assert round_trip.answer_evidence == evidence
