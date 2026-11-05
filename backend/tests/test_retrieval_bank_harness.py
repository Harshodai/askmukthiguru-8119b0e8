"""T2-02: Retrieval Bank Harness and IR Metrics Tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is in python path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.retrieval_bank.harness import (
    evaluate_retrieval_system,
    load_retrieval_bank,
)
from evals.retrieval_bank.metrics import (
    compute_confidence_interval,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_recall_at_k():
    relevant = {"doc1", "doc2"}
    assert recall_at_k(["doc1", "doc3", "doc4"], relevant, k=1) == 0.5
    assert recall_at_k(["doc1", "doc3", "doc2"], relevant, k=3) == 1.0
    assert recall_at_k(["doc3", "doc4"], relevant, k=5) == 0.0
    assert recall_at_k([], relevant, k=5) == 0.0
    assert recall_at_k(["doc1"], set(), k=5) == 0.0


def test_precision_at_k():
    relevant = {"doc1", "doc2"}
    assert precision_at_k(["doc1", "doc3", "doc4"], relevant, k=1) == 1.0
    assert precision_at_k(["doc1", "doc3", "doc4"], relevant, k=3) == 1.0 / 3.0
    assert precision_at_k(["doc3", "doc4"], relevant, k=2) == 0.0
    assert precision_at_k([], relevant, k=0) == 0.0


def test_reciprocal_rank():
    relevant = {"doc2"}
    assert reciprocal_rank(["doc1", "doc2", "doc3"], relevant) == 0.5
    assert reciprocal_rank(["doc2", "doc1"], relevant) == 1.0
    assert reciprocal_rank(["doc1", "doc3"], relevant) == 0.0
    assert reciprocal_rank([], relevant) == 0.0


def test_ndcg_at_k():
    grades = {"doc1": 3.0, "doc2": 2.0, "doc3": 1.0}
    # Perfect ranking
    assert ndcg_at_k(["doc1", "doc2", "doc3"], grades, k=3) == 1.0
    # Reversed ranking
    reversed_ndcg = ndcg_at_k(["doc3", "doc2", "doc1"], grades, k=3)
    assert 0.0 < reversed_ndcg < 1.0
    # No relevant items
    assert ndcg_at_k(["doc4", "doc5"], grades, k=3) == 0.0


def test_confidence_interval():
    vals = [0.8, 0.82, 0.79, 0.81, 0.80]
    mean, low, high = compute_confidence_interval(vals)
    assert 0.79 <= mean <= 0.81
    assert low < mean < high


def test_retrieval_bank_harness_execution():
    queries = load_retrieval_bank()
    assert len(queries) >= 8

    # Mock retrieve function returning perfect hits for testing
    def mock_retrieve(query: str, teacher: str) -> list[str]:
        for q in queries:
            if q["query"] == query:
                return list(q["relevant_ids"]) + ["distractor_1", "distractor_2"]
        return []

    res = evaluate_retrieval_system(queries, mock_retrieve, k_values=(1, 5, 10))
    summary = res["summary"]
    assert summary["num_queries"] == len(queries)

    # With perfect top hits, Recall@5 and Recall@10 should be 1.0
    assert summary["metrics"]["recall@5"]["mean"] == 1.0
    assert summary["metrics"]["recall@10"]["mean"] == 1.0
    assert summary["metrics"]["mrr"]["mean"] == 1.0
    assert len(summary["metrics"]["recall@10"]["ci_95"]) == 2
