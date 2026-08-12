"""Tests for shared ranking helpers."""

from services.rankers import _reciprocal_rank_fusion


def test_reciprocal_rank_fusion_preserves_integer_keys():
    vector = [101, 102, 103]
    graph = [103, 101, 104]
    fused = _reciprocal_rank_fusion([vector, graph], k=60)

    assert isinstance(fused, list)
    assert all(isinstance(key, int) for key in fused)
    # 101 and 103 both appear twice; 101 is ranked higher (rank 1 vector, rank 2 graph)
    # so it wins. 103 still outranks single-list ids 102 and 104.
    assert fused.index(101) < fused.index(102)
    assert fused.index(103) < fused.index(104)
    assert 102 in fused
    assert 104 in fused


def test_reciprocal_rank_fusion_empty_rankings():
    assert _reciprocal_rank_fusion([], k=60) == []
    assert _reciprocal_rank_fusion([[]], k=60) == []


def test_reciprocal_rank_fusion_single_list():
    assert _reciprocal_rank_fusion([[3, 1, 2]], k=60) == [3, 1, 2]


def test_stable_document_key_fuses_equivalent_documents_created_in_separate_channels():
    from rag.nodes.utils import _rrf_docs, stable_document_key

    vector_doc = {
        "point_id": "chunk-42",
        "text": "A stable teaching excerpt.",
        "metadata": {"source_id": "video-1", "chunk_index": 4},
        "score": 0.91,
    }
    graph_doc = {
        "point_id": "chunk-42",
        "text": "A stable teaching excerpt.",
        "metadata": {"source_id": "video-1", "chunk_index": 4},
        "score": 0.73,
    }

    assert vector_doc is not graph_doc
    assert stable_document_key(vector_doc) == stable_document_key(graph_doc)
    assert _rrf_docs([[vector_doc], [graph_doc]]) == [vector_doc]


def test_stable_document_key_preserves_distinct_chunks_from_one_source():
    from rag.nodes.utils import _rrf_docs, stable_document_key

    first_chunk = {
        "source_id": "video-1",
        "chunk_index": 4,
        "text": "A repeated teaching excerpt.",
    }
    second_chunk = {
        "source_id": "video-1",
        "chunk_index": 5,
        "text": "A repeated teaching excerpt.",
    }

    assert stable_document_key(first_chunk) != stable_document_key(second_chunk)
    assert _rrf_docs([[first_chunk], [second_chunk]]) == [first_chunk, second_chunk]
