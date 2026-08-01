"""Regression tests for the Phase-3 cross-config retrieval gate.

The legacy gate (``cross_avg > same-model avg + 0.02``) had two defects:

1. QUERY-only drift fired it as a false positive: a changed query embedding
   lowers the same-model overlap while the shared-query overlap stays high.
2. PASSAGE-only drift slipped through as a false negative: both averages drop
   together, so the delta never exceeds 0.02.

The replacement ``_evaluate_cross_config`` compares the shared-query passage
overlap against the calibrated Phase-3 baseline (>= 0.85) and fails only when
passage embeddings actually diverge. These tests pin that behaviour on
synthetic corpora so the gate cannot regress.
"""

from __future__ import annotations

import numpy as np
import pytest

import scripts.validate_onnx_retrieval as retrieval


def _random_vectors(n: int, dim: int = 64, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.normal(size=(n, dim))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    return v


def test_cross_config_overlap_identical_corpora_is_one():
    corpus = _random_vectors(50)
    q = _random_vectors(1, seed=1)[0]
    overlap = retrieval._cross_config_overlap(q, corpus, corpus, k=10)
    assert overlap == pytest.approx(1.0)
    assert retrieval._evaluate_cross_config(overlap) is True


def test_query_only_drift_does_not_trigger_gate():
    corpus = _random_vectors(50)
    q1 = _random_vectors(1, seed=1)[0]
    q2 = _random_vectors(1, seed=2)[0]
    o1 = retrieval._cross_config_overlap(q1, corpus, corpus)
    o2 = retrieval._cross_config_overlap(q2, corpus, corpus)
    assert o1 == pytest.approx(o2) == pytest.approx(1.0)
    assert retrieval._evaluate_cross_config(o1) is True


def test_passage_drift_triggers_gate():
    corpus = _random_vectors(50)
    q = _random_vectors(1, seed=3)[0]
    perturbed = corpus.copy()
    rng = np.random.default_rng(4)
    perturbed = perturbed + 0.5 * rng.normal(size=corpus.shape)
    perturbed /= np.linalg.norm(perturbed, axis=1, keepdims=True)
    overlap = retrieval._cross_config_overlap(q, corpus, perturbed)
    assert overlap < retrieval.OVERLAP_THRESHOLD
    assert retrieval._evaluate_cross_config(overlap) is False


def test_legacy_false_positive_scenario_now_passes():
    # Same-model overlap low (query drift), shared-query overlap high (passage
    # corpora agree). The legacy gate failed on this; the baseline gate passes.
    low_same_model_avg = 0.5
    high_cross_avg = 1.0
    assert high_cross_avg > low_same_model_avg + 0.02
    assert retrieval._evaluate_cross_config(high_cross_avg) is True


def test_evaluate_cross_config_respects_threshold():
    assert retrieval._evaluate_cross_config(0.90) is True
    assert retrieval._evaluate_cross_config(0.85) is True
    assert retrieval._evaluate_cross_config(0.84) is False
