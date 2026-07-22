#!/usr/bin/env python3
"""Backfill cluster_id on spiritual_wisdom Qdrant points using k-means clustering.

Run ONCE after deployment or after large ingestion batches. Reads all vectors from
Qdrant, runs k-means (k=64), then writes cluster_id back to each point's payload.

Usage:
  cd backend
  .venv/bin/python scripts/ops/backfill_clusters.py [--dry-run] [--k 64] [--batch 500]

Takes ~15-30 minutes for 89k × 1024d vectors. Requires ~4-6GB RAM.
Safe to re-run (idempotent: overwrites cluster_id on every point).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

COLLECTION = "spiritual_wisdom"
DEFAULT_K = 64


def main() -> None:
    parser = argparse.ArgumentParser(description="K-means cluster backfill for spiritual_wisdom")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    parser.add_argument("--k", type=int, default=DEFAULT_K, help="Number of clusters (default 64)")
    parser.add_argument("--batch", type=int, default=500, help="Scroll batch size")
    parser.add_argument("--limit", type=int, default=0, help="Max points to cluster (0 = all)")
    args = parser.parse_args()

    import numpy as np
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointIdsList

    try:
        from sklearn.cluster import MiniBatchKMeans
    except ImportError:
        print("ERROR: scikit-learn not installed. Run: pip install scikit-learn")
        sys.exit(1)

    from app.config import settings
    qdrant_api_key = os.environ.get("QDRANT_API_KEY", "")
    client = QdrantClient(url=settings.qdrant_url, api_key=qdrant_api_key or None, timeout=60)

    print(f"Connected to Qdrant at {settings.qdrant_url}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE WRITE'}, k={args.k}")

    # Phase 1: scroll all points + vectors
    print("Phase 1: reading all vectors from Qdrant...")
    all_ids: list[int | str] = []
    all_vectors: list[list[float]] = []
    offset = None
    start = time.time()

    while True:
        results, next_offset = client.scroll(
            collection_name=COLLECTION,
            limit=args.batch,
            offset=offset,
            with_payload=False,
            with_vectors=True,
        )
        if not results:
            break
        for point in results:
            vec = getattr(point, "vector", None)
            if vec is not None:
                all_ids.append(point.id)
                if isinstance(vec, dict):
                    embedding = next(iter(vec.values()))
                    all_vectors.append(embedding if isinstance(embedding, list) else list(embedding))
                else:
                    all_vectors.append(vec if isinstance(vec, list) else list(vec))
        print(f"  Scrolled {len(all_ids)} points...", end="\r")
        if args.limit and len(all_ids) >= args.limit:
            break
        offset = next_offset
        if offset is None:
            break

    print(f"\nRead {len(all_ids)} vectors in {time.time() - start:.1f}s")

    if not all_ids:
        print("No vectors found. Exiting.")
        return

    # Phase 2: k-means clustering
    print(f"Phase 2: running MiniBatchKMeans k={args.k} on {len(all_ids)} vectors...")
    X = np.array(all_vectors, dtype=np.float32)
    kmeans = MiniBatchKMeans(
        n_clusters=args.k,
        batch_size=min(4096, len(all_ids)),
        max_iter=100,
        random_state=42,
        n_init=3,
    )
    labels = kmeans.fit_predict(X)
    print(f"Clustering done. Cluster sizes: min={int(np.bincount(labels).min())}, max={int(np.bincount(labels).max())}")

    # Phase 3: write cluster_id back to Qdrant
    if args.dry_run:
        print("DRY RUN — skipping Qdrant writes")
        return

    print("Phase 3: writing cluster_id to Qdrant payload fields...")
    write_start = time.time()
    for i, (point_id, cluster_id) in enumerate(zip(all_ids, labels.tolist())):
        try:
            client.set_payload(
                collection_name=COLLECTION,
                payload={"cluster_id": cluster_id},
                points=PointIdsList(points=[point_id]),
            )
        except Exception as e:
            print(f"  WARN: failed on {point_id}: {e}")
        if (i + 1) % 1000 == 0:
            elapsed = time.time() - write_start
            rate = (i + 1) / elapsed
            eta = (len(all_ids) - i - 1) / max(rate, 0.1)
            print(f"  Written {i + 1}/{len(all_ids)} ({rate:.0f}/s, ETA {eta:.0f}s)...")

    print(f"Done. {len(all_ids)} points updated with cluster_id in {time.time() - write_start:.1f}s")


if __name__ == "__main__":
    main()
