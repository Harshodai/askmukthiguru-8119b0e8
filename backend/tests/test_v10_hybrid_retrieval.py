"""Tests for T4-02 / RET-02: Hybrid dense + sparse RRF in v10 context store.

Ensures that:
1. When query_sparse is provided to FirstPersonContextStore.retrieve, both dense
   and sparse prefetches are sent to Qdrant with FusionQuery(fusion=Fusion.RRF)
   both in query_points_groups and the query_points fallback.
2. Grouping by parent_unit_id is preserved across both dense and sparse hits.
"""

from unittest.mock import MagicMock

from qdrant_client.http.models import Fusion, FusionQuery, Prefetch, SparseVector

from domain.first_person_context import ParentUnit, SourceSpan
from services.first_person_context_store import FirstPersonContextStore


def _make_dummy_parent_and_span(pid: str = "p_unit_1", sid: str = "s_span_1"):
    span = SourceSpan(
        corpus_version="ctx-v1",
        guru_id="krishnaji",
        video_id="vid_1",
        source_asset_id="vid_1",
        source_span_id=sid,
        parent_unit_id=pid,
        start_ms=1000,
        end_ms=5000,
        verbatim_text="Meditation brings deep silence.",
        transcript_hash="a" * 64,
        rights_cleared=True,
        domain_rights_status="licensed",
        speaker_verified=True,
        speaker_role="guru",
    )
    parent = ParentUnit(
        corpus_version="ctx-v1",
        parent_unit_id=pid,
        video_id="vid_1",
        guru_id="krishnaji",
        source_asset_id="vid_1",
        start_ms=1000,
        end_ms=5000,
        verbatim_text="Meditation brings deep silence.",
        ordered_source_span_ids=(sid,),
        rights_cleared=True,
        domain_rights_status="licensed",
        speaker_verified=True,
    )
    return parent, [span]


def test_context_store_hybrid_sends_dense_and_sparse_prefetches_to_groups(monkeypatch):
    """When query_sparse is provided, query_points_groups must receive dense+sparse prefetches and RRF."""
    monkeypatch.setattr(
        "services.first_person_context_store.source_is_authoritatively_licensed",
        lambda **kw: True,
    )
    monkeypatch.setattr(
        "services.first_person_context_store.blocked_video_ids_or_none",
        lambda: set(),
    )

    client = MagicMock()
    # Mock query_points_groups
    client.query_points_groups.return_value = MagicMock(groups=[])

    store = FirstPersonContextStore(client, collection="first_person_v10")

    query_dense = [0.1] * 8
    query_sparse = {"indices": [42, 99], "values": [0.7, 0.9]}

    store.retrieve(query_dense, query_sparse=query_sparse, limit_parents=3)

    client.query_points_groups.assert_called_once()
    kwargs = client.query_points_groups.call_args.kwargs

    assert "prefetch" in kwargs
    prefetches = kwargs["prefetch"]
    assert len(prefetches) == 2
    assert all(isinstance(p, Prefetch) for p in prefetches)

    dense_prefetch = prefetches[0]
    sparse_prefetch = prefetches[1]

    assert dense_prefetch.using == "passage_dense"
    assert dense_prefetch.query == query_dense

    assert sparse_prefetch.using == "passage_sparse"
    assert isinstance(sparse_prefetch.query, SparseVector)
    assert sparse_prefetch.query.indices == [42, 99]
    assert sparse_prefetch.query.values == [0.7, 0.9]

    assert isinstance(kwargs["query"], FusionQuery)
    assert kwargs["query"].fusion == Fusion.RRF
    assert kwargs["group_by"] == "parent_unit_id"


def test_context_store_hybrid_sends_dense_and_sparse_prefetches_to_fallback(monkeypatch):
    """When query_points_groups is absent, query_points fallback must receive dense+sparse prefetches and RRF."""
    monkeypatch.setattr(
        "services.first_person_context_store.source_is_authoritatively_licensed",
        lambda **kw: True,
    )
    monkeypatch.setattr(
        "services.first_person_context_store.blocked_video_ids_or_none",
        lambda: set(),
    )

    client = MagicMock(spec=["query_points", "retrieve"])
    client.query_points.return_value = MagicMock(points=[])

    store = FirstPersonContextStore(client, collection="first_person_v10")

    query_dense = [0.1] * 8
    query_sparse = {"indices": [42, 99], "values": [0.7, 0.9]}

    store.retrieve(query_dense, query_sparse=query_sparse, limit_parents=3)

    client.query_points.assert_called_once()
    kwargs = client.query_points.call_args.kwargs

    assert "prefetch" in kwargs
    prefetches = kwargs["prefetch"]
    assert len(prefetches) == 2
    assert all(isinstance(p, Prefetch) for p in prefetches)

    dense_prefetch = prefetches[0]
    sparse_prefetch = prefetches[1]

    assert dense_prefetch.using == "passage_dense"
    assert sparse_prefetch.using == "passage_sparse"
    assert sparse_prefetch.query.indices == [42, 99]

    assert isinstance(kwargs["query"], FusionQuery)
    assert kwargs["query"].fusion == Fusion.RRF


def test_context_store_dense_only_when_no_sparse_vector(monkeypatch):
    """When query_sparse is None or empty, query_points_groups queries dense directly."""
    monkeypatch.setattr(
        "services.first_person_context_store.source_is_authoritatively_licensed",
        lambda **kw: True,
    )
    monkeypatch.setattr(
        "services.first_person_context_store.blocked_video_ids_or_none",
        lambda: set(),
    )

    client = MagicMock()
    client.query_points_groups.return_value = MagicMock(groups=[])

    store = FirstPersonContextStore(client, collection="first_person_v10")

    query_dense = [0.1] * 8
    store.retrieve(query_dense, query_sparse=None, limit_parents=3)

    client.query_points_groups.assert_called_once()
    kwargs = client.query_points_groups.call_args.kwargs
    assert kwargs.get("using") == "passage_dense"
    assert kwargs.get("query") == query_dense
    assert "prefetch" not in kwargs
