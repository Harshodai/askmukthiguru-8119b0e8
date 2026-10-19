"""Shadow collection experiment — compare an embedding model change offline.

Scope, honestly stated
-----------------------
This clones a sample of the live collection into a shadow collection re-embedded
with a candidate model, then runs the same golden-query NDCG evaluation
(tests/test_qdrant_search_quality.py) against both, side by side.

What this does NOT do: route live production traffic, run a multi-day A/B
split, or auto-cutover. Building that needs request-routing infra that does
not exist in the pipeline yet (PipelineCoordinator has no shadow-traffic
concept). Faking that here would be dishonest — this script answers "would
the new model score better on our golden queries," which is the part
verifiable offline before committing to a live re-index.

Usage:
    python3 -m scripts.ops.shadow_collection_experiment \\
        --source-collection spiritual_wisdom_contextual \\
        --candidate-model intfloat/multilingual-e5-large \\
        --sample-size 500
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

logger = logging.getLogger(__name__)


def clone_sample_to_shadow(
    client,
    source_collection: str,
    shadow_collection: str,
    sample_size: int,
    embedder,
) -> int:
    """Scroll a sample of points from source, re-embed dense vectors with the
    candidate embedder, upsert into a fresh shadow collection.

    Returns the number of points written.
    """
    from qdrant_client.http.models import Distance, PointStruct, VectorParams

    points, _ = client.scroll(
        collection_name=source_collection,
        limit=sample_size,
        with_payload=True,
        with_vectors=False,
    )
    if not points:
        logger.warning(f"No points found in {source_collection} to sample")
        return 0

    texts = [p.payload.get("text", "") for p in points]
    logger.info(f"Re-embedding {len(texts)} sampled chunks with candidate model...")
    new_vectors = embedder.encode_batch(texts)["dense"]

    dim = len(new_vectors[0])
    if not client.collection_exists(shadow_collection):
        client.create_collection(
            collection_name=shadow_collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

    new_points = [
        PointStruct(id=i, vector=list(new_vectors[i]), payload=points[i].payload)
        for i in range(len(points))
    ]
    batch_size = 200
    for i in range(0, len(new_points), batch_size):
        client.upsert(collection_name=shadow_collection, points=new_points[i : i + batch_size])

    logger.info(f"Shadow collection '{shadow_collection}' populated with {len(new_points)} points")
    return len(new_points)


def compare_collections(
    client,
    baseline_collection: str,
    shadow_collection: str,
    embedder,
) -> dict[str, Any]:
    """Run the golden-query NDCG eval against both collections, dense-only
    (shadow collection has no sparse vectors in this offline sample flow).
    """
    from services.qdrant.searcher import QdrantSearcher
    from tests.test_qdrant_search_quality import QdrantSearchQualityTester

    baseline_searcher = QdrantSearcher(client, baseline_collection)
    shadow_searcher = QdrantSearcher(client, shadow_collection)

    baseline_result = QdrantSearchQualityTester(baseline_searcher, embedder).evaluate_strategy(
        "dense"
    )
    shadow_result = QdrantSearchQualityTester(shadow_searcher, embedder).evaluate_strategy("dense")

    return {
        "baseline": {
            "collection": baseline_collection,
            "mean_ndcg": baseline_result["mean_ndcg"],
            "min_ndcg": baseline_result["min_ndcg"],
        },
        "shadow": {
            "collection": shadow_collection,
            "mean_ndcg": shadow_result["mean_ndcg"],
            "min_ndcg": shadow_result["min_ndcg"],
        },
        "shadow_wins": shadow_result["mean_ndcg"] > baseline_result["mean_ndcg"],
        "timestamp": datetime.now(UTC).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source-collection", default="spiritual_wisdom_contextual")
    parser.add_argument(
        "--shadow-collection", default=None, help="Default: {source}_shadow_{timestamp}"
    )
    parser.add_argument(
        "--candidate-model", required=True, help="e.g. intfloat/multilingual-e5-large"
    )
    parser.add_argument("--sample-size", type=int, default=500)
    args = parser.parse_args(argv)

    from app.config import settings
    from services.embedding_service import EmbeddingService
    from services.qdrant.client import QdrantClientManager

    shadow_collection = args.shadow_collection or (
        f"{args.source_collection}_shadow_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    )

    client_mgr = QdrantClientManager(collection=args.source_collection)
    client = client_mgr.client

    logger.info(f"Loading candidate embedder: {args.candidate_model}")
    # EmbeddingService reads the model to load from settings.embedding_model at
    # encode time (services/embedding_service.py:410) — there is no per-instance
    # constructor override, so the settings singleton must be set first.
    settings.embedding_model = args.candidate_model
    candidate_embedder = EmbeddingService()

    written = clone_sample_to_shadow(
        client, args.source_collection, shadow_collection, args.sample_size, candidate_embedder
    )
    if written == 0:
        logger.error("No points written to shadow collection — aborting comparison")
        return 1

    result = compare_collections(
        client, args.source_collection, shadow_collection, candidate_embedder
    )

    print("\n=== Shadow Collection Experiment ===")
    print(
        f"Baseline ({result['baseline']['collection']}): mean_ndcg={result['baseline']['mean_ndcg']:.3f}"
    )
    print(
        f"Shadow   ({result['shadow']['collection']}): mean_ndcg={result['shadow']['mean_ndcg']:.3f}"
    )
    print(f"Shadow wins: {result['shadow_wins']}")
    print(
        "\nNOTE: this is an offline sample comparison, not a live A/B test. "
        "A model switch still requires a full re-index before cutover — see "
        "app/config.py's embedding_backend comment for the re-index requirement."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
