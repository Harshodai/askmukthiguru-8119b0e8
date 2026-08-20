from rag.nodes.reranking import _limit_rerank_candidates


def test_tier2_simple_rerank_input_is_bounded_without_reordering():
    documents = [{"id": index} for index in range(12)]

    selected = _limit_rerank_candidates(documents, "tier2_simple")

    assert len(selected) == 8
    assert selected == documents[:8]


def test_other_tiers_keep_existing_candidate_budget():
    documents = [{"id": index} for index in range(12)]

    assert _limit_rerank_candidates(documents, "standard") is documents
    assert _limit_rerank_candidates(documents, "tier3_complex") is documents
    short_documents = documents[:8]
    assert _limit_rerank_candidates(short_documents, "tier2_simple") is short_documents


if __name__ == "__main__":
    test_tier2_simple_rerank_input_is_bounded_without_reordering()
    test_other_tiers_keep_existing_candidate_budget()
    print("reranking budget checks passed")

