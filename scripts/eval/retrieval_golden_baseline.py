"""Measure retrieval quality against a golden set drawn from the live index.

B16 left the nDCG gate vacuously 0.0 because no golden corpus existed: the
matrix runner (`retrieval_evaluation_matrix.py`) can only score labels someone
supplies. This builds those labels.

Method (standard synthetic-IR, BEIR "generated queries" style): sample chunks
from the production collection, ask the fast model for a question that ONLY
that chunk answers, then run the question through the production embedding +
Qdrant search path and record the rank of the originating chunk. Reports
Recall@{1,5,10}, MRR@10 and nDCG@10.

The labels are synthetic, so treat the absolute numbers as a regression
baseline, not ground truth about human questions. A drop between runs on the
same corpus is still a real signal.

Usage (from backend/, with the stack up):
    .venv/bin/python ../scripts/eval/retrieval_golden_baseline.py --n 40
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.config import settings  # noqa: E402

QUESTION_PROMPT = (
    "Read this excerpt from a spiritual teaching. Write ONE specific question "
    "that this excerpt answers and that a seeker might actually ask. Use the "
    "excerpt's own distinctive vocabulary. Reply with the question only, no "
    "preamble, no quotes.\n\nExcerpt:\n{text}"
)


def _sample_chunks(client, collection: str, n: int, seed: int) -> list[dict]:
    """Scroll the collection and take a deterministic sample of usable chunks."""
    points, _ = client.scroll(
        collection_name=collection, limit=4000, with_payload=True, with_vectors=False
    )
    usable = []
    for p in points:
        payload = p.payload or {}
        text = payload.get("text") or payload.get("content") or payload.get("page_content") or ""
        # Search flattens payloads and drops the point id, exposing it as
        # `chunk_id` (searcher.py: `payload.get("chunk_id") or hit.id`). Mirror
        # that fallback here so stored points and hits share one identifier.
        chunk_id = payload.get("chunk_id") or p.id
        if len(text.strip()) >= 400 and chunk_id:
            usable.append(
                {
                    "id": str(chunk_id),
                    "text": text.strip(),
                    "source_url": payload.get("source_url") or "",
                }
            )
    if not usable:
        raise SystemExit(f"no chunk in {collection} carries >=400 chars of text")
    random.Random(seed).shuffle(usable)
    return usable[:n]


def _ndcg_at_k(rank: int | None, k: int) -> float:
    """Single relevant document, binary relevance: DCG is 1/log2(rank+1), IDCG is 1."""
    if rank is None or rank > k:
        return 0.0
    return 1.0 / math.log2(rank + 1)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20260912)
    ap.add_argument("--collection", default=settings.qdrant_collection)
    ap.add_argument("--out", default="retrieval_golden_baseline.json")
    ap.add_argument(
        "--questions",
        help=(
            "Path to a cached question set. Written if absent, reused if present. "
            "Variants MUST share one set — regenerating questions per run makes "
            "any A/B comparison a comparison of two different benchmarks."
        ),
    )
    ap.add_argument(
        "--dense-only",
        action="store_true",
        help="Disable the sparse lane, to measure the dense contribution alone.",
    )
    args = ap.parse_args()

    from services.embedding_service import EmbeddingService
    from services.llm_factory import LLMServiceFactory
    from services.qdrant_service import QdrantService

    qdrant = QdrantService()
    embedder = EmbeddingService()
    llm = LLMServiceFactory.create(settings.llm_provider)

    cache = Path(args.questions) if args.questions else None
    if cache and cache.exists():
        chunks = json.loads(cache.read_text())
        print(f"reusing {len(chunks)} cached questions from {cache}", flush=True)
    else:
        chunks = _sample_chunks(qdrant._client, args.collection, args.n, args.seed)
        print(f"sampled {len(chunks)} chunks from {args.collection}", flush=True)
        for chunk in chunks:
            q = (
                await llm._generate_fast(
                    "You write precise retrieval evaluation questions.",
                    QUESTION_PROMPT.format(text=chunk["text"][:1800]),
                )
            ).strip()
            chunk["question"] = q.strip('"').split("\n")[0][:300]
        chunks = [c for c in chunks if c.get("question")]
        if cache:
            cache.write_text(json.dumps(chunks, indent=2))
            print(f"cached {len(chunks)} questions to {cache}", flush=True)

    rows = []
    for i, chunk in enumerate(chunks, 1):
        question = chunk["question"]
        if not question:
            continue
        # Mirror production: retrieve_for_single_query passes BOTH the dense
        # vector and the sparse (lexical) one, and the collection carries a
        # sparse index. Measuring dense-only understates real recall.
        enc = embedder.encode_batch([question])
        vec = enc["dense"][0]
        sparse = (enc.get("sparse") or [None])[0] if not args.dense_only else None
        hits = qdrant.search(vec, limit=args.k, sparse_vector=sparse)
        ids = [str(h.get("chunk_id")) for h in hits]
        rank = ids.index(chunk["id"]) + 1 if chunk["id"] in ids else None
        # Lenient credit: the corpus holds near-duplicate chunks from the same
        # talk, so returning a sibling of the source chunk is not a miss in the
        # way returning an unrelated teaching is.
        srcs = [str(h.get("source_url") or "") for h in hits]
        same_source = bool(chunk["source_url"]) and chunk["source_url"] in srcs
        rows.append(
            {
                "chunk_id": chunk["id"],
                "question": question,
                "rank": rank,
                "same_source_in_topk": same_source,
                "returned": len(ids),
            }
        )
        print(f"[{i}/{len(chunks)}] rank={rank} {question[:70]}", flush=True)

    ranks = [r["rank"] for r in rows]
    found = [r for r in ranks if r is not None]
    n = len(rows)
    report = {
        "collection": args.collection,
        "mode": "dense_only" if args.dense_only else "hybrid_dense_sparse",
        "questions": n,
        "k": args.k,
        "recall_at_1": round(sum(1 for r in found if r <= 1) / n, 4) if n else None,
        "recall_at_5": round(sum(1 for r in found if r <= 5) / n, 4) if n else None,
        f"recall_at_{args.k}": round(len(found) / n, 4) if n else None,
        "mrr_at_k": round(sum(1.0 / r for r in found) / n, 4) if n else None,
        "ndcg_at_k": round(sum(_ndcg_at_k(r, args.k) for r in ranks) / n, 4) if n else None,
        "median_rank_when_found": statistics.median(found) if found else None,
        "lenient_recall_at_k_same_source": (
            round(sum(1 for r in rows if r["same_source_in_topk"]) / n, 4) if n else None
        ),
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
