#!/usr/bin/env python3
"""Publish a verified Qdrant retrieval-index compatibility contract.

This is an operator-controlled release step. It performs no write unless
``--apply`` is supplied, and it refuses to replace a different published
contract without ``--replace``. Run it only after a complete ingestion and
vector/graph consistency validation for the intended corpus release.

Examples:
  python scripts/ops/publish_retrieval_index_contract.py --dry-run \\
      --source-manifest /secure/release/source-manifest.json
  python scripts/ops/publish_retrieval_index_contract.py --apply \\
      --source-manifest /secure/release/source-manifest.json --require-graph
  python scripts/ops/publish_retrieval_index_contract.py --apply --replace \\
      --source-manifest /secure/release/source-manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import settings
from app.corpus_publication import (
    CorpusPublicationError,
    CorpusPublicationManifest,
    build_publication_record,
    validate_publication_record,
)
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


def _qdrant_publication_counts(client: Any, collection: str) -> tuple[int, int]:
    """Count all published vectors and distinct source identities, read-only."""
    counted = client.count(collection_name=collection, exact=True)
    points = int(getattr(counted, "count", 0) or 0)
    if points <= 0:
        raise RuntimeError(
            f"Qdrant collection {collection!r} has no points; refusing publication."
        )
    sources: set[str] = set()
    offset = None
    while True:
        page, offset = client.scroll(
            collection_name=collection,
            offset=offset,
            limit=512,
            with_payload=["source_url", "source_id", "source"],
            with_vectors=False,
        )
        for point in page:
            payload = getattr(point, "payload", None) or {}
            source = (
                payload.get("source_url") or payload.get("source_id") or payload.get("source")
            )
            if isinstance(source, str) and source.strip():
                sources.add(source.strip())
        if offset is None:
            break
    if not sources:
        raise RuntimeError(
            f"Qdrant collection {collection!r} has no source identity payloads; refusing publication."
        )
    return points, len(sources)


def _graph_counts(*, corpus_id: str) -> tuple[int, int]:
    """Read graph counts for a declared corpus. Called only with --require-graph."""
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=settings.neo4j_connection_timeout_s,
    )
    try:
        with driver.session() as session:
            nodes = session.run(
                "MATCH (n {corpus_id: $corpus_id}) RETURN count(n) AS count",
                corpus_id=corpus_id,
            ).single()["count"]
            edges = session.run(
                "MATCH (a {corpus_id: $corpus_id})-[r]->(b {corpus_id: $corpus_id}) "
                "RETURN count(r) AS count",
                corpus_id=corpus_id,
            ).single()["count"]
    finally:
        driver.close()
    return int(nodes), int(edges)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Validate and print; never write")
    mode.add_argument("--apply", action="store_true", help="Publish after all validation passes")
    parser.add_argument("--collection", default=settings.qdrant_collection)
    parser.add_argument("--corpus-version", default=None)
    parser.add_argument(
        "--source-manifest",
        type=Path,
        required=True,
        help="Approved source-rights manifest file; only its SHA-256 is stored",
    )
    parser.add_argument(
        "--require-graph",
        action="store_true",
        help="Require non-empty Neo4j nodes and edges for the active corpus before publishing",
    )
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
    if not args.source_manifest.is_file():
        raise RuntimeError(f"source manifest does not exist: {args.source_manifest}")
    points, sources = _qdrant_publication_counts(qdrant.client, args.collection)
    graph_nodes, graph_edges = (None, None)
    if args.require_graph:
        graph_nodes, graph_edges = _graph_counts(corpus_id=settings.default_corpus_id)
    publication = CorpusPublicationManifest(
        manifest_version="v1",
        collection=args.collection,
        corpus_version=expected.corpus_version,
        source_manifest_sha256=_sha256_file(args.source_manifest),
        index_fingerprint=expected.digest,
        qdrant_points=points,
        qdrant_sources=sources,
        graph_required=args.require_graph,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
    )
    record = build_publication_record(expected, publication)

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
            validate_publication_record(current, expected)
            print(json.dumps({"status": "already-published", "fingerprint": expected.digest}))
            return 0
        except (CorpusPublicationError, IndexFingerprintError) as exc:
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
                    "publication": publication.payload(),
                },
                sort_keys=True,
            )
        )
        return 0

    redis_client.set(key, json.dumps(record, sort_keys=True))
    print(json.dumps({"status": "published", "key": key, "fingerprint": expected.digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
