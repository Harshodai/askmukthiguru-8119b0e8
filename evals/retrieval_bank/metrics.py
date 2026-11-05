"""T2-02: Information Retrieval Evaluation Metrics.

Implements standard ranking metrics:
- Recall@k
- Precision@k
- Mean Reciprocal Rank (MRR)
- Normalized Discounted Cumulative Gain (nDCG@k)
- 95% Confidence Intervals via bootstrap / standard error
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def recall_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    """Recall at rank k."""
    if not relevant_ids or k <= 0:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for item in top_k if item in relevant_ids)
    return hits / float(len(relevant_ids))


def precision_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    """Precision at rank k."""
    if k <= 0:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for item in top_k if item in relevant_ids)
    return hits / float(k)


def reciprocal_rank(retrieved_ids: Sequence[str], relevant_ids: set[str]) -> float:
    """Reciprocal rank of the first relevant result."""
    if not relevant_ids:
        return 0.0
    for rank, item in enumerate(retrieved_ids, start=1):
        if item in relevant_ids:
            return 1.0 / float(rank)
    return 0.0


def dcg_at_k(relevance_scores: Sequence[float], k: int) -> float:
    """Discounted Cumulative Gain at rank k."""
    score = 0.0
    for i in range(min(len(relevance_scores), k)):
        rel = relevance_scores[i]
        score += (2.0**rel - 1.0) / math.log2(i + 2.0)
    return score


def ndcg_at_k(
    retrieved_ids: Sequence[str],
    graded_relevance: dict[str, float],
    k: int,
) -> float:
    """Normalized Discounted Cumulative Gain at rank k."""
    if not graded_relevance or k <= 0:
        return 0.0

    actual_scores = [graded_relevance.get(item_id, 0.0) for item_id in retrieved_ids[:k]]
    actual_dcg = dcg_at_k(actual_scores, k)

    ideal_scores = sorted(graded_relevance.values(), reverse=True)[:k]
    ideal_dcg = dcg_at_k(ideal_scores, k)

    if ideal_dcg <= 0.0:
        return 0.0
    return actual_dcg / ideal_dcg


def compute_confidence_interval(
    values: Sequence[float],
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Computes (mean, lower_bound, upper_bound) with 95% normal approximation."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = sum(values) / float(n)
    if n == 1:
        return mean, mean, mean

    variance = sum((x - mean) ** 2 for x in values) / float(n - 1)
    std_err = math.sqrt(variance / float(n))

    # 1.96 for 95% confidence interval
    z = 1.95996 if abs(confidence - 0.95) < 0.01 else 2.576
    margin = z * std_err
    return (
        round(mean, 4),
        round(max(0.0, mean - margin), 4),
        round(min(1.0, mean + margin), 4),
    )


def evaluate_retrieval_query(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
    graded_relevance: dict[str, float] | None = None,
    k_values: Sequence[int] = (1, 5, 10),
) -> dict[str, float]:
    """Computes all ranking metrics for a single query."""
    res: dict[str, float] = {}
    for k in k_values:
        res[f"recall@{k}"] = recall_at_k(retrieved_ids, relevant_ids, k)
        res[f"precision@{k}"] = precision_at_k(retrieved_ids, relevant_ids, k)

    res["mrr"] = reciprocal_rank(retrieved_ids, relevant_ids)

    # If graded relevance is not provided, use binary relevance {id: 1.0}
    grades = graded_relevance or {id_: 1.0 for id_ in relevant_ids}
    for k in k_values:
        res[f"ndcg@{k}"] = ndcg_at_k(retrieved_ids, grades, k)

    return res
