"""Ranking helpers shared across RAG services.

The Reciprocal Rank Fusion implementation here lives in a service module so that
RAG nodes do not accumulate ranking logic.  Keys stay as their original type
(typically integer ids from `id(doc)`); callers must not coerce them.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TypeVar

T = TypeVar("T")


def _reciprocal_rank_fusion(rankings: list[list[T]], k: int = 60) -> list[T]:
    """Fuse multiple ranked lists using Reciprocal Rank Fusion.

    Formula::

        RRF_Score(d) = sum_{r in rankings} 1 / (k + rank_r(d))

    Args:
        rankings: Ranked lists of item keys/ids.  Order within each list is the
            rank (first item = rank 1).
        k: RRF constant that dampens the impact of low ranks.

    Returns:
        Keys sorted by descending fused score.
    """
    scores: defaultdict[T, float] = defaultdict(float)

    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] += 1.0 / (k + rank)

    sorted_items = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [key for key, _ in sorted_items]


if __name__ == "__main__":
    # Self-check: integer keys must remain integers and shared hit 103 outranks 102/104.
    vector = [101, 102, 103]
    graph = [103, 101, 104]
    fused = _reciprocal_rank_fusion([vector, graph], k=60)
    assert all(isinstance(key, int) for key in fused), "keys must stay integers"
    assert fused.index(103) < fused.index(102), "shared id 103 should outrank single-list 102"
    assert fused.index(101) < fused.index(104), "dual-list 101 should outrank single-list 104"
    print("rankers.py self-check passed:", fused)
