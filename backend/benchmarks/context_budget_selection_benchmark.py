#!/usr/bin/env python3
"""Free (no LLM calls) benchmark comparing the old blind hash-sort-then-truncate
knowledge assembly against the new relevance-aware-selection-then-hash-sort
approach in rag/nodes/generation.py's context_engineer.

Uses the real production functions (sort_docs_canonically, cap_to_token_budget,
ContextBudgetManager) against many random doc-set configurations, measuring
whether the single highest-relevance doc survives budget truncation and the
average relevance of what actually gets kept — the exact question that matters
for answer quality, without needing an LLM call to answer it.

Run: python3 benchmarks/context_budget_selection_benchmark.py
"""

import random
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from rag.compressor import cap_to_token_budget  # noqa: E402
from rag.doc_utils import sort_docs_canonically  # noqa: E402
from services.context_compressor import ContextBudgetManager  # noqa: E402

KNOWLEDGE_BUDGET = 1536  # fast/tier2_simple tier, the tightest budget — most likely to truncate


def _make_doc_set(n_docs: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    docs = []
    for i in range(n_docs):
        relevance = rng.uniform(0.05, 0.99)
        # length uncorrelated with relevance on purpose — a short, highly relevant
        # doc and a long, barely-relevant one are equally plausible in real retrieval
        length_chars = rng.randint(800, 3000)
        text = f"doc-{i}-{seed} " * (length_chars // 8)
        docs.append(
            {
                "title": f"Doc {i}",
                "text": text,
                "source_url": f"https://example/{i}",
                "rerank_score": relevance,
            }
        )
    return docs


def old_method(docs: list[dict]) -> list[dict]:
    """Current production behavior: hash-sort first, then blind tail-truncate the joined string."""
    ordered = sort_docs_canonically(docs)
    joined = "\n\n".join(d["text"] for d in ordered)
    capped = cap_to_token_budget(joined, KNOWLEDGE_BUDGET)
    # A doc "survived" if any non-trivial fraction of its text appears in the capped output
    survived = [d for d in ordered if d["text"][:100] in capped]
    return survived


def new_method(docs: list[dict]) -> list[dict]:
    """New behavior: relevance-select first (ContextBudgetManager), then hash-sort survivors."""
    wrapped = [{"content": d["text"], "relevance": d["rerank_score"], "_orig": d} for d in docs]
    mgr = ContextBudgetManager(
        total_budget=KNOWLEDGE_BUDGET, system_prompt_reserve=0.0001, history_reserve=0.0001
    )
    result = mgr.compress(wrapped)
    return [w["_orig"] for w in result["selected_chunks"]]


def run_benchmark(n_trials: int = 200) -> dict:
    top_doc_survived_old = 0
    top_doc_survived_new = 0
    avg_relevance_old = []
    avg_relevance_new = []

    for trial in range(n_trials):
        n_docs = random.Random(trial).randint(3, 8)
        docs = _make_doc_set(n_docs, seed=trial)
        top_doc = max(docs, key=lambda d: d["rerank_score"])

        old_kept = old_method(docs)
        new_kept = new_method(docs)

        if any(d is top_doc for d in old_kept):
            top_doc_survived_old += 1
        if any(d is top_doc for d in new_kept):
            top_doc_survived_new += 1

        if old_kept:
            avg_relevance_old.append(sum(d["rerank_score"] for d in old_kept) / len(old_kept))
        if new_kept:
            avg_relevance_new.append(sum(d["rerank_score"] for d in new_kept) / len(new_kept))

    return {
        "trials": n_trials,
        "top_doc_survival_rate_old": top_doc_survived_old / n_trials,
        "top_doc_survival_rate_new": top_doc_survived_new / n_trials,
        "avg_relevance_of_kept_content_old": sum(avg_relevance_old) / len(avg_relevance_old)
        if avg_relevance_old
        else 0.0,
        "avg_relevance_of_kept_content_new": sum(avg_relevance_new) / len(avg_relevance_new)
        if avg_relevance_new
        else 0.0,
    }


if __name__ == "__main__":
    results = run_benchmark()
    print("\n" + "=" * 60)
    print("CONTEXT BUDGET SELECTION: OLD (hash-truncate) vs NEW (relevance-select)")
    print("=" * 60)
    for k, v in results.items():
        print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")
    print("=" * 60)

    assert results["top_doc_survival_rate_new"] >= results["top_doc_survival_rate_old"], (
        "New method should never lose to the old one on top-doc survival"
    )
    assert (
        results["avg_relevance_of_kept_content_new"] >= results["avg_relevance_of_kept_content_old"]
    ), "New method should never lose to the old one on average kept relevance"
    print("\nPASS: new method matches or beats the old one on both metrics.")
