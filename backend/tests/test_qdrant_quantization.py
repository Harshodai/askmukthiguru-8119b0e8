import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qdrant_client.http.models import (
    BinaryQuantization,
    ScalarQuantization,
    TurboQuantization,
)

from services.qdrant.client import QdrantClientManager
from services.qdrant.searcher import QdrantSearcher


def test_scalar_int8_matches_legacy_config():
    """Default scalar_int8 must produce exactly the original hardcoded config."""
    cfg = QdrantClientManager._build_quantization_config("scalar_int8")
    assert isinstance(cfg, ScalarQuantization)
    assert cfg.scalar.type.value == "int8"
    assert cfg.scalar.always_ram is True


def test_binary_config():
    cfg = QdrantClientManager._build_quantization_config("binary")
    assert isinstance(cfg, BinaryQuantization)
    assert cfg.binary.always_ram is True


def test_turboquant_configs():
    for setting, expected in [
        ("turboquant_1bit", "bits1"),
        ("turboquant_2bit", "bits2"),
        ("turboquant_4bit", "bits4"),
    ]:
        cfg = QdrantClientManager._build_quantization_config(setting)
        assert isinstance(cfg, TurboQuantization), setting
        assert cfg.turbo.bits.value == expected, setting
        assert cfg.turbo.always_ram is True, setting


def test_invalid_quantization_raises():
    for bad in ["scalar_int4", "turboquant_8bit", "unknown"]:
        with pytest.raises(ValueError):
            QdrantClientManager._build_quantization_config(bad)


def test_search_params_scalar_default_is_none():
    """When quantization is scalar_int8, dense search should not pass extra params."""
    with patch("services.qdrant.searcher.settings") as mock_settings:
        mock_settings.qdrant_quantization = "scalar_int8"
        mock_settings.qdrant_quantization_oversampling = 3.0
        client = MagicMock()
        client.query_points.return_value = MagicMock(points=[])
        searcher = QdrantSearcher(client, "test")
        searcher._dense_search([0.1] * 8, 5, None)
        call_kwargs = client.query_points.call_args.kwargs
        assert call_kwargs.get("search_params") is None


def test_search_params_binary_includes_rescore_oversampling():
    with patch("services.qdrant.searcher.settings") as mock_settings:
        mock_settings.qdrant_quantization = "binary"
        mock_settings.qdrant_quantization_oversampling = 2.5
        client = MagicMock()
        client.query_points.return_value = MagicMock(points=[])
        searcher = QdrantSearcher(client, "test")
        searcher._dense_search([0.1] * 8, 5, None)
        call_kwargs = client.query_points.call_args.kwargs
        params = call_kwargs.get("search_params")
        assert params is not None
        assert params.quantization.rescore is True
        assert params.quantization.oversampling == 2.5


def test_hybrid_prefetch_dense_includes_params():
    with patch("services.qdrant.searcher.settings") as mock_settings:
        mock_settings.qdrant_quantization = "turboquant_2bit"
        mock_settings.qdrant_quantization_oversampling = 4.0
        client = MagicMock()
        client.query_points.return_value = MagicMock(points=[])
        searcher = QdrantSearcher(client, "test")
        sparse = {1: 0.5, 2: 0.5}
        searcher.search(
            query_vector=[0.1] * 8,
            limit=3,
            sparse_vector=sparse,
        )
        prefetches = client.query_points.call_args.kwargs["prefetch"]
        dense_prefetch = next(p for p in prefetches if p.using == "dense")
        assert dense_prefetch.params is not None
        assert dense_prefetch.params.quantization.rescore is True
        assert dense_prefetch.params.quantization.oversampling == 4.0

        sparse_prefetch = next(p for p in prefetches if p.using == "sparse")
        assert sparse_prefetch.params is None


if __name__ == "__main__":
    test_scalar_int8_matches_legacy_config()
    test_binary_config()
    test_turboquant_configs()
    test_invalid_quantization_raises()
    test_search_params_scalar_default_is_none()
    test_search_params_binary_includes_rescore_oversampling()
    test_hybrid_prefetch_dense_includes_params()
    print("All self-checks passed.")
