"""Deterministic node-level performance-regression guard.

Not a load test — no live services, no network, no LLM calls. This times a
handful of pure CPU functions on the hot retrieval-fusion path
(``rag/nodes/utils.py``) against synthetic input of a fixed, production-like
shape, and asserts wall time stays under a budget set at roughly 30-50x the
measured baseline (see ``_measure_baseline_ms`` in this file's
``if __name__ == "__main__":`` block). The generous multiplier absorbs normal
CI-runner noise; it is not generous enough to miss an accidental O(n^2)/O(n^3)
regression, an accidentally-introduced sleep/network call, or a retry loop
without backoff landing on a function this hot.

ponytail: wall-clock, not a profiler — the ceiling is "did this get an order
of magnitude slower", not micro-benchmarking. Upgrade to pytest-benchmark (or
promote to a live-endpoint p95 check) if per-request latency work needs finer
signal than this.

Budgets are pydantic config, not bare magic numbers in each assertion, per
the repo's "pydantic over hardcoding" convention.
"""

from __future__ import annotations

import random
import time

from pydantic import BaseModel, Field

from rag.nodes.utils import _fuse_docs, stable_document_key


class NodeBudget(BaseModel):
    """A wall-clock ceiling for one deterministic node-utility benchmark."""

    name: str
    budget_ms: float = Field(gt=0)
    description: str


# Budgets measured 2026-09-16 on this machine (Apple Silicon, no other load):
#   fuse_docs_rrf_dbsf   : ~0.52ms per call (200 docs, 4 ranked lists of 50)
#   stable_document_key  : ~0.0022ms per call
# Budgets below are ~30-50x those measurements — enough headroom for a slower
# CI runner, not enough to hide a real algorithmic regression.
BUDGETS = {
    "fuse_docs": NodeBudget(
        name="fuse_docs",
        budget_ms=25.0,
        description="_fuse_docs (RRF + DBSF) over 4 ranked lists x 50 docs = 200 candidates",
    ),
    "stable_document_key": NodeBudget(
        name="stable_document_key",
        budget_ms=50.0,
        description="stable_document_key over 500 calls (fusion's per-doc identity hash)",
    ),
}


def _make_ranked_lists(n_lists: int, n_docs: int) -> list[list[dict]]:
    rng = random.Random(42)  # noqa: S311 - deterministic fixture, not security-sensitive
    return [
        [
            {
                "point_id": f"p{listi}-{i}",
                "source_id": f"src{i % 50}",
                "text": f"doc text number {listi}-{i} " * 5,
                "score": rng.random(),
            }
            for i in range(n_docs)
        ]
        for listi in range(n_lists)
    ]


def test_fuse_docs_rrf_and_dbsf_stay_within_budget():
    lists = _make_ranked_lists(n_lists=4, n_docs=50)
    budget = BUDGETS["fuse_docs"]

    start = time.perf_counter()
    _fuse_docs(lists, strategy="rrf")
    _fuse_docs(lists, strategy="dbsf")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < budget.budget_ms, (
        f"{budget.name} took {elapsed_ms:.2f}ms, budget {budget.budget_ms}ms "
        f"({budget.description}). Likely an accidental O(n^2)+ regression or a "
        "blocking call added to a hot retrieval-fusion function."
    )


def test_stable_document_key_stays_within_budget():
    lists = _make_ranked_lists(n_lists=1, n_docs=1)
    doc = lists[0][0]
    budget = BUDGETS["stable_document_key"]

    start = time.perf_counter()
    for _ in range(500):
        stable_document_key(doc)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < budget.budget_ms, (
        f"{budget.name} took {elapsed_ms:.2f}ms for 500 calls, budget "
        f"{budget.budget_ms}ms ({budget.description})."
    )


if __name__ == "__main__":  # runnable self-check / baseline re-measurement
    lists = _make_ranked_lists(n_lists=4, n_docs=50)
    start = time.perf_counter()
    for _ in range(20):
        _fuse_docs(lists, strategy="rrf")
        _fuse_docs(lists, strategy="dbsf")
    per_call_ms = (time.perf_counter() - start) * 1000 / 40
    print(f"fuse_docs: {per_call_ms:.4f} ms/call (budget {BUDGETS['fuse_docs'].budget_ms}ms)")

    doc = lists[0][0]
    start = time.perf_counter()
    for _ in range(1000):
        stable_document_key(doc)
    per_call_ms = (time.perf_counter() - start) * 1000 / 1000
    print(
        f"stable_document_key: {per_call_ms:.5f} ms/call "
        f"(budget {BUDGETS['stable_document_key'].budget_ms}ms / 500 calls)"
    )
