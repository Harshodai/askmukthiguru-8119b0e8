import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qdrant_client.http.models import (
    Fusion,
    FusionQuery,
    ScalarQuantization,
    ScalarType,
)

from rag.nodes.utils import _fuse_docs
from services.qdrant.client import QdrantClientManager
from services.qdrant.searcher import QdrantSearcher
from services.qdrant_service import QdrantService


def test_scalar_quantization_quantile_099():
    """Verify ScalarQuantizationConfig applies quantile=0.99 and always_ram=True."""
    cfg = QdrantClientManager._build_quantization_config("scalar_int8")
    assert isinstance(cfg, ScalarQuantization)
    assert cfg.scalar.type == ScalarType.INT8
    assert cfg.scalar.quantile == 0.99
    assert cfg.scalar.always_ram is True


def test_payload_indexes_include_grouping_fields():
    """Verify video_id, source_url, parent_id are in required payload indexes."""
    index_dict = dict(QdrantClientManager._PAYLOAD_INDEXES)
    assert index_dict.get("video_id") == "keyword"
    assert index_dict.get("source_url") == "keyword"
    assert index_dict.get("parent_id") == "keyword"


def test_searcher_calls_query_points_groups_with_prefetch_and_fusion():
    """Verify QdrantSearcher.search with group_by uses query_points_groups with prefetch & RRF fusion."""
    client = MagicMock()
    mock_point = MagicMock()
    mock_point.id = "pt-1"
    mock_point.payload = {
        "text": "Spiritual teaching chunk",
        "video_id": "vid-123",
        "parent_id": "parent-abc",
        "source_url": "https://youtube.com/watch?v=vid-123",
    }
    mock_point.score = 0.88
    mock_point.vector = {"dense": [0.1] * 1024}

    mock_group = MagicMock()
    mock_group.id = "vid-123"
    mock_group.hits = [mock_point]

    client.query_points_groups.return_value = MagicMock(groups=[mock_group])

    searcher = QdrantSearcher(client, "test_collection")
    sparse_vec = {1: 0.5, 42: 0.8}

    results = searcher.search_groups(
        query_vector=[0.1] * 1024,
        group_by="video_id",
        group_size=2,
        limit=5,
        sparse_vector=sparse_vec,
        fusion_strategy="rrf",
    )

    assert client.query_points_groups.called
    kwargs = client.query_points_groups.call_args.kwargs

    assert kwargs["collection_name"] == "test_collection"
    assert kwargs["group_by"] == "video_id"
    assert kwargs["group_size"] == 2
    assert kwargs["limit"] == 5 + 5  # internal_limit = limit + 5
    assert isinstance(kwargs["query"], FusionQuery)
    assert kwargs["query"].fusion == Fusion.RRF

    # Verify prefetches
    prefetches = kwargs["prefetch"]
    assert len(prefetches) == 2
    dense_prefetch = next(p for p in prefetches if p.using == "dense")
    sparse_prefetch = next(p for p in prefetches if p.using == "sparse")
    assert dense_prefetch is not None
    assert sparse_prefetch is not None

    # Verify returned doc format
    assert len(results) == 1
    doc = results[0]
    assert doc["text"] == "Spiritual teaching chunk"
    assert doc["video_id"] == "vid-123"
    assert doc["group_id"] == "vid-123"
    assert doc["_dense_embedding"] == [0.1] * 1024


def test_searcher_dbsf_fusion():
    """Verify QdrantSearcher supports DBSF fusion strategy."""
    client = MagicMock()
    client.query_points.return_value = MagicMock(points=[])

    searcher = QdrantSearcher(client, "test_collection")
    searcher.search(
        query_vector=[0.1] * 1024,
        limit=5,
        sparse_vector={1: 0.5},
        fusion_strategy="dbsf",
    )

    kwargs = client.query_points.call_args.kwargs
    assert isinstance(kwargs["query"], FusionQuery)
    assert kwargs["query"].fusion == Fusion.DBSF


def test_dbsf_and_fuse_docs():
    """Verify Distribution-Based Score Fusion algorithm and _fuse_docs wrapper."""
    list1 = [
        {"text": "doc1", "source_url": "u1", "score": 0.9},
        {"text": "doc2", "source_url": "u2", "score": 0.7},
    ]
    list2 = [
        {"text": "doc2", "source_url": "u2", "score": 0.85},
        {"text": "doc3", "source_url": "u3", "score": 0.4},
    ]

    # DBSF
    fused_dbsf = _fuse_docs([list1, list2], strategy="dbsf")
    assert len(fused_dbsf) == 3
    # doc2 appeared in both with high scores, so it should rank first in DBSF
    assert fused_dbsf[0]["source_url"] == "u2"

    # RRF
    fused_rrf = _fuse_docs([list1, list2], strategy="rrf")
    assert len(fused_rrf) == 3
    assert fused_rrf[0]["source_url"] == "u2"


def test_qdrant_service_search_groups_facade():
    """Verify QdrantService facade delegates to search_groups."""
    mock_client = MagicMock()
    mock_client.get_collections.return_value = MagicMock(collections=[MagicMock(name="test_col")])
    mock_client.get_collection.return_value = MagicMock(
        config=MagicMock(params=MagicMock(vectors={"dense": MagicMock(size=1024)}))
    )
    mock_group = MagicMock(id="grp1", hits=[])
    mock_client.query_points_groups.return_value = MagicMock(groups=[mock_group])

    service = QdrantService(collection="test_col", client=mock_client)
    res = service.search_groups(
        query_vector=[0.1] * 1024,
        group_by="parent_id",
        group_size=2,
        limit=5,
    )
    assert isinstance(res, list)
    assert mock_client.query_points_groups.called


def test_configure_qdrant_advanced_script():
    """Verify check_and_configure_collection and verify_universal_queries functions."""
    from scripts.ops.configure_qdrant_advanced import (
        check_and_configure_collection,
        verify_universal_queries,
    )

    mock_client = MagicMock()
    mock_client.get_collections.return_value = MagicMock(
        collections=[MagicMock(name="spiritual_wisdom_contextual")]
    )
    mock_col_info = MagicMock()
    mock_col_info.points_count = 12000
    mock_col_info.status = "green"
    mock_col_info.payload_schema = {"tenant_id": MagicMock(), "corpus_id": MagicMock()}
    mock_client.get_collection.return_value = mock_col_info

    # Test apply=True
    cfg_result = check_and_configure_collection(
        client=mock_client,
        collection_name="spiritual_wisdom_contextual",
        dimension=1024,
        quantile=0.99,
        apply=True,
    )

    assert cfg_result["exists"] is True
    assert cfg_result["quantization_applied"] is True
    assert mock_client.update_collection.called
    assert mock_client.create_payload_index.called
    # Check that video_id and parent_id were created
    assert "video_id" in cfg_result["indexes_created"]
    assert "parent_id" in cfg_result["indexes_created"]

    # Test verify_universal_queries
    mock_client.query_points.return_value = MagicMock(points=[MagicMock()])
    mock_client.query_points_groups.return_value = MagicMock(groups=[MagicMock()])

    query_res = verify_universal_queries(
        client=mock_client,
        collection_name="spiritual_wisdom_contextual",
        dimension=1024,
    )
    assert query_res["universal_query_rrf"] is True
    assert query_res["universal_query_dbsf"] is True
    assert query_res["parent_group_query"] is True
    assert query_res["group_key_used"] == "video_id"
