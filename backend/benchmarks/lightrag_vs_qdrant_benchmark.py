#!/usr/bin/env python3
"""Benchmark: LightRAG-augmented retrieval vs. Qdrant-only retrieval.

Runs the same query set through ``retrieve_for_single_query`` twice:
1. With LightRAG enabled (``lightrag=...``)
2. With LightRAG disabled (``lightrag=None``)

Reports:
- Per-query latency delta
- Result overlap (Jaccard index on doc IDs)
- Coverage metrics (how many unique sources each variant surfaces)
- Token count difference in retrieved context

Usage:
    cd backend && python -m benchmarks.lightrag_vs_qdrant_benchmark
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap path + env
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

from benchmarks.question_bank import QUERIES  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SAMPLE_SIZE = int(os.getenv("LIGHTRAG_SAMPLE_SIZE", "20"))
"""Number of queries to benchmark (default 20 for speed)."""

MAX_CONCURRENT = int(os.getenv("LIGHTRAG_MAX_CONCURRENT", "4"))
"""Concurrent retrieval calls to avoid overwhelming Qdrant."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class RetrievalComparison:
    query: str
    category: str
    with_lightrag_time_ms: float = 0.0
    without_lightrag_time_ms: float = 0.0
    with_lightrag_doc_count: int = 0
    without_lightrag_doc_count: int = 0
    overlap_ratio: float = 0.0
    only_lightrag_ids: list[str] = field(default_factory=list)
    only_qdrant_ids: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class BenchmarkReport:
    total_queries: int = 0
    errors: int = 0
    avg_with_lightrag_ms: float = 0.0
    avg_without_lightrag_ms: float = 0.0
    avg_overlap: float = 0.0
    avg_doc_delta: float = 0.0
    only_lightrag_coverage: int = 0
    only_qdrant_coverage: int = 0
    samples: list[RetrievalComparison] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Core benchmark
# ---------------------------------------------------------------------------


async def benchmark_single_query(
    query_text: str,
    category: str,
    *,
    embedder,
    qdrant,
    lightrag,
) -> RetrievalComparison:
    """Run one query with and without LightRAG."""
    from rag.nodes.retrieval import retrieve_for_single_query

    comp = RetrievalComparison(query=query_text, category=category)

    async def _run(lightrag_enabled: bool) -> tuple[list[dict], float]:
        start = time.perf_counter()
        results = await retrieve_for_single_query(
            query=query_text,
            chat_history=[],
            hyde_text=None,
            intent="QUERY",
            selected_clusters=[],
            embedder=embedder,
            qdrant=qdrant,
            lightrag=lightrag if lightrag_enabled else None,
        )
        elapsed = (time.perf_counter() - start) * 1000
        return results, elapsed

    try:
        with_results, with_time = await _run(lightrag_enabled=True)
        without_results, without_time = await _run(lightrag_enabled=False)
    except Exception as exc:
        comp.error = f"{type(exc).__name__}: {exc}"
        return comp

    with_ids = {str(d.get("id", d.get("doc_id", hash(str(d))))) for d in with_results}
    without_ids = {str(d.get("id", d.get("doc_id", hash(str(d))))) for d in without_results}

    comp.with_lightrag_time_ms = round(with_time, 2)
    comp.without_lightrag_time_ms = round(without_time, 2)
    comp.with_lightrag_doc_count = len(with_results)
    comp.without_lightrag_doc_count = len(without_results)
    comp.overlap_ratio = round(_jaccard(with_ids, without_ids), 3)
    comp.only_lightrag_ids = sorted(with_ids - without_ids)
    comp.only_qdrant_ids = sorted(without_ids - with_ids)

    return comp


async def run_benchmark():
    """Entry point: sample queries, run comparisons, print report."""
    # Lazy imports so we fail fast if the app isn't bootstrapped
    from app.dependencies import get_container
    from services.embedding_service import EmbeddingService
    from services.lightrag_service import LightRAGService
    from services.qdrant_service import QdrantService

    container = get_container()
    embedder: EmbeddingService = container.embedding
    qdrant: QdrantService = container.qdrant
    lightrag: LightRAGService = getattr(container, "lightrag", None)

    # Collect flat list of (query, category) tuples
    test_cases: list[tuple[str, str]] = []
    for category, items in QUERIES.items():
        for item in items:
            if isinstance(item, dict):
                qtext = item.get("query") or item.get("q")
                if qtext:
                    test_cases.append((qtext, category))
            elif isinstance(item, str):
                test_cases.append((item, category))

    import random

    random.seed(42)
    test_cases = test_cases[: min(SAMPLE_SIZE, len(test_cases))]

    print(f"Running LightRAG vs Qdrant benchmark on {len(test_cases)} queries...")
    print(f"  LightRAG enabled: {'yes' if lightrag else 'no (control)'}\n")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    results: list[RetrievalComparison] = []

    async def _bounded_task(qtext: str, cat: str):
        async with semaphore:
            return await benchmark_single_query(
                qtext, cat, embedder=embedder, qdrant=qdrant, lightrag=lightrag
            )

    tasks = [_bounded_task(q, c) for q, c in test_cases]
    for coro in asyncio.as_completed(tasks):
        comp = await coro
        results.append(comp)
        status = "✅" if not comp.error else f"❌ {comp.error}"
        print(
            f"  [{status}] {comp.query[:60]:<60}  "
            f"Δ={comp.with_lightrag_time_ms - comp.without_lightrag_time_ms:>+6.1f}ms  "
            f"overlap={comp.overlap_ratio:.2f}"
        )

    # Assemble report
    report = BenchmarkReport()
    report.total_queries = len(results)
    report.errors = sum(1 for r in results if r.error)
    valid = [r for r in results if not r.error]

    if valid:
        report.avg_with_lightrag_ms = round(
            sum(r.with_lightrag_time_ms for r in valid) / len(valid), 2
        )
        report.avg_without_lightrag_ms = round(
            sum(r.without_lightrag_time_ms for r in valid) / len(valid), 2
        )
        report.avg_overlap = round(
            sum(r.overlap_ratio for r in valid) / len(valid), 3
        )
        report.avg_doc_delta = round(
            sum(r.with_lightrag_doc_count - r.without_lightrag_doc_count for r in valid)
            / len(valid),
            2,
        )
        report.only_lightrag_coverage = sum(len(r.only_lightrag_ids) for r in valid)
        report.only_qdrant_coverage = sum(len(r.only_qdrant_ids) for r in valid)

    report.samples = results

    # Print summary
    print("\n" + "=" * 70)
    print("LIGHTRAG vs QDRANT-ONLY  BENCHMARK REPORT")
    print("=" * 70)
    print(f"  Total queries : {report.total_queries}")
    print(f"  Errors        : {report.errors}")
    print(f"  Avg latency WITH LightRAG    : {report.avg_with_lightrag_ms} ms")
    print(f"  Avg latency WITHOUT LightRAG   : {report.avg_without_lightrag_ms} ms")
    print(f"  Avg overlap (Jaccard)          : {report.avg_overlap}")
    print(f"  Avg doc count delta (+LightRAG): {report.avg_doc_delta:+.2f}")
    print(f"  Unique docs ONLY from LightRAG : {report.only_lightrag_coverage}")
    print(f"  Unique docs ONLY from Qdrant   : {report.only_qdrant_coverage}")
    print("=" * 70)

    # Save JSON report
    report_path = Path("benchmarks/reports/lightrag_vs_qdrant_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    print(f"\nFull report saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
