"""Build the Phase 1 golden retrieval set for recall@k gating.

Labels correct source documents for benchmark queries by term-match:
a chunk is a correct source if its text contains ALL of the query's
`must_mention` terms (case-insensitive). Terms come from the verified
question bank (`question_bank.py`, `verified: true` items), so the labels
derive from confirmed teaching facts, not from retrieval quality.

Labeling is done over a FULL scroll of the collection (not over retrieved
top-k), so the golden labels are independent of retrieval behaviour.

Output JSON (one item per query):
    {
      "id", "query", "category", "must_mention",
      "correct_sources": [source_url, ...],   # distinct source_urls of matching chunks
      "correct_chunks": n,                    # number of matching chunks
    }

Usage:
    docker cp backend/benchmarks/build_golden_retrieval_set.py <ctr>:/app/benchmarks/
    docker exec <ctr> python /app/benchmarks/build_golden_retrieval_set.py \
        --collection spiritual_wisdom --out /tmp/golden_retrieval_v1.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client import QdrantClient  # noqa: E402


def _load_question_bank(path: str) -> list[dict]:
    """Load verified queries with must_mention terms from question_bank.py."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("question_bank", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    items: list[dict] = []
    for category, queries in module.QUERIES.items():
        for q in queries:
            if not q.get("verified"):
                continue
            terms = q.get("must_mention") or []
            if not terms:
                continue
            items.append(
                {
                    "query": q["q"],
                    "category": category,
                    "must_mention": terms,
                    "source": q.get("source", category),
                }
            )
    return items


def _scroll_all(client: QdrantClient, collection: str, page_size: int = 1000) -> list[dict]:
    """Full scroll of the collection: list of {text, source_url} payloads."""
    chunks: list[dict] = []
    offset = None
    while True:
        page, next_offset = client.scroll(
            collection_name=collection,
            limit=page_size,
            offset=offset,
            with_payload=["text", "source_url"],
            with_vectors=False,
        )
        for point in page:
            payload = point.payload or {}
            text = payload.get("text", "")
            source_url = payload.get("source_url", "")
            if text and source_url:
                chunks.append({"text": text.lower(), "source_url": source_url})
        if next_offset is None:
            break
        offset = next_offset
        if len(chunks) % 20000 == 0:
            print(f"  scrolled {len(chunks)} chunks...", flush=True)
    return chunks


def _normalize_terms(terms: list[str]) -> list[str]:
    """Lowercase and strip punctuation from terms."""
    cleaned = []
    for t in terms:
        t = t.lower().strip()
        t = re.sub(r"[^a-z0-9\u0900-\u0DFF\s'-]", "", t)
        if t:
            cleaned.append(t)
    return cleaned


def _label(
    chunks: list[dict], terms: list[str], source_level: bool = False
) -> tuple[set[str], int]:
    """Return (distinct source_urls, matching chunk count).

    Chunk-level (default): a chunk must contain ALL terms; its source_url
    is correct. Source-level: a source is correct if its chunks *collectively*
    cover all terms (union of per-chunk term coverage) — captures multi-hop
    queries whose answer facts span multiple chunks of one source.
    """
    sources: set[str] = set()
    matching = 0
    if not source_level:
        for chunk in chunks:
            text = chunk["text"]
            if all(term in text for term in terms):
                sources.add(chunk["source_url"])
                matching += 1
        return sources, matching

    per_source_terms: dict[str, set[str]] = {}
    per_source_chunks: Counter = Counter()
    for chunk in chunks:
        text = chunk["text"]
        covered = {t for t in terms if t in text}
        if covered:
            per_source_terms.setdefault(chunk["source_url"], set()).update(covered)
            per_source_chunks[chunk["source_url"]] += 1
    term_set = set(terms)
    for source_url, covered in per_source_terms.items():
        if covered >= term_set:
            sources.add(source_url)
            matching += per_source_chunks[source_url]
    return sources, matching


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--collection", default="spiritual_wisdom")
    p.add_argument("--url", default="http://localhost:6333")
    p.add_argument("--question-bank", default="/app/benchmarks/question_bank.py")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument(
        "--min-chunks", type=int, default=1, help="Queries with fewer matching chunks are dropped."
    )
    p.add_argument(
        "--source-level",
        action="store_true",
        help="Label sources whose chunks collectively cover all terms (multi-hop).",
    )
    args = p.parse_args(argv)

    client = QdrantClient(url=args.url, timeout=120)

    print("Loading question bank...")
    items = _load_question_bank(args.question_bank)
    print(f"  {len(items)} verified queries with must_mention terms")

    print(f"Scrolling {args.collection}...")
    chunks = _scroll_all(client, args.collection)
    print(f"  {len(chunks)} text chunks with source_url")

    print("Labeling correct sources by all-terms match...")
    labeled = []
    dropped = []
    for i, item in enumerate(items):
        terms = _normalize_terms(item["must_mention"])
        if not terms:
            dropped.append({"id": f"q{i:03d}", **item, "reason": "no usable terms"})
            continue
        sources, n_chunks = _label(chunks, terms, source_level=args.source_level)
        if n_chunks < args.min_chunks:
            dropped.append(
                {**item, "reason": f"only {n_chunks} chunks matched", "n_matched": n_chunks}
            )
            continue
        labeled.append(
            {
                "id": f"{item['category']}-{i:03d}",
                "query": item["query"],
                "category": item["category"],
                "must_mention": item["must_mention"],
                "correct_sources": sorted(sources),
                "correct_chunks": n_chunks,
            }
        )
        if (i + 1) % 25 == 0:
            print(f"  labeled {i + 1}/{len(items)}")

    by_cat = Counter(it["category"] for it in labeled)
    print(f"\nLabeled {len(labeled)} queries; dropped {len(dropped)}:")
    print(f"  by category: {dict(by_cat)}")

    out = {
        "version": "v1",
        "collection": args.collection,
        "generated": "2026-08-01",
        "labeling": (
            "source-level all-terms coverage over full corpus scroll (verified question bank)"
            if args.source_level
            else "all-must_mention-terms match over full corpus scroll (verified question bank)"
        ),
        "items": labeled,
    }
    args.out.write_text(json.dumps(out, indent=2))
    print(f"Wrote {args.out}")

    if len(labeled) < 50:
        print(f"WARNING: only {len(labeled)} labeled queries (target 50-200)")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
