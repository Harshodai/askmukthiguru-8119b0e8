#!/usr/bin/env python3
"""Publish a verified Qdrant retrieval-index compatibility contract.

This is an operator-controlled release step. It performs no write unless
``--apply`` is supplied, and it refuses to replace a different published
contract without ``--replace``. Run it only after a complete ingestion and
vector/graph consistency validation for the intended corpus release.

Examples:
  python scripts/ops/publish_retrieval_index_contract.py --dry-run
  python scripts/ops/publish_retrieval_index_contract.py --apply
  python scripts/ops/publish_retrieval_index_contract.py --apply --replace
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import settings
from app.index_fingerprint import IndexFingerprintError, build_index_fingerprint


def _assert_qdrant_schema(client: Any, collection: str, expected_dimension: int) -> None:
    """Validate the minimum vector schema before publishing its identity."""
    info = client.get_collection(collection)
    vectors = info.config.params.vectors
    dense = vectors.get("dense") if isinstance(vectors, dict) else None
    if dense is None or getattr(dense, "size", None) != expected_dimension:
        actual = getattr(dense, "size", None)
        raise RuntimeError(
            f"Qdrant collection {collection!r} dense dimension is {actual!r}; "
            f"expected {expected_dimension}. Refusing publication."
        )
    sparse = getattr(info.config.params, "sparse_vectors", None)
    if not isinstance(sparse, dict) or "sparse" not in sparse:
        raise RuntimeError(
            f"Qdrant collection {collection!r} lacks the required named sparse vector. "
            "Refusing publication."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Validate and print; never write")
    mode.add_argument("--apply", action="store_true", help="Publish after all validation passes")
    parser.add_argument("--collection", default=settings.qdrant_collection)
    parser.add_argument("--corpus-version", default=None)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Allow replacing an incompatible existing publication after a validated re-index",
    )
    args = parser.parse_args(argv)
    if args.replace and not args.apply:
        parser.error("--replace requires --apply")

    from services.qdrant.client import QdrantClientManager

    qdrant = QdrantClientManager(collection=args.collection)
    expected = build_index_fingerprint(
        settings, collection=args.collection, corpus_version=args.corpus_version
    )
    _assert_qdrant_schema(qdrant.client, args.collection, expected.dense_dimension)

    import redis

    redis_client = redis.Redis.from_url(
        settings.redis_url, socket_timeout=5, socket_connect_timeout=5
    )
    redis_client.ping()
    key = f"retrieval_index_contract:{args.collection}"
    raw = redis_client.get(key)
    current = json.loads(raw) if raw else None

    if current is not None:
        try:
            expected.assert_matches(current)
            print(json.dumps({"status": "already-published", "fingerprint": expected.digest}))
            return 0
        except IndexFingerprintError as exc:
            if not args.replace:
                raise RuntimeError(
                    f"An incompatible contract is already published: {exc}. "
                    "Validate the re-index and rerun with --apply --replace."
                ) from exc

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "validated-not-published",
                    "key": key,
                    "fingerprint": expected.digest,
                    "contract": expected.payload(),
                },
                sort_keys=True,
            )
        )
        return 0

    redis_client.set(key, json.dumps(expected.published_payload(), sort_keys=True))
    print(json.dumps({"status": "published", "key": key, "fingerprint": expected.digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
