from benchmarks.check_golden_retrieval_drift import evaluate_item, validate_golden
from benchmarks.retrieval_metrics import first_relevant_rank, summarize_rankings


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
