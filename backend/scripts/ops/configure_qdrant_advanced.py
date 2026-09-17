#!/usr/bin/env python3
"""
Configure and optimize Qdrant for Advanced Retrieval:
1. INT8 Scalar Quantization with quantile=0.99 and always_ram=True
2. On-disk vector and payload persistence
3. Ensure named vectors (dense 1024d cosine + sparse lexical weights)
4. Ensure all required payload indexes including video_id, source_url, parent_id
5. Test and verify Universal Query API (query_points with Prefetch & RRF/DBSF)
6. Test and verify Parent Document Group Search (query_points_groups)

Usage:
  python -m scripts.ops.configure_qdrant_advanced [--apply] [--url http://localhost:6333] [--collection spiritual_wisdom_contextual]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("configure_qdrant_advanced")

# Essential payload indexes for filtering, full-text search, and parent document grouping
REQUIRED_PAYLOAD_INDEXES: list[tuple[str, str]] = [
    # Grouping keys for Parent Document Group Search
    ("video_id", "keyword"),
    ("source_url", "keyword"),
    ("parent_id", "keyword"),
    ("chunk_id", "keyword"),
    # Core multitenancy and rights governance
    ("tenant_id", "keyword"),
    ("corpus_id", "keyword"),
    ("teacher_id", "keyword"),
    ("teacher_ids", "keyword"),
    ("domain_rights_status", "keyword"),
    # Metadata and taxonomy filtering
    ("raptor_level", "integer"),
    ("source_type", "keyword"),
    ("language", "keyword"),
    ("tags", "keyword"),
    ("speaker", "keyword"),
    ("topic", "keyword"),
    ("content_type", "keyword"),
    ("title", "keyword"),
    ("text", "text"),
    # Graph linking
    ("entity_ids", "keyword"),
    ("graph_node_ids", "keyword"),
    ("context_cluster_ids", "keyword"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure Qdrant advanced quantization, indexes, and test universal queries."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("QDRANT_URL", "http://localhost:6333"),
        help="Qdrant service URL (default: http://localhost:6333)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("QDRANT_API_KEY", ""),
        help="Qdrant API key if required",
    )
    parser.add_argument(
        "--collection",
        default=os.environ.get("QDRANT_COLLECTION", "spiritual_wisdom_contextual"),
        help="Target collection name (default: spiritual_wisdom_contextual)",
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=int(os.environ.get("EMBEDDING_DIMENSION", "1024")),
        help="Dense embedding dimension (default: 1024)",
    )
    parser.add_argument(
        "--quantile",
        type=float,
        default=float(os.environ.get("QDRANT_QUANTIZATION_QUANTILE", "0.99")),
        help="Quantization quantile threshold (default: 0.99)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply modifications. Without this flag, script runs in dry-run/inspect mode.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip verification queries (query_points and query_points_groups)",
    )
    return parser.parse_args()


def check_and_configure_collection(
    client: Any,
    collection_name: str,
    dimension: int,
    quantile: float,
    apply: bool,
) -> dict[str, Any]:
    from qdrant_client.http.models import (
        Distance,
        HnswConfigDiff,
        OptimizersConfigDiff,
        ScalarQuantization,
        ScalarQuantizationConfig,
        ScalarType,
        SparseIndexParams,
        SparseVectorParams,
        VectorParams,
    )

    result: dict[str, Any] = {
        "collection": collection_name,
        "exists": False,
        "points_count": 0,
        "quantization_applied": False,
        "indexes_created": [],
        "indexes_existing": [],
        "errors": [],
    }

    try:
        collections = client.get_collections().collections
        existing_names = [c.name for c in collections]
    except Exception as e:
        logger.error("Failed to connect or list collections on Qdrant: %s", e)
        result["errors"].append(f"Connection failed: {e}")
        return result

    if collection_name not in existing_names:
        result["exists"] = False
        logger.warning(f"Collection '{collection_name}' does not exist.")
        if apply:
            logger.info(f"Creating collection '{collection_name}' with advanced configuration...")
            quant_cfg = ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=quantile,
                    always_ram=True,
                )
            )
            client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense": VectorParams(
                        size=dimension,
                        distance=Distance.COSINE,
                        on_disk=True,
                    ),
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(on_disk=False),
                    ),
                },
                hnsw_config=HnswConfigDiff(
                    m=32,
                    ef_construct=200,
                    full_scan_threshold=10000,
                ),
                quantization_config=quant_cfg,
                on_disk_payload=True,
            )
            result["exists"] = True
            result["quantization_applied"] = True
            logger.info(f"Collection '{collection_name}' created successfully.")
        else:
            logger.info("Dry-run mode: pass --apply to create the collection.")
            return result
    else:
        result["exists"] = True

    # Inspect current collection
    try:
        col_info = client.get_collection(collection_name)
        result["points_count"] = col_info.points_count
        result["status"] = str(col_info.status)
        logger.info(
            f"Collection '{collection_name}' status: {col_info.status}, points: {col_info.points_count}"
        )

        # Update quantization if collection exists and apply is set
        if apply:
            logger.info(
                f"Applying INT8 scalar quantization (quantile={quantile}, always_ram=True)..."
            )
            scalar_cfg = ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=quantile,
                    always_ram=True,
                )
            )
            client.update_collection(
                collection_name=collection_name,
                quantization_config=scalar_cfg,
                hnsw_config=HnswConfigDiff(
                    m=32,
                    ef_construct=200,
                    full_scan_threshold=10000,
                ),
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=20000,
                ),
            )
            result["quantization_applied"] = True
            logger.info("Collection quantization updated successfully.")
        else:
            logger.info(
                f"Dry-run: would apply INT8 quantization (quantile={quantile}) to '{collection_name}'"
            )

        # Ensure payload indexes
        payload_schema = col_info.payload_schema or {}
        for field_name, field_schema in REQUIRED_PAYLOAD_INDEXES:
            if field_name in payload_schema:
                result["indexes_existing"].append(field_name)
            else:
                if apply:
                    try:
                        logger.info(
                            f"Creating payload index for '{field_name}' ({field_schema})..."
                        )
                        client.create_payload_index(
                            collection_name=collection_name,
                            field_name=field_name,
                            field_schema=field_schema,
                        )
                        result["indexes_created"].append(field_name)
                    except Exception as idx_err:
                        logger.warning(f"Failed creating index for {field_name}: {idx_err}")
                        result["errors"].append(f"Index error ({field_name}): {idx_err}")
                else:
                    logger.info(f"Dry-run: would create index for '{field_name}' ({field_schema})")
                    result["indexes_created"].append(f"{field_name} (dry-run)")

    except Exception as exc:
        logger.error("Error configuring collection: %s", exc)
        result["errors"].append(str(exc))

    return result


def verify_universal_queries(
    client: Any,
    collection_name: str,
    dimension: int,
) -> dict[str, Any]:
    """Test Universal Query API and Parent Document Grouping."""
    from qdrant_client.http.models import (
        Fusion,
        FusionQuery,
        Prefetch,
        SparseVector,
    )

    test_report: dict[str, Any] = {
        "universal_query_rrf": False,
        "universal_query_dbsf": False,
        "parent_group_query": False,
        "group_key_used": None,
        "details": [],
    }

    dummy_dense = [0.01] * dimension
    dummy_sparse = SparseVector(indices=[1, 42, 105], values=[0.5, 0.8, 0.3])

    # 1. Test Universal Query with RRF
    try:
        logger.info("Testing Universal Query API with Prefetch (dense + sparse) and Fusion.RRF...")
        res_rrf = client.query_points(
            collection_name=collection_name,
            prefetch=[
                Prefetch(query=dummy_dense, using="dense", limit=5),
                Prefetch(query=dummy_sparse, using="sparse", limit=5),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=5,
            with_payload=True,
        )
        test_report["universal_query_rrf"] = True
        test_report["details"].append(f"Universal Query RRF passed ({len(res_rrf.points)} hits)")
        logger.info("Universal Query RRF passed.")
    except Exception as e:
        logger.warning("Universal Query RRF test failed: %s", e)
        test_report["details"].append(f"Universal Query RRF failed: {e}")

    # 2. Test Universal Query with DBSF
    try:
        logger.info("Testing Universal Query API with Prefetch (dense + sparse) and Fusion.DBSF...")
        res_dbsf = client.query_points(
            collection_name=collection_name,
            prefetch=[
                Prefetch(query=dummy_dense, using="dense", limit=5),
                Prefetch(query=dummy_sparse, using="sparse", limit=5),
            ],
            query=FusionQuery(fusion=Fusion.DBSF),
            limit=5,
            with_payload=True,
        )
        test_report["universal_query_dbsf"] = True
        test_report["details"].append(f"Universal Query DBSF passed ({len(res_dbsf.points)} hits)")
        logger.info("Universal Query DBSF passed.")
    except Exception as e:
        logger.warning("Universal Query DBSF test failed: %s", e)
        test_report["details"].append(f"Universal Query DBSF failed: {e}")

    # 3. Test Parent Document Group Search (hierarchy: video_id -> source_url -> parent_id)
    group_candidates = ["video_id", "source_url", "parent_id"]
    for grp_field in group_candidates:
        try:
            logger.info(f"Testing Parent Document Group Search with group_by='{grp_field}'...")
            res_group = client.query_points_groups(
                collection_name=collection_name,
                prefetch=[
                    Prefetch(query=dummy_dense, using="dense", limit=10),
                    Prefetch(query=dummy_sparse, using="sparse", limit=10),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                group_by=grp_field,
                limit=3,
                group_size=2,
                with_payload=True,
            )
            test_report["parent_group_query"] = True
            test_report["group_key_used"] = grp_field
            test_report["details"].append(
                f"Group search with '{grp_field}' passed ({len(res_group.groups)} groups returned)"
            )
            logger.info(f"Parent Document Group Search passed using '{grp_field}'.")
            break
        except Exception as grp_err:
            logger.warning(f"Group search test with '{grp_field}' failed: {grp_err}")
            test_report["details"].append(f"Group search '{grp_field}' failed: {grp_err}")

    return test_report


def main() -> int:
    from qdrant_client import QdrantClient

    args = parse_args()
    logger.info("Starting Qdrant Advanced Architecture configuration...")
    logger.info(f"Target Qdrant: {args.url}, Collection: {args.collection}")

    client = QdrantClient(
        url=args.url,
        api_key=args.api_key or None,
        timeout=30.0,
        check_compatibility=False,
    )

    config_result = check_and_configure_collection(
        client=client,
        collection_name=args.collection,
        dimension=args.dimension,
        quantile=args.quantile,
        apply=args.apply,
    )

    test_result = {}
    if not args.skip_tests and config_result["exists"]:
        test_result = verify_universal_queries(
            client=client,
            collection_name=args.collection,
            dimension=args.dimension,
        )

    full_report = {
        "status": "SUCCESS" if not config_result.get("errors") else "WARNING",
        "mode": "APPLIED" if args.apply else "DRY_RUN",
        "config": config_result,
        "tests": test_result,
    }

    print("\n" + "=" * 60)
    print("QDRANT ADVANCED ARCHITECTURE REPORT")
    print("=" * 60)
    print(json.dumps(full_report, indent=2))
    print("=" * 60)

    if config_result.get("errors"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
