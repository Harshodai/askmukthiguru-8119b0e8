"""T2-02: Frozen Retrieval Bank Harness.

Evaluates retrieval quality (Recall@k, MRR, nDCG@k) over the frozen bank,
calculating 95% confidence intervals per metric.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from evals.retrieval_bank.metrics import (
    compute_confidence_interval,
    evaluate_retrieval_query,
)

BANK_PATH = Path(__file__).resolve().parent / "bank.jsonl"


def load_retrieval_bank(path: Path | None = None) -> list[dict[str, Any]]:
    """Loads query items from the frozen retrieval bank."""
    target = path or BANK_PATH
    if not target.exists():
        raise FileNotFoundError(f"Retrieval bank not found: {target}")

    items = []
    with open(target, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def evaluate_retrieval_system(
    queries: Sequence[dict[str, Any]],
    retrieve_fn: Callable[[str, str], list[str]],
    k_values: Sequence[int] = (1, 5, 10),
) -> dict[str, Any]:
    """Runs retrieval evaluation across the query bank.

    Args:
        queries: List of query items with 'query', 'relevant_ids', 'teacher'.
        retrieve_fn: Function (query, teacher) -> list of retrieved span/point IDs.
        k_values: Ranks to evaluate.

    Returns:
        Summary dictionary with mean and 95% confidence intervals per metric.
    """
    per_metric_scores: dict[str, list[float]] = defaultdict(list)
    query_results = []

    for item in queries:
        qid = item.get("query_id", "unknown")
        query = item["query"]
        teacher = item.get("teacher", "both")
        relevant_ids = set(item.get("relevant_ids", []))

        retrieved_ids = retrieve_fn(query, teacher)

        scores = evaluate_retrieval_query(
            retrieved_ids=retrieved_ids,
            relevant_ids=relevant_ids,
            k_values=k_values,
        )

        for metric_name, val in scores.items():
            per_metric_scores[metric_name].append(val)

        query_results.append(
            {
                "query_id": qid,
                "retrieved_count": len(retrieved_ids),
                "metrics": scores,
            }
        )

    summary: dict[str, Any] = {
        "num_queries": len(queries),
        "metrics": {},
    }

    for metric_name, vals in per_metric_scores.items():
        mean, ci_low, ci_high = compute_confidence_interval(vals)
        summary["metrics"][metric_name] = {
            "mean": mean,
            "ci_95": [ci_low, ci_high],
        }

    return {
        "summary": summary,
        "queries": query_results,
    }
