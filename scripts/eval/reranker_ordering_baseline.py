"""Measure whether the reranker or the retriever decides the answer (F11).

Audit finding: recall@24 is 0.917 but recall@1 is 0.2326 -- the gold document
is almost always IN the candidate set and almost never FIRST after the
pipeline retrieves 24 (RAG_TOP_K_RETRIEVAL) and reranks to 5
(RAG_TOP_K_RERANK). This measures the reranker's OWN contribution in
isolation: for each golden question, record the gold chunk's rank among the
24 retrieved candidates BEFORE reranking and AFTER reranking, so a config
change can be judged against the actual bottleneck instead of guessed at.

Read-only. Reuses the exact question cache retrieval_golden_baseline.py
writes/reads (--questions), per that script's own rule: variants MUST share
one question set, or an A/B comparison is comparing two different benchmarks.

Usage (from backend/, with the stack up, after retrieval_golden_baseline.py
has already produced a --questions cache):
    .venv/bin/python ../scripts/eval/reranker_ordering_baseline.py \
        --questions retrieval_golden_baseline_questions.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--questions",
        required=True,
        help="Cached question set from retrieval_golden_baseline.py (MUST already exist).",
    )
    ap.add_argument("--k", type=int, default=24, help="Candidate pool size (RAG_TOP_K_RETRIEVAL).")
    ap.add_argument("--out", default="reranker_ordering_baseline.json")
    args = ap.parse_args()

    cache = Path(args.questions)
    if not cache.exists():
        raise SystemExit(
            f"{cache} does not exist -- run retrieval_golden_baseline.py with "
            "--questions first to produce a shared question set."
        )
    chunks = json.loads(cache.read_text())
    print(f"loaded {len(chunks)} cached questions from {cache}", flush=True)

    from services.embedding_service import EmbeddingService
    from services.qdrant_service import QdrantService
    from services.reranker_service import RerankerService

    qdrant = QdrantService()
    embedder = EmbeddingService()
    reranker = RerankerService()

    rows = []
    for i, chunk in enumerate(chunks, 1):
        question = chunk.get("question")
        gold_id = chunk["id"]
        if not question:
            continue

        enc = embedder.encode_batch([question])
        vec = enc["dense"][0]
        sparse = (enc.get("sparse") or [None])[0]
        candidates = qdrant.search(vec, limit=args.k, sparse_vector=sparse)

        pre_ids = [str(d.get("chunk_id")) for d in candidates]
        pre_rank = pre_ids.index(gold_id) + 1 if gold_id in pre_ids else None

        if not candidates:
            rows.append({"chunk_id": gold_id, "pre_rank": None, "post_rank": None, "candidates": 0})
            continue

        reranked = await reranker.rerank(question, candidates)
        post_ids = [str(d.get("chunk_id")) for d in reranked]
        post_rank = post_ids.index(gold_id) + 1 if gold_id in post_ids else None

        rows.append(
            {
                "chunk_id": gold_id,
                "question": question,
                "pre_rank": pre_rank,
                "post_rank": post_rank,
                "candidates": len(candidates),
            }
        )
        print(
            f"[{i}/{len(chunks)}] pre_rank={pre_rank} post_rank={post_rank} {question[:60]}",
            flush=True,
        )

    def _at1(key: str) -> float | None:
        found = [r for r in rows if r.get(key) is not None]
        n = len(rows)
        return round(sum(1 for r in found if r[key] == 1) / n, 4) if n else None

    def _median(key: str) -> float | None:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return statistics.median(vals) if vals else None

    # The signal that matters: did reranking move the gold doc closer to rank
    # 1, farther away, or leave it unchanged? If pre_rank is already good and
    # post_rank is worse, the reranker is actively hurting, not just failing
    # to help -- a different fix than "the reranker isn't strong enough."
    moved_up = sum(
        1
        for r in rows
        if r.get("pre_rank") is not None
        and r.get("post_rank") is not None
        and r["post_rank"] < r["pre_rank"]
    )
    moved_down = sum(
        1
        for r in rows
        if r.get("pre_rank") is not None
        and r.get("post_rank") is not None
        and r["post_rank"] > r["pre_rank"]
    )
    unchanged = sum(
        1
        for r in rows
        if r.get("pre_rank") is not None
        and r.get("post_rank") is not None
        and r["post_rank"] == r["pre_rank"]
    )

    report = {
        "questions": len(rows),
        "k": args.k,
        "recall_at_1_pre_rerank": _at1("pre_rank"),
        "recall_at_1_post_rerank": _at1("post_rank"),
        "median_rank_pre_rerank": _median("pre_rank"),
        "median_rank_post_rerank": _median("post_rank"),
        "gold_moved_toward_rank_1": moved_up,
        "gold_moved_away_from_rank_1": moved_down,
        "gold_rank_unchanged": unchanged,
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
