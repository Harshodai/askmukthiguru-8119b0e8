"""Exact Statistical Bounds & Clustered Bootstrap for RAG Evaluation — Invariant B3.

Provides exact Clopper-Pearson confidence bounds for precision claims (>= 99%)
and clustered bootstrap resampling by video_id to account for intra-source correlation.

Mathematical Foundation:
- Wald intervals catastrophically collapse to 0 variance when p -> 1.0 (true coverage ~82% vs nominal 95%).
- Clopper-Pearson provides exact finite-sample conservative lower bounds via the Beta distribution.
  This is the bound that can actually CERTIFY a <=1% error-rate claim at 95% confidence: 299
  answers with 0 errors, or 628 answers with up to 2 errors (see min_sample_size_for_precision).
- Clustered bootstrap eliminates the 35% standard error underestimation caused by intra-video
  correlation, but it is for COMPARISONS only (e.g. "did this change help?"), not certification:
  when every item in the sample passes, its resampled distribution collapses to a point mass at
  1.0, so `one_sided_lower` is also 1.0 regardless of sample size -- it cannot express the
  uncertainty a small all-passing sample actually has, and must not be quoted as a certified bound.
"""

from __future__ import annotations

import numpy as np
import scipy.stats as stats
from typing import Any


def clopper_pearson_lower_bound(
    k: int,
    n: int,
    confidence: float = 0.95,
) -> float:
    """
    Exact one-sided Clopper-Pearson lower confidence bound.

    Returns the minimum true success rate p consistent with observing k successes
    out of n trials at the given confidence level.
    """
    if n <= 0 or k < 0 or k > n:
        raise ValueError(f"Invalid inputs: k={k}, n={n}")
    if k == 0:
        return 0.0
    alpha = 1.0 - confidence
    # Clopper-Pearson lower bound is BetaQuantile(alpha; k, n - k + 1)
    return float(stats.beta.ppf(alpha, k, n - k + 1))


def clopper_pearson_upper_bound(
    k: int | None = None,
    n: int | None = None,
    confidence: float = 0.95,
    *,
    k_errors: int | None = None,
    n_total: int | None = None,
    delta: float | None = None,
) -> float:
    """
    Exact one-sided Clopper-Pearson upper confidence bound.

    Returns the maximum true failure/error rate consistent with observing k events
    out of n trials at confidence level (1 - delta).
    """
    if k_errors is not None:
        k = k_errors
    if n_total is not None:
        n = n_total
    if delta is not None:
        confidence = 1.0 - delta

    if k is None or n is None:
        raise ValueError("Must provide k and n (or k_errors and n_total)")
    if n <= 0 or k < 0 or k > n:
        raise ValueError(f"Invalid inputs: k={k}, n={n}")
    if k == n:
        return 1.0
    # Upper bound is BetaQuantile(confidence; k + 1, n - k)
    return float(stats.beta.ppf(confidence, k + 1, n - k))


clopper_pearson_upper = clopper_pearson_upper_bound


def min_sample_size_for_precision(
    target_lower_bound: float = 0.99,
    max_failures: int = 2,
    confidence: float = 0.95,
) -> int:
    """Find the minimum sample size n required to establish target precision."""
    for n in range(max_failures + 1, 10000):
        k = n - max_failures
        lb = clopper_pearson_lower_bound(k, n, confidence)
        if lb >= target_lower_bound:
            return n
    return -1


def clustered_bootstrap_ci(
    cluster_ids: list[str],
    successes: list[int],
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Compute clustered bootstrap confidence intervals by resampling whole video clusters.

    Args:
        cluster_ids: list of video_id or source cluster identifiers for each evaluation item.
        successes: binary indicator (1 = pass/verbatim, 0 = fail) for each item.
        n_boot: number of bootstrap iterations (default: 2000).
        confidence: confidence level (default: 0.95).
        seed: random seed for reproducibility.

    Returns:
        dict containing point_estimate, one_sided_lower, two_sided_ci, standard_error, deff.
    """
    if len(cluster_ids) != len(successes):
        raise ValueError("Length mismatch between cluster_ids and successes")
    if not cluster_ids:
        return {"point_estimate": 0.0, "one_sided_lower": 0.0, "total_items": 0}

    rng = np.random.default_rng(seed)
    unique_clusters = np.unique(cluster_ids)
    m_clusters = len(unique_clusters)

    # Pre-aggregate successes and counts per cluster for O(M) resampling
    cluster_succ_map: dict[str, int] = {}
    cluster_total_map: dict[str, int] = {}
    for cid, succ in zip(cluster_ids, successes):
        cluster_succ_map[cid] = cluster_succ_map.get(cid, 0) + int(succ)
        cluster_total_map[cid] = cluster_total_map.get(cid, 0) + 1

    c_succ = np.array([cluster_succ_map[c] for c in unique_clusters], dtype=float)
    c_total = np.array([cluster_total_map[c] for c in unique_clusters], dtype=float)

    total_n = len(successes)
    total_succ = sum(successes)
    point_est = float(total_succ / total_n) if total_n > 0 else 0.0

    # Resample whole clusters with replacement
    boot_estimates = np.empty(n_boot)
    for b in range(n_boot):
        sampled_indices = rng.integers(0, m_clusters, size=m_clusters)
        sum_succ = np.sum(c_succ[sampled_indices])
        sum_total = np.sum(c_total[sampled_indices])
        boot_estimates[b] = sum_succ / sum_total if sum_total > 0 else 0.0

    alpha = 1.0 - confidence
    one_sided_lower = float(np.percentile(boot_estimates, 100 * alpha))
    ci_lower = float(np.percentile(boot_estimates, 100 * (alpha / 2)))
    ci_upper = float(np.percentile(boot_estimates, 100 * (1 - alpha / 2)))
    se_clustered = float(np.std(boot_estimates))

    # Calculate Design Effect (DEFF) relative to naive binomial SE
    se_naive = np.sqrt(point_est * (1.0 - point_est) / total_n) if total_n > 0 else 0.0
    deff = float((se_clustered / se_naive) ** 2) if se_naive > 0 else 1.0

    return {
        "point_estimate": round(point_est, 4),
        "one_sided_lower": round(one_sided_lower, 4),
        "two_sided_ci": [round(ci_lower, 4), round(ci_upper, 4)],
        "std_error": round(se_clustered, 4),
        "deff": round(deff, 2),
        "num_clusters": m_clusters,
        "total_items": total_n,
    }
