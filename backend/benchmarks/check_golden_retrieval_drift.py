"""Read-only drift check for the source-level golden retrieval labels.

The golden set's ``correct_chunks`` is a count of matching chunks, not a
Qdrant point id.  Re-running this tool after a corpus re-ingestion establishes
whether each labelled source still exists, still covers all ``must_mention``
terms across its chunks, and has the expected matching-chunk count.

It never writes to Qdrant, Redis, or the golden dataset.  Use ``--fail-on-
drift`` in a staging release gate only after the collection and label policy
have been explicitly approved.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def normalize_terms(terms: list[str]) -> list[str]:
    """Normalize terms exactly as the golden-set builder does."""
    normalized: list[str] = []
    for term in terms:
        cleaned = re.sub(r"[^a-z0-9\u0900-\u0DFF\s'-]", "", term.lower().strip())
        if cleaned:
            normalized.append(cleaned)
    return normalized


def evaluate_item(item: dict[str, Any], chunks_by_source: dict[str, list[str]]) -> dict[str, Any]:
    """Return source presence, term coverage, and matching-count drift for one label."""
    terms = set(normalize_terms(list(item.get("must_mention") or [])))
    sources = list(item.get("correct_sources") or [])
    missing_sources = [source for source in sources if source not in chunks_by_source]
    sources_missing_terms: dict[str, list[str]] = {}
    matching_chunks = 0

    for source in sources:
        chunks = chunks_by_source.get(source, [])
        covered: set[str] = set()
        contributors = 0
        for text in chunks:
            text_lower = text.lower()
            chunk_terms = {term for term in terms if term in text_lower}
            if chunk_terms:
                contributors += 1
                covered.update(chunk_terms)
        if chunks and covered != terms:
            sources_missing_terms[source] = sorted(terms - covered)
        elif chunks:
            matching_chunks += contributors

    expected_chunks = item.get("correct_chunks")
    count_drift = isinstance(expected_chunks, int) and expected_chunks != matching_chunks
    return {
        "id": item.get("id"),
        "missing_sources": missing_sources,
        "sources_missing_terms": sources_missing_terms,
        "expected_correct_chunks": expected_chunks,
        "actual_correct_chunks": matching_chunks,
        "correct_chunks_drifted": count_drift,
        "drifted": bool(missing_sources or sources_missing_terms or count_drift),
    }


def validate_golden(golden: dict[str, Any]) -> list[str]:
    """Validate the small schema needed for a meaningful drift report."""
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(golden.get("items") or []):
        if not isinstance(item, dict):
            errors.append(f"items[{index}]: item must be an object")
            continue
        label = item.get("id") or f"items[{index}]"
        if not item.get("id") or item["id"] in seen:
            errors.append(f"{label}: id must be present and unique")
        seen.add(item.get("id", ""))
        if not item.get("correct_sources"):
            errors.append(f"{label}: correct_sources must not be empty")
        if not item.get("must_mention"):
            errors.append(f"{label}: must_mention must not be empty")
        if not isinstance(item.get("correct_chunks"), int) or item["correct_chunks"] < 1:
            errors.append(f"{label}: correct_chunks must be a positive count")
    return errors


def _scroll_chunks(client: Any, collection: str) -> dict[str, list[str]]:
    chunks_by_source: dict[str, list[str]] = defaultdict(list)
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            limit=1_000,
            offset=offset,
            with_payload=["source_url", "text"],
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            source = payload.get("source_url")
            text = payload.get("text")
            if isinstance(source, str) and source and isinstance(text, str) and text:
                chunks_by_source[source].append(text.lower())
        if next_offset is None:
            return dict(chunks_by_source)
        offset = next_offset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", required=True, type=Path)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--api-key")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-items", type=int, default=0, help="0 checks every item")
    parser.add_argument("--fail-on-drift", action="store_true")
    args = parser.parse_args(argv)

    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    errors = validate_golden(golden)
    if errors:
        parser.error("invalid golden dataset: " + "; ".join(errors))

    from qdrant_client import QdrantClient

    chunks_by_source = _scroll_chunks(
        QdrantClient(url=args.url, api_key=args.api_key, timeout=120), args.collection
    )
    items = golden["items"][: args.max_items or None]
    checks = [evaluate_item(item, chunks_by_source) for item in items]
    drifted = [check for check in checks if check["drifted"]]
    report = {
        "golden_version": golden.get("version"),
        "collection": args.collection,
        "n_items_checked": len(checks),
        "n_sources_scanned": len(chunks_by_source),
        "n_drifted": len(drifted),
        "checks": checks,
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"checked={len(checks)} drifted={len(drifted)} report={args.out}")
    return 1 if args.fail_on_drift and drifted else 0


if __name__ == "__main__":
    raise SystemExit(main())
