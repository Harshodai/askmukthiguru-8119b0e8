from collections import defaultdict
from typing import TypeVar

T = TypeVar("T")


def reciprocal_rank_fusion(rankings: list[list[T]], k: int = 60) -> list[T]:
    """
    Computes Reciprocal Rank Fusion (RRF) over multiple ranked result sets.

    Formula: RRF_Score(d) = Sum_{r in rankings} 1 / (k + rank_r(d))

    Args:
        rankings: A list of ranked lists of document IDs/keys.
        k: RRF constant (default 60) that dampens the impact of low ranks.

    Returns:
        List of document IDs sorted by fused RRF score (descending).
    """
    scores: defaultdict[str, float] = defaultdict(float)

    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)

    sorted_docs = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [doc_id for doc_id, _ in sorted_docs]


class RRFRanker:
    """
    Standalone Reciprocal Rank Fusion ranker.
    """

    def __init__(self, k: int = 60):
        self.k = k

    def fuse(self, rankings: list[list[str]]) -> list[str]:
        return reciprocal_rank_fusion(rankings, k=self.k)