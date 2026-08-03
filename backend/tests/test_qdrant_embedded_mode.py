"""Embedded (local, no-Docker) Qdrant mode: correctness + optional stress test.

Validates the same code path used when `settings.qdrant_local_path` is set
(no Docker Qdrant — future mobile/edge deployments). The pytest-collected test
uses a small vector set for speed; the 100k-vector/1000-search stress variant
is opt-in via the `slow` marker (not run in normal CI — it takes minutes).
"""

import random
import time

import pytest
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

DIM = 1024  # matches settings.embedding_dimension (BAAI/bge-m3)


def _make_random_vector(dim: int = DIM) -> list[float]:
    return [random.uniform(-1, 1) for _ in range(dim)]


def _build_embedded_collection(client: QdrantClient, collection: str, n_vectors: int) -> None:
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
    )
    points = [
        PointStruct(id=i, vector=_make_random_vector(), payload={"source_url": f"doc_{i}"})
        for i in range(n_vectors)
    ]
    # Batch upsert like production QdrantIndexer does
    batch_size = 200
    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=collection, points=points[i : i + batch_size])


def test_embedded_mode_basic_search_correctness():
    """Small-scale correctness check: embedded (:memory:) mode returns sane results."""
    client = QdrantClient(path=":memory:")
    collection = "test_embedded_small"
    n_vectors = 200

    _build_embedded_collection(client, collection, n_vectors)

    query_vector = _make_random_vector()
    results = client.query_points(
        collection_name=collection,
        query=query_vector,
        limit=10,
        with_payload=True,
    )

    assert len(results.points) == 10
    for point in results.points:
        assert "source_url" in point.payload
        assert point.score is not None


def test_embedded_mode_consistent_across_repeated_queries():
    """Same query vector must return the same top result deterministically."""
    client = QdrantClient(path=":memory:")
    collection = "test_embedded_consistency"
    n_vectors = 100

    _build_embedded_collection(client, collection, n_vectors)

    query_vector = _make_random_vector()
    result1 = client.query_points(collection_name=collection, query=query_vector, limit=5)
    result2 = client.query_points(collection_name=collection, query=query_vector, limit=5)

    ids1 = [p.id for p in result1.points]
    ids2 = [p.id for p in result2.points]
    assert ids1 == ids2


def test_embedded_mode_no_network_required():
    """Embedded mode must work with no QDRANT_URL / network dependency at all."""
    # path=":memory:" never touches disk or network — this is the assertion itself:
    # if this call didn't raise, no network was needed.
    client = QdrantClient(path=":memory:")
    collection = "test_embedded_offline"
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
    )
    assert client.collection_exists(collection)


@pytest.mark.slow
def test_embedded_mode_stress_100k_vectors():
    """Opt-in stress test: 100k vectors, 1000 searches. Run explicitly:
    pytest tests/test_qdrant_embedded_mode.py -m slow -v
    """
    client = QdrantClient(path=":memory:")
    collection = "test_embedded_stress"
    n_vectors = 100_000
    n_searches = 1000

    start = time.time()
    _build_embedded_collection(client, collection, n_vectors)
    build_time = time.time() - start

    latencies = []
    for _ in range(n_searches):
        query_vector = _make_random_vector()
        t0 = time.time()
        client.query_points(collection_name=collection, query=query_vector, limit=10)
        latencies.append((time.time() - t0) * 1000)

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]

    print(f"\nEmbedded mode stress: build={build_time:.1f}s, p50={p50:.1f}ms, p95={p95:.1f}ms")
    # Sanity bound only — this documents behavior, not a strict perf contract
    assert p95 < 5000, f"p95 search latency too high for embedded mode: {p95}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "slow"])
