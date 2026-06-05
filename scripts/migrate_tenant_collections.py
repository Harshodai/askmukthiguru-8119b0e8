#!/usr/bin/env python3
"""
Unit 19 — Multi-Tenant Collection Migration Script

Soft migration: creates per-tenant Qdrant collection namespaces without
deleting or moving existing data. The legacy default collection is left intact.

Usage:
    python scripts/migrate_tenant_collections.py --dry-run
    python scripts/migrate_tenant_collections.py --tenant my-org-id

What it does:
  1. Lists all existing collections in Qdrant
  2. For each new tenant ID provided (or from a config file), creates a
     namespaced collection with the same vector config as the primary collection.
  3. Logs the result — does NOT copy data (soft mode: tenants start fresh).

Soft mode (default):
  - Legacy data on {QDRANT_COLLECTION} stays untouched.
  - New tenants get {QDRANT_COLLECTION}__tenant_{tenant_id}.
  - No data is moved or deleted.

Hard mode (future):
  - Run a separate ETL to move points filtered by user_id to tenant collections.
  - Controlled by --hard flag (not yet implemented).
"""

from __future__ import annotations

import argparse
import sys
import os

# Allow running from repo root or backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    parser = argparse.ArgumentParser(description="Multi-tenant Qdrant collection migration")
    parser.add_argument("--tenant", nargs="+", help="Tenant ID(s) to create collections for")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without doing it")
    args = parser.parse_args()

    try:
        from app.config import settings
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import (
            Distance, VectorParams, SparseVectorParams, SparseIndexParams,
            ScalarQuantization, ScalarQuantizationConfig, ScalarType
        )
    except ImportError as e:
        print(f"ERROR: Cannot import backend modules: {e}")
        print("Run this script from the backend/ directory or set PYTHONPATH.")
        sys.exit(1)

    if settings.qdrant_local_path:
        client = QdrantClient(path=settings.qdrant_local_path, check_compatibility=False)
    else:
        client = QdrantClient(url=settings.qdrant_url, check_compatibility=False)

    base_collection = settings.qdrant_collection
    dimension = settings.embedding_dimension

    existing = [c.name for c in client.get_collections().collections]
    print(f"Existing collections: {existing}")
    print(f"Base collection: {base_collection}")
    print(f"Dry run: {args.dry_run}")
    print()

    tenant_ids = args.tenant or []
    if not tenant_ids:
        print("No --tenant IDs provided. Nothing to migrate.")
        print("Usage: python scripts/migrate_tenant_collections.py --tenant org1 org2")
        return

    for tenant_id in tenant_ids:
        # Sanitize tenant ID
        safe_tid = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_id)
        coll_name = f"{base_collection}__tenant_{safe_tid}"

        if coll_name in existing:
            print(f"  SKIP  {coll_name} (already exists)")
            continue

        print(f"  CREATE {coll_name} ...")
        if not args.dry_run:
            client.create_collection(
                collection_name=coll_name,
                vectors_config={
                    "dense": VectorParams(size=dimension, distance=Distance.COSINE),
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(index=SparseIndexParams()),
                },
                quantization_config=ScalarQuantization(
                    scalar=ScalarQuantizationConfig(
                        type=ScalarType.INT8,
                        always_ram=True,
                    )
                ),
                on_disk_payload=True,
            )
            # Create the same indexes as the primary collection
            client.create_payload_index(coll_name, "raptor_level", "integer")
            client.create_payload_index(coll_name, "phonetic_tokens", "keyword")
            print(f"  DONE  {coll_name}")
        else:
            print(f"  (dry-run) Would create {coll_name} with {dimension}d dense + sparse vectors")

    if args.dry_run:
        print("\nDry run complete. No changes were made.")
    else:
        print("\nMigration complete.")


if __name__ == "__main__":
    main()
