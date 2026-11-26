"""Tests for serving-path hnsw_ef propagation to Qdrant."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.qdrant.searcher import QdrantSearcher


def test_hnsw_ef_search_param_propagation():
    """Verify hnsw_ef is passed to SearchParams when configured or explicitly passed."""
    client = MagicMock()
    client.query_points.return_value = MagicMock(points=[])
    searcher = QdrantSearcher(client, "test_collection")

    # 1. Default configured hnsw_ef (e.g. 64)
    with patch("services.qdrant.searcher.settings") as mock_settings:
        mock_settings.qdrant_quantization = "scalar_int8"
        mock_settings.qdrant_hnsw_ef_search = 64
        searcher._dense_search([0.1] * 8, 5, None)
        call_kwargs = client.query_points.call_args.kwargs
        params = call_kwargs.get("search_params")
        assert params is not None
        assert params.hnsw_ef == 64

    # 2. Custom explicit hnsw_ef via kwargs
    with patch("services.qdrant.searcher.settings") as mock_settings:
        mock_settings.qdrant_quantization = "scalar_int8"
        mock_settings.qdrant_hnsw_ef_search = 64
        searcher._dense_search(
            [0.1] * 8,
            5,
            None,
            search_params=searcher._dense_quantization_search_params(hnsw_ef=128),
        )
        call_kwargs = client.query_points.call_args.kwargs
        params = call_kwargs.get("search_params")
        assert params is not None
        assert params.hnsw_ef == 128

    # 3. Disabled ef_search (0) with scalar_int8 returns None
    with patch("services.qdrant.searcher.settings") as mock_settings:
        mock_settings.qdrant_quantization = "scalar_int8"
        mock_settings.qdrant_hnsw_ef_search = 0
        searcher._dense_search([0.1] * 8, 5, None)
        call_kwargs = client.query_points.call_args.kwargs
        params = call_kwargs.get("search_params")
        assert params is None


def test_hnsw_ef_hybrid_prefetch_dense():
    """Verify hnsw_ef is included in dense prefetch during hybrid search."""
    client = MagicMock()
    client.query_points.return_value = MagicMock(points=[])
    searcher = QdrantSearcher(client, "test_collection")

    with patch("services.qdrant.searcher.settings") as mock_settings:
        mock_settings.qdrant_quantization = "scalar_int8"
        mock_settings.qdrant_hnsw_ef_search = 96
        mock_settings.qdrant_dense_prefetch_multiplier = 2.0
        mock_settings.qdrant_sparse_prefetch_multiplier = 1.5
        mock_settings.qdrant_fusion_strategy = "rrf"

        sparse = {1: 0.5, 2: 0.5}
        searcher.search(query_vector=[0.1] * 8, limit=5, sparse_vector=sparse)

        call_kwargs = client.query_points.call_args.kwargs
        prefetches = call_kwargs.get("prefetch", [])
        assert len(prefetches) == 2
        dense_prefetch = prefetches[0]
        assert dense_prefetch.params is not None
        assert dense_prefetch.params.hnsw_ef == 96
