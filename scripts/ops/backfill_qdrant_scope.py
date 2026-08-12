#!/usr/bin/env python3
"""Backfill tenant/corpus payload scope for legacy Qdrant teaching points.

Dry-run by default. Use --apply only after inspecting the reported count and
sampling target collection payloads. Existing explicit values are never changed.
"""
from __future__ import annotations

import argparse
import os
from collections.abc import Iterable

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, IsEmptyCondition, PayloadField


def iter_unscoped_points(client: QdrantClient, collection: str) -> Iterable[object]:
    offset = None
    scope_filter = Filter(
        should=[
            IsEmptyCondition(is_empty=PayloadField(key="tenant_id")),
            IsEmptyCondition(is_empty=PayloadField(key="corpus_id")),
        ]
    )
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=scope_filter,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        yield from points
        if offset is None:
            return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist inferred default scope values")
    parser.add_argument("--url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--api-key", default=os.environ.get("QDRANT_API_KEY"))
    parser.add_argument("--collection", default=os.environ.get("QDRANT_COLLECTION", "mukthi_guru_knowledge"))
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--corpus-id", default=os.environ.get("DEFAULT_CORPUS_ID", "askmukthiguru"))
    args = parser.parse_args()

    client = QdrantClient(url=args.url, api_key=args.api_key or None, check_compatibility=False)
    points = list(iter_unscoped_points(client, args.collection))
    print(f"Found {len(points)} unscoped point(s) in {args.collection}.")
    if not args.apply:
        print("Dry run only. Re-run with --apply after validating the defaults.")
        return 0
    for point in points:
        payload = point.payload or {}
        patch = {}
        if not payload.get("tenant_id"):
            patch["tenant_id"] = args.tenant_id
        if not payload.get("corpus_id"):
            patch["corpus_id"] = args.corpus_id
        if patch:
            client.set_payload(collection_name=args.collection, payload=patch, points=[point.id])
    print(f"Applied scope defaults to {len(points)} point(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
