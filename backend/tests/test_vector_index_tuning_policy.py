"""Tests for vector index tuning policy and benchmark matrix generation."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from benchmarks.hnsw_tuning_sweep import (
    calculate_recall,
    recommend_hnsw_params,
    run_hnsw_sweep,
)
from services.vector_optimizer import VectorIndexOptimizer


def test_vector_optimizer_defaults_reconciled():
    """Verify that run_optimization() in vector_optimizer calls aligned defaults (32, 200)."""
    source = inspect.getsource(VectorIndexOptimizer.run_optimization)
    assert "32, 200, 10_000" in source, (
        "Optimizer defaults should align with fresh collection schema (m=32, ef_construct=200)"
    )


def test_scale_aware_recommendations():
    # 1. Very small corpus -> Flat exact scan
    small = recommend_hnsw_params(num_vectors=5_000)
    assert small["index_type"] == "flat"
    assert small["expected_recall"] == 1.0

    # 2. Medium corpus -> HNSW
    medium = recommend_hnsw_params(num_vectors=250_000, target_recall=0.95)
    assert medium["index_type"] == "hnsw"
    assert medium["M"] == 32
    assert medium["ef_construction"] == 200
    assert medium["ef_search"] in [64, 128]

    # 3. Large corpus -> HNSW + Quantization
    large = recommend_hnsw_params(num_vectors=5_000_000, available_memory_gb=8.0)
    assert large["index_type"] == "hnsw"
    assert large["quantization"] in ["scalar_int8", "binary"]
    assert large["M"] == 48

    # 4. Massive corpus -> IVF+PQ / DiskANN
    massive = recommend_hnsw_params(num_vectors=150_000_000)
    assert massive["index_type"] == "ivf_pq_or_diskann"


def test_calculate_recall():
    ground_truth = np.array(
        [
            [10, 11, 12, 13, 14],
            [20, 21, 22, 23, 24],
        ]
    )
    # Exact match -> 1.0
    preds_exact = np.array(
        [
            [10, 11, 12, 13, 14],
            [20, 21, 22, 23, 24],
        ]
    )
    assert calculate_recall(preds_exact, ground_truth, k=5) == 1.0

    # 3 of 5 match on row 0, 4 of 5 on row 1 -> (3 + 4) / 10 = 0.7
    preds_partial = np.array(
        [
            [10, 11, 12, 99, 98],
            [20, 21, 22, 23, 97],
        ]
    )
    assert calculate_recall(preds_partial, ground_truth, k=5) == 0.7


def test_run_hnsw_sweep_output_structure():
    np.random.seed(42)
    vectors = np.random.randn(50, 16).astype(np.float32)
    queries = np.random.randn(5, 16).astype(np.float32)

    results = run_hnsw_sweep(
        vectors=vectors,
        queries=queries,
        m_values=[8, 16],
        ef_construction_values=[64],
        ef_search_values=[32, 64],
        k=5,
    )

    # 2 M values * 1 efC * 2 efS = 4 results
    assert len(results) == 4
    for r in results:
        assert "M" in r
        assert "ef_construction" in r
        assert "ef_search" in r
        assert "recall@10" in r
        assert "latency_p50_ms" in r
        assert "latency_p95_ms" in r
        assert "memory_mb" in r
        assert "build_time_s" in r
        assert "benchmark_mode" in r
        assert "production_certified" in r
        assert r["recall@10"] > 0.0


def test_hnsw_sweep_require_native_fails_when_missing():
    vectors = np.random.randn(10, 8).astype(np.float32)
    queries = np.random.randn(2, 8).astype(np.float32)

    try:
        import hnswlib  # noqa: F401  (availability probe)

        has_hnswlib = True
    except ImportError:
        has_hnswlib = False

    if not has_hnswlib:
        with pytest.raises(RuntimeError) as exc_info:
            run_hnsw_sweep(vectors, queries, require_native=True)
        assert "Native C++ index library 'hnswlib' is required" in str(exc_info.value)
