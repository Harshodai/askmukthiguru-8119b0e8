"""Phase 1 recall@k harness — gate every retrieval change on this.

Loads the golden retrieval set (build_golden_retrieval_set.py), embeds each
query with the production EmbeddingService (dense + sparse), and runs the
production hybrid retrieval path (`QdrantSearcher.search` with
raptor_level=0, mirroring `retrieve_for_single_query`'s chunk task).

A query is a hit at k if any of the top-k retrieved chunks has a
source_url in the query's labelled `correct_sources`.

Reports, per run:
  - recall@k for k in [1, 5, 10, 25, 50]
  - mean per-query latency (embed ms, search ms), p50/p95
  - per-query detail (hit/miss + top sources) for inspection

Usage (in backend container, where models + qdrant are reachable):
    docker cp backend/benchmarks/recall_harness.py <ctr>:/app/benchmarks/
    docker cp golden_retrieval_v1.json <ctr>:/tmp/
    docker exec <ctr> python /app/benchmarks/recall_harness.py \
        --golden /tmp/golden_retrieval_v1.json --collection spiritual_wisdom \
        --out /tmp/recall_baseline.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client import QdrantClient  # noqa: E402
from services.embedding_service import EmbeddingService  # noqa: E402
from services.qdrant.searcher import QdrantSearcher  # noqa: E402


def _p(percentile: float, values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(percentile / 100 * len(ordered)))
    return ordered[idx]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--golden", required=True, type=Path)
    p.add_argument("--collection", default="spiritual_wisdom")
    p.add_argument("--url", default="http://localhost:6333")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--top-k", default=50, type=int)
    p.add_argument("--max-queries", type=int, default=0, help="0 = all")
    args = p.parse_args(argv)

    golden = json.loads(args.golden.read_text())
    items = golden["items"]
    if args.max_queries:
        items = items[: args.max_queries]
    print(f"Golden set: {len(items)} queries ({golden['collection']} -> {args.collection})")

    client = QdrantClient(url=args.url, timeout=120)
    searcher = QdrantSearcher(client, args.collection)
    embedder = EmbeddingService()

    embed_ms: list[float] = []
    search_ms: list[float] = []
    detail = []
    hits_at = {k: 0 for k in (1, 5, 10, 25, 50)}

    for i, item in enumerate(items):
        q = item["query"]
        gold_sources = set(item["correct_sources"])

        t0 = time.perf_counter()
        emb = embedder.encode_single_full(q)
        embed_ms.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        results = searcher.search(
            query_vector=emb["dense"],
            limit=args.top_k,
            sparse_vector=emb["sparse"],
            raptor_level=0,
            query=q,
        )
        search_ms.append((time.perf_counter() - t0) * 1000)

        retrieved_sources = [r.get("source_url", "") for r in results[:50]]
        for k in hits_at:
            if any(s in gold_sources for s in retrieved_sources[:k]):
                hits_at[k] += 1

        detail.append(
            {
                "id": item["id"],
                "query": q,
                "hit_at_10": any(s in gold_sources for s in retrieved_sources[:10]),
                "hit_at_50": any(s in gold_sources for s in retrieved_sources[:50]),
                "n_gold_sources": len(gold_sources),
                "top_sources": retrieved_sources[:10],
                "gold_sources": sorted(gold_sources)[:10],
                "embed_ms": round(embed_ms[-1], 1),
                "search_ms": round(search_ms[-1], 1),
            }
        )
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(items)} queries done", flush=True)

    n = len(items)
    recall = {k: round(hits_at[k] / n, 4) if n else 0.0 for k in hits_at}
    report = {
        "collection": args.collection,
        "golden_version": golden.get("version"),
        "n_queries": n,
        "recall_at_k": recall,
        "embed_latency_ms": {
            "mean": round(statistics.mean(embed_ms), 1),
            "p50": round(_p(50, embed_ms), 1),
            "p95": round(_p(95, embed_ms), 1),
        },
        "search_latency_ms": {
            "mean": round(statistics.mean(search_ms), 1),
            "p50": round(_p(50, search_ms), 1),
            "p95": round(_p(95, search_ms), 1),
        },
        "detail": detail,
    }
    args.out.write_text(json.dumps(report, indent=2))
    print(f"\nrecall@k: {recall}")
    print(f"embed  ms p50={report['embed_latency_ms']['p50']} p95={report['embed_latency_ms']['p95']}")
    print(f"search ms p50={report['search_latency_ms']['p50']} p95={report['search_latency_ms']['p95']}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
