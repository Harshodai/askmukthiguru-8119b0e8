#!/usr/bin/env python3
"""
quantization_pilot.py — Benchmark harness for Qdrant quantization pilots.

Compares dense retrieval on the baseline ``spiritual_wisdom`` collection (current
INT8 production schema) against a candidate pilot collection (binary /
TurboQuant / etc.). Reports recall@10, recall@50, and latency percentiles, then
emits a go/no-go verdict against fixed quality thresholds.

The harness is read-only with respect to the baseline collection. It never
creates, deletes, or mutates the pilot collection; ingestion of the pilot
collection is handled separately (Task 4).

Run:
    cd backend && LLM_PROVIDER=ollama python3 benchmarks/quantization_pilot.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add backend directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402
from services.embedding_service import EmbeddingService  # noqa: E402
from services.qdrant.client import QdrantClientManager  # noqa: E402

# Imported lazily below to avoid paying import cost during self-check.
_QuantizationSearchParams: Any = None
_SearchParams: Any = None

logger = logging.getLogger(__name__)

BASELINE_COLLECTION = "spiritual_wisdom"
DEFAULT_PILOT_COLLECTION = "spiritual_wisdom_quant_pilot"
DEFAULT_TOP_K = 50
DEFAULT_OUTPUT = "quantization_pilot_results.json"

RECALL_AT_10_THRESHOLD = 0.93
RECALL_AT_50_THRESHOLD = 0.97

FALLBACK_QUERIES = [
    "What is Deeksha?",
    "Who are Sri Preethaji and Sri Krishnaji?",
    "Where is Ekam located?",
    "Explain the Four Sacred Secrets.",
    "What is a beautiful state?",
    "How does Universal Intelligence work?",
    "What is Spiritual Right Action?",
    "What is Soul Sync meditation?",
    "How can I practice conscious breathing?",
    "What is the Power of Intention?",
    "Explain Deeksha neuroscience.",
    "What is the Oneness blessing?",
    "How do I calm my mind?",
    "What is heart intelligence?",
    "What is karma cleansing?",
    "What is the spiritual significance of Tirupati?",
    "What happens during an awakening?",
    "Who is Lokaa?",
    "What does Ekam teach about manifestation?",
    "How do feminine energies relate to spirituality?",
    "Explain the Power of Gratitude.",
    "What is the Power of Letting Go?",
    "What is self-love according to the teachings?",
    "What is family connection in the teachings?",
    "How to set a heartfelt intention?",
    "What is the Power of Rebirth?",
    "What is the role of a guru?",
    "What is Samadhi?",
    "What is the meaning of Namaste?",
    "Explain Atman and Brahman.",
    "What is the purpose of meditation?",
]


@dataclass(frozen=True)
class SearchResult:
    """A single retrieved chunk, identified by source URL and chunk index."""

    source_url: str
    chunk_index: int


@dataclass
class QueryOutcome:
    """Per-query recall and latency measurements."""

    query: str
    baseline_results: list[SearchResult]
    candidate_results: list[SearchResult]
    baseline_ms: float
    candidate_ms: float

    @property
    def recall_at_10(self) -> float:
        return _recall(self.baseline_results[:10], self.candidate_results[:10])

    @property
    def recall_at_50(self) -> float:
        return _recall(self.baseline_results, self.candidate_results)


def _load_smoke_queries(limit: int) -> list[str]:
    """Load natural-language queries from ``smoke_doctrine.py`` if available."""
    smoke_path = Path(__file__).with_name("smoke_doctrine.py")
    if not smoke_path.exists():
        return []

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("smoke_doctrine", smoke_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        queries = getattr(module, "queries", None)
        if queries is None:
            queries = getattr(module, "QUERIES", None)

        if callable(queries):
            queries = queries()

        if not queries:
            return []

        # Accept either a list of strings or a list of dicts with a "q" key.
        result: list[str] = []
        for item in queries[:limit]:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                result.append(str(item.get("q", item.get("query", ""))))

        return [q for q in result if q]
    except Exception as exc:
        logger.warning(f"Could not reuse smoke_doctrine.py queries: {exc}")
        return []


def _build_query_set(limit: int) -> list[str]:
    """Return the query set to benchmark, preferring ``smoke_doctrine.py``."""
    smoke_queries = _load_smoke_queries(limit)
    if smoke_queries:
        logger.info(f"Reusing {len(smoke_queries)} queries from smoke_doctrine.py")
        return smoke_queries[:limit]

    logger.info(f"Using built-in fallback query set ({len(FALLBACK_QUERIES)} queries)")
    return FALLBACK_QUERIES[:limit]


def _parse_hits(raw_hits: Any) -> list[SearchResult]:
    """Convert Qdrant query results into comparable identity records."""
    results: list[SearchResult] = []
    for hit in raw_hits:
        payload = getattr(hit, "payload", None) or {}
        source_url = payload.get("source_url", "")
        chunk_index = payload.get("chunk_index", 0)
        if source_url:
            results.append(SearchResult(source_url=source_url, chunk_index=chunk_index))
    return results


def _recall(baseline: list[SearchResult], candidate: list[SearchResult]) -> float:
    """Recall of baseline identities that appear in the candidate list."""
    if not baseline:
        return 0.0
    baseline_set = set(baseline)
    candidate_set = set(candidate)
    found = len(baseline_set & candidate_set)
    return found / len(baseline_set)


def _percentile(values: list[float], pct: float) -> float:
    """Return the ``pct`` percentile of ``values`` using nearest-rank logic."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = max(0, int(round((len(sorted_values) - 1) * (pct / 100.0))))
    return sorted_values[k]


def _is_quantized_collection(client_manager: QdrantClientManager, collection_name: str) -> bool:
    """Return True if the collection uses any quantization besides scalar int8."""
    try:
        info = client_manager.client.get_collection(collection_name)
        qc = getattr(info.config, "quantization_config", None)
        if qc is None:
            return False
        # Scalar int8 is the production baseline; we do not apply extra search params there.
        scalar = getattr(qc, "scalar", None)
        if scalar and getattr(scalar, "type", None) == "int8":
            return False
        return True
    except Exception as exc:
        logger.warning(f"Could not read quantization config for '{collection_name}': {exc}")
        return False


def _quantization_search_params() -> Any:
    """Build SearchParams with rescore + oversampling for quantized collections."""
    global _QuantizationSearchParams, _SearchParams
    if _QuantizationSearchParams is None:
        from qdrant_client.http.models import QuantizationSearchParams, SearchParams

        _QuantizationSearchParams = QuantizationSearchParams
        _SearchParams = SearchParams
    return _SearchParams(
        quantization=_QuantizationSearchParams(
            rescore=True,
            oversampling=settings.qdrant_quantization_oversampling,
        )
    )


def _dense_search(
    client_manager: QdrantClientManager,
    collection_name: str,
    query_vector: list[float],
    limit: int,
    use_quantization_params: bool = False,
) -> tuple[list[SearchResult], float]:
    """Run a dense-only search and return hits plus wall-clock latency in ms."""
    client = client_manager.client
    search_params = _quantization_search_params() if use_quantization_params else None
    start = time.perf_counter()
    try:
        response = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            using="dense",
            limit=limit,
            with_payload=True,
            search_params=search_params,
        )
        hits = _parse_hits(response.points)
    except Exception as exc:
        logger.warning(f"Dense search failed on '{collection_name}': {exc}")
        hits = []
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return hits, elapsed_ms


def _format_table_row(
    label: str,
    recall_10: float,
    recall_50: float,
    median_ms: float,
    p95_ms: float,
) -> str:
    return (
        f"| {label:<25} | "
        f"{recall_10:>7.3f} | "
        f"{recall_50:>7.3f} | "
        f"{median_ms:>8.1f} | "
        f"{p95_ms:>8.1f} |"
    )


async def _embed_queries(
    embedder: EmbeddingService,
    queries: list[str],
) -> list[list[float]]:
    """Batch-encode queries and return dense vectors only."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: embedder.encode_batch(queries)["dense"])


def _collection_exists(client_manager: QdrantClientManager, name: str) -> bool:
    """Check whether a Qdrant collection exists."""
    try:
        collections = client_manager.client.get_collections().collections
        return any(c.name == name for c in collections)
    except Exception as exc:
        logger.warning(f"Could not list collections: {exc}")
        return False


def _qdrant_is_reachable(client_manager: QdrantClientManager) -> bool:
    """Return True if Qdrant is reachable at the configured URL."""
    try:
        client_manager.client.get_collections()
        return True
    except Exception as exc:
        logger.error(f"Qdrant is not reachable at {settings.qdrant_url}: {exc}")
        return False


async def run_benchmark(
    queries: list[str],
    pilot_collection: str,
    top_k: int,
    output_path: str,
) -> dict[str, Any]:
    """Run the full benchmark and return aggregated results."""
    baseline_manager = QdrantClientManager(BASELINE_COLLECTION)

    if not _qdrant_is_reachable(baseline_manager):
        raise RuntimeError(f"Cannot reach Qdrant at {settings.qdrant_url}")

    pilot_exists = _collection_exists(baseline_manager, pilot_collection)
    if not pilot_exists:
        logger.warning(
            f"Pilot collection '{pilot_collection}' does not exist yet. "
            "Candidate recall/latency metrics will be unavailable."
        )

    logger.info("Loading embedding model (this may take a minute on CPU)...")
    embedder = EmbeddingService()
    embedder._ensure_encoder()

    logger.info(f"Embedding {len(queries)} queries...")
    query_vectors = await _embed_queries(embedder, queries)

    outcomes: list[QueryOutcome] = []
    baseline_latencies: list[float] = []
    candidate_latencies: list[float] = []

    use_quant_params_for_pilot = pilot_exists and _is_quantized_collection(
        baseline_manager, pilot_collection
    )
    if use_quant_params_for_pilot:
        logger.info(
            f"Pilot collection '{pilot_collection}' is quantized; applying "
            f"rescore=True, oversampling={settings.qdrant_quantization_oversampling} search params."
        )

    for query, vector in zip(queries, query_vectors):
        baseline_hits, baseline_ms = _dense_search(
            baseline_manager, BASELINE_COLLECTION, vector, top_k
        )
        baseline_latencies.append(baseline_ms)

        candidate_hits: list[SearchResult] = []
        candidate_ms = 0.0
        if pilot_exists:
            candidate_hits, candidate_ms = _dense_search(
                baseline_manager, pilot_collection, vector, top_k, use_quant_params_for_pilot
            )
            candidate_latencies.append(candidate_ms)

        outcomes.append(
            QueryOutcome(
                query=query,
                baseline_results=baseline_hits,
                candidate_results=candidate_hits,
                baseline_ms=baseline_ms,
                candidate_ms=candidate_ms,
            )
        )

    candidate_recalls_10 = [o.recall_at_10 for o in outcomes]
    candidate_recalls_50 = [o.recall_at_50 for o in outcomes]

    aggregated = {
        "baseline": {
            "recall_at_10_mean": 1.0,
            "recall_at_50_mean": 1.0,
            "median_ms": statistics.median(baseline_latencies) if baseline_latencies else 0.0,
            "p95_ms": _percentile(baseline_latencies, 95.0),
            "collection": BASELINE_COLLECTION,
            "query_count": len(queries),
            "top_k": top_k,
        },
        "candidate": {
            "recall_at_10_mean": statistics.mean(candidate_recalls_10)
            if candidate_recalls_10
            else 0.0,
            "recall_at_50_mean": statistics.mean(candidate_recalls_50)
            if candidate_recalls_50
            else 0.0,
            "median_ms": statistics.median(candidate_latencies) if candidate_latencies else 0.0,
            "p95_ms": _percentile(candidate_latencies, 95.0),
            "collection": pilot_collection,
            "exists": pilot_exists,
            "query_count": len(queries),
            "top_k": top_k,
        },
        "per_query": [
            {
                "query": o.query,
                "baseline_ms": o.baseline_ms,
                "candidate_ms": o.candidate_ms,
                "recall_at_10": o.recall_at_10,
                "recall_at_50": o.recall_at_50,
            }
            for o in outcomes
        ],
        "settings": {
            "qdrant_url": settings.qdrant_url,
            "embedding_model": settings.embedding_model,
            "embedding_backend": settings.embedding_backend,
            "embedding_dimension": settings.embedding_dimension,
        },
    }

    _print_report(aggregated)
    _write_json(output_path, aggregated)
    baseline_manager.close()

    return aggregated


def _print_report(results: dict[str, Any]) -> None:
    """Print markdown table and go/no-go verdict to stdout."""
    baseline = results["baseline"]
    candidate = results["candidate"]

    print("\n### Quantization Pilot Benchmark Results\n")
    print("| Setting                   | Recall@10 | Recall@50 | Median ms | P95 ms   |")
    print("|---------------------------|-----------|-----------|-----------|----------|")
    print(
        _format_table_row(
            "baseline (INT8)",
            baseline["recall_at_10_mean"],
            baseline["recall_at_50_mean"],
            baseline["median_ms"],
            baseline["p95_ms"],
        )
    )

    if candidate["exists"]:
        print(
            _format_table_row(
                f"candidate ({candidate['collection']})",
                candidate["recall_at_10_mean"],
                candidate["recall_at_50_mean"],
                candidate["median_ms"],
                candidate["p95_ms"],
            )
        )
    else:
        print(f"| candidate ({candidate['collection']}) | N/A (collection absent) |")

    if candidate["exists"]:
        r10_ok = candidate["recall_at_10_mean"] >= RECALL_AT_10_THRESHOLD
        r50_ok = candidate["recall_at_50_mean"] >= RECALL_AT_50_THRESHOLD
        latency_ok = candidate["p95_ms"] <= baseline["p95_ms"]

        verdict = "GO" if (r10_ok and r50_ok and latency_ok) else "NO-GO"
        print(f"\nVerdict: **{verdict}**")
        print(
            f"- recall@10 ≥ {RECALL_AT_10_THRESHOLD}: "
            f"{'✅' if r10_ok else '❌'} {candidate['recall_at_10_mean']:.3f}"
        )
        print(
            f"- recall@50 ≥ {RECALL_AT_50_THRESHOLD}: "
            f"{'✅' if r50_ok else '❌'} {candidate['recall_at_50_mean']:.3f}"
        )
        print(
            f"- p95 latency ≤ baseline p95: "
            f"{'✅' if latency_ok else '❌'} "
            f"candidate={candidate['p95_ms']:.1f}ms vs baseline={baseline['p95_ms']:.1f}ms"
        )
    else:
        print(
            "\nVerdict: **PENDING** — pilot collection does not exist yet. "
            "Run Task 4 to create and populate it."
        )


def _write_json(path: str, data: dict[str, Any]) -> None:
    """Persist results as indented JSON."""
    out = Path(path)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Results written to {out.resolve()}")


def _build_argument_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Benchmark Qdrant quantization pilots against the spiritual_wisdom baseline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=len(FALLBACK_QUERIES),
        help="Maximum number of queries to benchmark.",
    )
    parser.add_argument(
        "--pilot-collection",
        type=str,
        default=DEFAULT_PILOT_COLLECTION,
        help="Name of the candidate quantized collection.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Number of results to retrieve per query.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        help="Path to write the JSON results file.",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=settings.qdrant_url,
        help="Override the Qdrant URL from settings.",
    )
    parser.add_argument(
        "--baseline-collection",
        type=str,
        default=BASELINE_COLLECTION,
        help="Override the baseline collection name.",
    )
    return parser


def _self_check() -> None:
    """Validate that imports and the CLI parser work without running a full benchmark."""
    parser = _build_argument_parser()
    # Parsing --help would call sys.exit; in self-check mode we only verify the
    # parser object is well-formed by inspecting its actions.
    action_names = {a.dest for a in parser._actions}
    required = {
        "queries",
        "pilot_collection",
        "top_k",
        "output",
        "qdrant_url",
        "baseline_collection",
    }
    assert required <= action_names, f"Missing CLI arguments: {required - action_names}"


async def main() -> int:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = _build_argument_parser()
    args = parser.parse_args()

    queries = _build_query_set(args.queries)
    if not queries:
        logger.error("No queries available; aborting.")
        return 1

    logger.info(
        f"Benchmarking baseline='{args.baseline_collection}' "
        f"pilot='{args.pilot_collection}' with {len(queries)} queries, k={args.top_k}"
    )

    await run_benchmark(
        queries=queries,
        pilot_collection=args.pilot_collection,
        top_k=args.top_k,
        output_path=args.output,
    )
    return 0


if __name__ == "__main__":
    # When invoked for self-check only, ensure imports parse.
    if {"--self-check", "--self_check"} & set(sys.argv):
        _self_check()
        print("Self-check passed: imports and CLI parser are valid.")
        sys.exit(0)

    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:
        logger.exception(f"Benchmark failed: {exc}")
        sys.exit(1)
