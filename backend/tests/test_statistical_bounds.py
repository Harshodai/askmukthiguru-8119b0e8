"""Unit tests for Clopper-Pearson bounds and clustered bootstrap (Invariant B3)."""

import pytest
from evaluation.statistical_bounds import (
    clopper_pearson_lower_bound,
    min_sample_size_for_precision,
    clustered_bootstrap_ci,
)


def test_clopper_pearson_exact_calculation():
    # Zero failures at n=299
    lb_zero = clopper_pearson_lower_bound(k=299, n=299, confidence=0.95)
    assert lb_zero >= 0.9900

    # 2 failures at n=628 (k=626) -> exact verification from subagent research
    lb_two = clopper_pearson_lower_bound(k=626, n=628, confidence=0.95)
    assert lb_two >= 0.9900

    # 2 failures at n=627 (k=625) -> should fail 0.9900 threshold
    lb_under = clopper_pearson_lower_bound(k=625, n=627, confidence=0.95)
    assert lb_under < 0.9900


def test_min_sample_size_for_precision():
    n_for_zero = min_sample_size_for_precision(target_lower_bound=0.99, max_failures=0)
    assert n_for_zero == 299

    n_for_two = min_sample_size_for_precision(target_lower_bound=0.99, max_failures=2)
    assert n_for_two == 628


def test_clustered_bootstrap_ci():
    # 5 clusters, each with 10 questions
    cluster_ids = []
    successes = []
    for c in range(5):
        cid = f"video_{c}"
        for q in range(10):
            cluster_ids.append(cid)
            # cluster 0 has 1 error, others 100%
            successes.append(0 if (c == 0 and q == 0) else 1)

    res = clustered_bootstrap_ci(cluster_ids, successes, n_boot=500, seed=123)
    assert res["point_estimate"] == 49 / 50
    assert 0.90 <= res["one_sided_lower"] <= 0.99
    assert res["num_clusters"] == 5
    assert res["total_items"] == 50
    assert res["deff"] > 0.0
