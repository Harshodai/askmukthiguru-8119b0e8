"""Regression test for the 2026-09-26 parent-document-group-search defect.

Root cause (verified against live Qdrant, read-only): RAPTOR assigns
``cluster_id`` only to summary nodes (``raptor_level=1``); leaf/child chunks
(``raptor_level=0``) never carry it (0 of 10,560 raptor_level=0 points have a
matching ``cluster_id``, vs 656 of 3,473 raptor_level=1 points). The
grouped/leaf retrieval path (``rag/nodes/retrieval.py``'s ``chunk_task``)
queries ``raptor_level=0`` *and* filters on ``cluster_ids`` selected by tree
navigation in the same ``must`` filter -- an impossible intersection that
starves both the grouped ``query_points_groups`` call and its flat
``query_points`` fallback down to zero candidates, which is what the "0
groups / 0 hits" warning in ``QdrantSearcher.search`` was actually reporting.
"""

from unittest.mock import MagicMock, create_autospec

from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Prefetch

from services.qdrant.searcher import QdrantSearcher


def _cluster_condition_present(prefetch_list: list[Prefetch]) -> bool:
    for pf in prefetch_list:
        must = pf.filter.must if pf.filter and pf.filter.must else []
        for cond in must:
            if isinstance(cond, FieldCondition) and cond.key == "cluster_id":
                return True
    return False


def _autospec_client_with_empty_groups() -> QdrantClient:
    client = create_autospec(QdrantClient, instance=True)
    client.query_points_groups.return_value = MagicMock(groups=[])
    client.query_points.return_value = MagicMock(points=[])
    return client


def test_leaf_chunk_search_does_not_filter_by_cluster_id():
    """raptor_level=0 (leaf chunks) must not receive a cluster_id filter --
    no leaf chunk in the corpus has one, so it always zeroes the candidate set.
    """
    client = _autospec_client_with_empty_groups()
    searcher = QdrantSearcher(client, "test_collection")

    searcher.search(
        query_vector=[0.1] * 1024,
        limit=5,
        sparse_vector={1: 0.5},
        raptor_level=0,
        group_by="parent_id",
        cluster_ids=[0, 30, 42],
    )

    assert client.query_points_groups.called
    prefetch = client.query_points_groups.call_args.kwargs["prefetch"]
    assert not _cluster_condition_present(prefetch), (
        "cluster_id filter must be dropped for raptor_level=0 (leaf chunk) "
        "searches -- it is never populated there and silently empties the "
        "candidate set."
    )


def test_summary_search_still_filters_by_cluster_id():
    """raptor_level=1 (RAPTOR summary nodes) genuinely carry cluster_id, so
    the filter must still be applied there -- this guards against a lazy
    "just drop cluster_ids everywhere" fix.
    """
    client = _autospec_client_with_empty_groups()
    searcher = QdrantSearcher(client, "test_collection")

    searcher.search(
        query_vector=[0.1] * 1024,
        limit=5,
        sparse_vector={1: 0.5},
        raptor_level=1,
        cluster_ids=[0, 30, 42],
    )

    assert client.query_points.called
    prefetch = client.query_points.call_args.kwargs["prefetch"]
    assert _cluster_condition_present(prefetch)


if __name__ == "__main__":
    test_leaf_chunk_search_does_not_filter_by_cluster_id()
    test_summary_search_still_filters_by_cluster_id()
    print("OK")
