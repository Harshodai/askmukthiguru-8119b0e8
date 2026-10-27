import json
import math
from pathlib import Path

import pytest
from benchmarks.check_golden_retrieval_drift import evaluate_item, validate_golden
from benchmarks.retrieval_metrics import first_relevant_rank, summarize_rankings
from evaluation.data_shape_validator import (
    DataShapeViolationError,
    validate_chunk_data_shape,
)
from evaluation.fp_rank_metrics import (
    average_precision_at_k,
    map_at_k,
    mean_ndcg_at_k,
    mrr,
    ndcg_at_k,
    reciprocal_rank,
)
from evaluation.run_golden_eval import (
    generate_release_artifact,
    score_golden_eval,
)


def test_rank_metrics_distinguish_chunk_precision_from_source_recall() -> None:
    metrics = summarize_rankings(
        [
            (["wrong", "gold", "gold"], {"gold"}),
            (["wrong"], {"gold"}),
        ],
        ks=(1, 2, 3),
    )

    assert metrics == {
        "n_queries": 2,
        "recall_at_k": {1: 0.0, 2: 0.5, 3: 0.5},
        "precision_at_k": {1: 0.0, 2: 0.25, 3: 0.3333},
        "mrr": 0.25,
    }
    assert first_relevant_rank(["wrong", "gold"], {"gold"}) == 2
    assert first_relevant_rank(["wrong"], {"gold"}) is None


def test_drift_check_uses_source_level_term_coverage_and_chunk_count() -> None:
    item = {
        "id": "q1",
        "must_mention": ["golden light", "humming"],
        "correct_sources": ["video-1"],
        "correct_chunks": 2,
    }
    check = evaluate_item(item, {"video-1": ["Golden light practice", "Use humming"]})

    assert check["drifted"] is False
    assert check["actual_correct_chunks"] == 2

    check = evaluate_item(item, {"video-1": ["Golden light practice"]})
    assert check["drifted"] is True
    assert check["sources_missing_terms"] == {"video-1": ["humming"]}


def test_golden_schema_rejects_empty_or_duplicate_labels() -> None:
    errors = validate_golden(
        {
            "items": [
                {"id": "q", "correct_sources": [], "must_mention": [], "correct_chunks": 0},
                {"id": "q", "correct_sources": ["s"], "must_mention": ["t"], "correct_chunks": 1},
            ]
        }
    )

    assert any("correct_sources" in error for error in errors)
    assert any("unique" in error for error in errors)


# --- Phase 5 Tests (DE-5.2, DE-5.3, DE-5.4, DE-5.5) ---


def test_ranking_metrics_calculation() -> None:
    """MRR, MAP@k, NDCG@k on known fixture rankings."""
    q1 = [True, False, False, False, False]
    q2 = [False, True, False, False, False]
    q3 = [False, False, True, False, False]
    q4 = [False, False, False, False, False]

    assert reciprocal_rank(q1) == 1.0
    assert reciprocal_rank(q2) == 0.5
    assert round(reciprocal_rank(q3), 4) == 0.3333
    assert reciprocal_rank(q4) == 0.0

    assert average_precision_at_k(q1, k=5) == 1.0
    assert average_precision_at_k(q2, k=5) == 0.5
    assert round(average_precision_at_k(q3, k=5), 4) == 0.3333
    assert average_precision_at_k(q4, k=5) == 0.0

    assert ndcg_at_k(q1, k=10) == 1.0
    assert ndcg_at_k(q2, k=10) == round(1.0 / math.log2(3), 4)
    assert ndcg_at_k(q3, k=10) == 0.5
    assert ndcg_at_k(q4, k=10) == 0.0

    all_hits = [q1, q2, q3, q4]
    # MRR = (1.0 + 0.5 + 1/3 + 0.0) / 4 = 1.833333 / 4 ≈ 0.4583
    assert mrr(all_hits) == 0.4583
    # MAP@5 = (1.0 + 0.5 + 1/3 + 0.0) / 4 ≈ 0.4583
    assert map_at_k(all_hits, k=5) == 0.4583
    assert map_at_k(all_hits, k=10) == 0.4583
    # Mean NDCG@10 = (1.0 + 0.6309 + 0.5 + 0.0) / 4 = 2.1309 / 4 ≈ 0.5327
    assert mean_ndcg_at_k(all_hits, k=10) == 0.5327


def test_per_query_class_breakdown() -> None:
    """Metrics properly aggregated per question class."""
    items = [
        {"id": "q-faq", "question": "What is meditation?", "question_class": "faq", "must_mention": ["stillness"]},
        {"id": "q-comp", "question": "Meditation vs contemplation", "question_class": "comparative", "must_mention": ["focus"]},
        {"id": "q-hop", "question": "How does karma affect rebirth?", "question_class": "multi_hop", "must_mention": ["action"]},
        {"id": "q-dist", "question": "I feel hopeless", "question_class": "distress_adjacent", "expected_intent": "DISTRESS"},
        {"id": "q-indic", "question": "ध्यान क्या है?", "question_class": "indic_language", "must_mention": ["शांति"]},
        {"id": "q-std", "question": "Explain the teaching of oneness", "question_class": "standard", "must_mention": ["oneness"]},
    ]
    answers = [
        "Meditation is inner stillness.",
        "Meditation focuses inward while contemplation ponders.",
        "Karma is action determining rebirth.",
        "We are here for you, please reach out to support.",
        "ध्यान आंतरिक शांति है।",
        "Oneness is dissolution of division.",
    ]
    contexts = [
        ["Stillness in meditation is key."],
        ["Other topic", "Focus is essential."],
        ["Irrelevant text"],
        ["Support and care"],
        ["शांति की प्राप्ति ध्यान से होती है।"],
        ["Oneness is universal."],
    ]

    report = score_golden_eval(
        items=items,
        answers=answers,
        contexts=contexts,
        refs=[it.get("question", "") for it in items],
        questions=[it.get("question", "") for it in items],
    )

    breakdown = report["per_class_breakdown"]
    assert "faq" in breakdown
    assert "comparative" in breakdown
    assert "multi_hop" in breakdown
    assert "distress_adjacent" in breakdown
    assert "indic_language" in breakdown
    assert "standard" in breakdown

    assert breakdown["faq"]["count"] == 1
    assert breakdown["faq"]["mrr"] == 1.0
    assert breakdown["faq"]["map_at_10"] == 1.0
    assert breakdown["faq"]["ndcg_at_10"] == 1.0
    assert "generation_scores" in breakdown["faq"]

    assert breakdown["comparative"]["count"] == 1
    assert breakdown["comparative"]["mrr"] == 0.5
    assert breakdown["comparative"]["map_at_10"] == 0.5

    assert breakdown["multi_hop"]["count"] == 1
    assert breakdown["multi_hop"]["mrr"] == 0.0

    assert "retrieval_metrics" in report
    assert "mrr" in report["retrieval_metrics"]
    assert "map_at_5" in report["retrieval_metrics"]
    assert "map_at_10" in report["retrieval_metrics"]
    assert "ndcg_at_10" in report["retrieval_metrics"]


def test_data_shape_assertions_pass_clean() -> None:
    """Clean chunks pass shape assertions without error."""
    chunks = [
        f"In this passage number {i}, the seeker learns that inner peace arises from observing thoughts without judgment. "
        "When the mind becomes quiet, awareness expands beyond the limited sense of self into a state of profound connection. "
        "Daily practice of mindful breathing and meditation anchors this wisdom in everyday life."
        for i in range(10)
    ]
    result = validate_chunk_data_shape(
        chunks=chunks,
        min_mean_length=200,
        max_artifact_rate=0.0,
        max_duplicate_rate=0.05,
    )
    assert result["count"] == 10
    assert result["mean_length"] >= 200
    assert result["p95_length"] >= result["p05_length"]
    assert result["duplicate_rate"] == 0.0
    assert result["artifact_rate"] == 0.0


def test_data_shape_assertions_fail_halved_mean_length() -> None:
    """Truncated chunks fail when mean length is below minimum."""
    chunks = [f"Truncated chunk {i}." for i in range(10)]
    with pytest.raises(DataShapeViolationError) as exc_info:
        validate_chunk_data_shape(chunks, min_mean_length=200)
    assert "below minimum" in str(exc_info.value)


def test_data_shape_assertions_fail_on_artifacts() -> None:
    """Chunks contaminated with LLM reasoning artifacts fail."""
    chunks = [
        f"Clean doctrine content number {i} on the nature of suffering and freedom. " * 5
        for i in range(5)
    ]
    chunks.append("**Analyze the Input** and identify key themes in spiritual doctrine.")
    with pytest.raises(DataShapeViolationError) as exc_info:
        validate_chunk_data_shape(chunks, min_mean_length=100, max_artifact_rate=0.0)
    assert "Artifact rate" in str(exc_info.value)


def test_release_eval_artifact_generation(tmp_path: Path) -> None:
    """Release JSON artifact written with full required structure."""
    report = {
        "questions_total": 5,
        "questions_failed": 0,
        "scoring_method": "concept_overlap_fallback",
        "judge_metrics_pass": True,
        "diversity_pass": True,
        "retrieval_metrics": {
            "mrr": 0.85,
            "map_at_5": 0.80,
            "map_at_10": 0.82,
            "ndcg_at_10": 0.88,
        },
        "per_class_breakdown": {
            "faq": {"count": 2, "mrr": 1.0, "map_at_10": 1.0, "ndcg_at_10": 1.0, "generation_scores": {"faithfulness": 0.9}},
            "standard": {"count": 3, "mrr": 0.75, "map_at_10": 0.70, "ndcg_at_10": 0.80, "generation_scores": {"faithfulness": 0.85}},
        },
        "faithfulness": 0.88,
        "answer_relevancy": 0.82,
        "citation_correctness": {
            "diversity_violations": 0,
            "valid_citations_rate": 1.0,
            "passed": True,
        },
        "abstention_stats": {
            "expected_refusal_count": 1,
            "expected_refusal_abstained": 1,
            "expected_refusal_rate": 1.0,
            "false_refusal_count": 0,
            "false_refusal_rate": 0.0,
        },
    }

    out_file = tmp_path / "test-corpus-release-eval.json"
    artifact = generate_release_artifact(report, output_path=out_file)

    assert out_file.exists()
    saved = json.loads(out_file.read_text())

    assert saved["release_verdict"] == "PASS"
    assert "retrieval_metrics" in saved
    assert saved["retrieval_metrics"]["mrr"] == 0.85
    assert saved["retrieval_metrics"]["map_at_5"] == 0.80
    assert saved["retrieval_metrics"]["map_at_10"] == 0.82
    assert saved["retrieval_metrics"]["ndcg_at_10"] == 0.88

    assert "per_class_breakdown" in saved
    assert "faq" in saved["per_class_breakdown"]
    assert "standard" in saved["per_class_breakdown"]

    assert saved["faithfulness"] == 0.88
    assert saved["relevancy"] == 0.82
    assert "citation_correctness" in saved
    assert saved["citation_correctness"]["passed"] is True
    assert "abstention_stats" in saved
    assert saved["abstention_stats"]["false_refusal_count"] == 0
