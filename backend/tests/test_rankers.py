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
