from services.rrf_ranker import RRFRanker, reciprocal_rank_fusion


def test_rrf_merges_rankings():
    vector_results = ["doc1", "doc2", "doc3"]
    graph_results = ["doc3", "doc1", "doc4"]
    fused = reciprocal_rank_fusion([vector_results, graph_results], k=60)
    # doc1 (ranks 1 & 2) or doc3 (ranks 3 & 1) should be first
    assert fused[0] in ("doc1", "doc3")
    assert len(fused) == 4


def test_rrf_single_ranking():
    results = ["a", "b", "c"]
    fused = reciprocal_rank_fusion([results])
    assert fused == ["a", "b", "c"]


def test_rrf_class_wrapper():
    ranker = RRFRanker(k=60)
    rankings = [["a", "b"], ["b", "c"]]
    result = ranker.fuse(rankings)
    assert len(result) == 3
    assert set(result) == {"a", "b", "c"}