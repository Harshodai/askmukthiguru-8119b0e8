"""Pin the measured retrieval settings so a later edit has to re-measure.

Measured 2026-09-12 against a fixed 60-question golden set drawn from the live
collection (scripts/eval/retrieval_golden_baseline.py):

    prefetch 1.0 -> 3.0 (k=10):  R@1 0.433->0.517, MRR 0.602->0.646, nDCG 0.660->0.693
    depth  12 -> 24 (prefetch 3): recall 0.850 -> 0.917 (saturates at 24)

These are not arbitrary constants; lowering them measurably costs retrieval
quality, and raising them past the measured saturation costs latency for
nothing.
"""

from app.config import Settings


def test_prefetch_multipliers_are_the_measured_optimum():
    s = Settings()
    assert s.qdrant_dense_prefetch_multiplier == 3.0
    assert s.qdrant_sparse_prefetch_multiplier == 3.0


def test_retrieval_depth_reaches_recall_saturation():
    assert Settings().rag_top_k_retrieval == 24


def test_rerank_still_narrows_the_candidate_set():
    s = Settings()
    assert s.rag_top_k_rerank < s.rag_top_k_retrieval, (
        "retrieval depth exists to give the reranker choices; if rerank is not "
        "narrower the extra depth is pure latency"
    )
