"""BGE-M3 ColBERT MaxSim scorer (pure NumPy, no classes, no state).

Contract: callers MUST slice off the CLS token before passing arrays
(matching FlagEmbedding's `colbert_vecs[:tokens_num - 1]`). Both query
and doc embeddings must be L2-normalized per token (BGE-M3 default).
"""
from __future__ import annotations
import logging
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

_MIN_DOC_TOKENS = 10


def maxsim_score(
    query_embeddings: np.ndarray,
    doc_embeddings: np.ndarray,
    doc_mask: Optional[np.ndarray] = None,
) -> float:
    """BGE-M3 MaxSim: s = (1/N) * mean_i max_j E_q[i] · E_p[j]^T.

    Args:
        query_embeddings: [n_q, 1024] L2-normalized query token embeddings (CLS already excluded by caller).
        doc_embeddings: [n_d, 1024] L2-normalized doc token embeddings (CLS already excluded by caller).
        doc_mask: optional [n_d] boolean mask, True = valid token. If provided and valid tokens < _MIN_DOC_TOKENS, returns 0.0.

    Returns:
        float MaxSim score (mean of per-query-token max similarities to doc tokens).
    """
    if query_embeddings.size == 0 or query_embeddings.shape[0] == 0:
        return 0.0
    if doc_embeddings.size == 0 or doc_embeddings.shape[0] == 0:
        return 0.0
    if doc_mask is not None and int(doc_mask.sum()) < _MIN_DOC_TOKENS:
        return 0.0

    q = np.ascontiguousarray(query_embeddings, dtype=np.float32)
    d = np.ascontiguousarray(doc_embeddings, dtype=np.float32)

    sim = np.dot(q, d.T)
    if sim.ndim == 1:
        sim = sim.reshape(-1, 1)

    if doc_mask is not None:
        invalid = ~np.asarray(doc_mask, dtype=bool)
        if invalid.any():
            sim[:, invalid] = -np.inf

    per_token_max = sim.max(axis=1)
    if per_token_max.size == 0:
        return 0.0

    if np.isinf(per_token_max).all():
        return 0.0

    return float(per_token_max.mean())


def batch_maxsim(
    query_embeddings: np.ndarray,
    doc_embeddings_list: list[np.ndarray],
    doc_masks: Optional[list[Optional[np.ndarray]]] = None,
) -> list[float]:
    """Score one query against a batch of docs.

    Args:
        query_embeddings: [n_q, 1024] query token embeddings (CLS excluded).
        doc_embeddings_list: list of [n_d_i, 1024] doc token embeddings (CLS excluded, variable length per doc).
        doc_masks: optional list of masks (one per doc), None entries = no mask for that doc.

    Returns:
        list[float] scores, one per doc, same order as doc_embeddings_list.
    """
    if doc_masks is None:
        doc_masks = [None] * len(doc_embeddings_list)

    scores: list[float] = []
    for doc_emb, mask in zip(doc_embeddings_list, doc_masks):
        scores.append(maxsim_score(query_embeddings, doc_emb, mask))
    return scores


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    dim = 1024

    q = rng.standard_normal((8, dim)).astype(np.float32)
    q = q / np.linalg.norm(q, axis=1, keepdims=True)

    relevant = rng.standard_normal((50, dim)).astype(np.float32)
    relevant[:8] = q + 0.01 * rng.standard_normal((8, dim))
    relevant = relevant / np.linalg.norm(relevant, axis=1, keepdims=True)

    irrelevant = rng.standard_normal((50, dim)).astype(np.float32)
    irrelevant = irrelevant / np.linalg.norm(irrelevant, axis=1, keepdims=True)

    rel_score = maxsim_score(q, relevant)
    irrel_score = maxsim_score(q, irrelevant)
    print(f"relevant score: {rel_score:.4f}")
    print(f"irrelevant score: {irrel_score:.4f}")
    assert rel_score > irrel_score, f"FAIL: relevant ({rel_score}) should beat irrelevant ({irrel_score})"

    # Test mask: put high-sim tokens in the MASKED region, so masking must drop the score.
    # Construct a doc where tokens 0-7 are near-copies of query, then mask those exact tokens.
    relevant_for_mask = rng.standard_normal((50, dim)).astype(np.float32)
    relevant_for_mask[:8] = q + 0.01 * rng.standard_normal((8, dim))  # high-sim at start
    relevant_for_mask = relevant_for_mask / np.linalg.norm(relevant_for_mask, axis=1, keepdims=True)

    # Mask the high-sim tokens (0-7), forcing the max to fall back to the random tokens (low sim)
    mask = np.ones(50, dtype=bool)
    mask[:8] = False  # mask the high-sim region
    masked_score = maxsim_score(q, relevant_for_mask, doc_mask=mask)

    # Unmasked score should be high (high-sim tokens present)
    unmasked_score = maxsim_score(q, relevant_for_mask)
    print(f"unmasked (high-sim at start): {unmasked_score:.4f}")
    print(f"masked (high-sim tokens masked out): {masked_score:.4f}")
    assert unmasked_score > 0.5, f"unmasked should be high (high-sim tokens present), got {unmasked_score}"
    assert masked_score < unmasked_score, f"masking high-sim tokens MUST drop the score, got {masked_score} vs {unmasked_score}"
    assert masked_score < 0.2, f"masked score should be low (only random tokens remain), got {masked_score}"

    # Empty arrays edge cases
    empty_q = np.zeros((0, dim), dtype=np.float32)
    empty_d = np.zeros((0, dim), dtype=np.float32)
    assert maxsim_score(empty_q, relevant) == 0.0, "empty query should return 0.0"
    assert maxsim_score(q, empty_d) == 0.0, "empty doc should return 0.0"
    print("empty arrays: PASS (returns 0.0, not nan)")

    scores = batch_maxsim(q, [relevant, irrelevant])
    print(f"batch scores: {scores}")
    assert scores[0] > scores[1], "batch should rank relevant first"
    assert abs(scores[0] - rel_score) < 1e-6 and abs(scores[1] - irrel_score) < 1e-6, "batch should match single"

    short = rng.standard_normal((3, dim)).astype(np.float32)
    short = short / np.linalg.norm(short, axis=1, keepdims=True)
    short_mask = np.ones(3, dtype=bool)
    short_score = maxsim_score(q, short, doc_mask=short_mask)
    print(f"short doc score: {short_score:.4f}")
    assert short_score == 0.0, "docs with < _MIN_DOC_TOKENS valid tokens should return 0.0"

    print("PASS — MaxSim scorer ranks relevant > irrelevant, mask works, batch matches single, degenerate guarded, empty arrays guarded")