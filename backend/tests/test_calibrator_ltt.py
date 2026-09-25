"""Fixed-sequence (Learn-then-Test) selection tests for SelectiveRiskCalibrator.

The old `find_operating_threshold` collected every threshold whose UCB passed
and picked the max-coverage one -- an uncorrected multiple-testing procedure
that voids the (1 - delta) confidence guarantee. These tests pin the
fixed-sequence replacement: walk thresholds highest-to-lowest, stop at the
first UCB failure, return the last point that passed.
"""

from __future__ import annotations

from evaluation.gold.calibrator import SelectiveRiskCalibrator
from evaluation.gold.metrics import clopper_pearson_upper


def _min_n_for_k_errors(k_errors: int, target: float = 0.01, delta: float = 0.05) -> int:
    n = k_errors + 1
    while clopper_pearson_upper(k_errors=k_errors, n_total=n, delta=delta) > target:
        n += 1
    return n


def test_fixed_sequence_stops_at_first_failure_not_max_coverage():
    """Level 1 (top scores) passes; level 2 (mid scores) fails by adding one
    error into a still-small n; level 3 (bottom scores) would pass AGAIN
    because n grows large enough to absorb that same single error -- the old
    max-coverage-among-all-valid-points code would pick level 3 (highest
    coverage); fixed-sequence must stop at level 2's failure and return
    level 1.
    """
    target_risk, delta = 0.01, 0.05

    n1 = 299  # 0 errors, verified in metrics.py self-check: ucb(0, 299) <= 0.01
    n2_extra = 10  # cumulative n=309, 1 error -> ucb(1, 309) > 0.01 (verified below)
    min_n_k1 = _min_n_for_k_errors(1, target_risk, delta)
    n3_extra = (min_n_k1 + 5) - (n1 + n2_extra)  # enough extra correct items to pass again

    assert clopper_pearson_upper(k_errors=0, n_total=n1, delta=delta) <= target_risk
    assert clopper_pearson_upper(k_errors=1, n_total=n1 + n2_extra, delta=delta) > target_risk
    assert clopper_pearson_upper(k_errors=1, n_total=min_n_k1 + 5, delta=delta) <= target_risk

    scores = (
        [3.0] * n1
        + [2.0] * n2_extra
        + [1.0] * n3_extra
    )
    labels = (
        [1] * n1
        + [0] + [1] * (n2_extra - 1)  # 1 error at level 2
        + [1] * n3_extra  # no new errors at level 3
    )

    calibrator = SelectiveRiskCalibrator(scores=scores, labels=labels)
    curve = calibrator.compute_precision_coverage_curve(delta=delta)

    # Sanity: prove the trap is real -- a later (lower-threshold) point does
    # pass again, so a max-coverage-among-all-valid-points selector would
    # pick it.
    by_threshold = {p["threshold"]: p for p in curve}
    assert by_threshold[3.0]["ucb_risk"] <= target_risk
    assert by_threshold[2.0]["ucb_risk"] > target_risk
    assert by_threshold[1.0]["ucb_risk"] <= target_risk
    assert by_threshold[1.0]["coverage"] > by_threshold[3.0]["coverage"]

    result = calibrator.find_operating_threshold(target_risk=target_risk, delta=delta)
    assert result is not None
    assert result["threshold"] == 3.0
    assert result["n_selected"] == n1


def test_highest_threshold_failing_returns_none():
    scores = [5.0, 4.0]
    labels = [0, 1]  # top threshold (5.0) already has 1 error in 1 sample -> ucb == 1.0

    calibrator = SelectiveRiskCalibrator(scores=scores, labels=labels)
    result = calibrator.find_operating_threshold(target_risk=0.01, delta=0.05)
    assert result is None


def test_to_profile_round_trips_keys_and_raises_on_risk_violation():
    scores = [3.0] * 299 + [1.0] * 5
    labels = [1] * 299 + [0] * 5

    calibrator = SelectiveRiskCalibrator(scores=scores, labels=labels)
    point = calibrator.find_operating_threshold(target_risk=0.01, delta=0.05)
    assert point is not None

    profile = calibrator.to_profile(point, collection="okf_quotes", target_risk=0.01)
    assert profile["threshold"] == point["threshold"]
    assert profile["score_kind"] == "dense_cosine"
    assert profile["n"] == calibrator.n
    assert profile["n_selected"] == point["n_selected"]
    assert profile["coverage"] == point["coverage"]
    assert profile["precision"] == point["precision"]
    assert profile["ucb_risk"] == point["ucb_risk"]
    assert profile["target_risk"] == 0.01
    assert profile["collection"] == "okf_quotes"
    assert "fitted_at" in profile and profile["fitted_at"]

    failing_point = {**point, "ucb_risk": 0.5}
    try:
        calibrator.to_profile(failing_point, collection="okf_quotes", target_risk=0.01)
        assert False, "expected ValueError for ucb_risk > target_risk"
    except ValueError:
        pass


def test_sample_size_boundary_299_vs_298():
    """The walk starts at the first threshold selecting n_min items -- the
    smallest n whose zero-error Clopper-Pearson bound can clear the target.
    That start depends only on score ranks, never on labels, so fixed-sequence
    validity holds. Without it, distinct scores put a 1-item threshold first
    (UCB 0.95) and the calibrator could never pass on real data.
    """
    assert clopper_pearson_upper(k_errors=0, n_total=299, delta=0.05) <= 0.01
    assert clopper_pearson_upper(k_errors=0, n_total=298, delta=0.05) > 0.01

    result_299 = SelectiveRiskCalibrator([float(i) for i in range(299, 0, -1)], [1] * 299).find_operating_threshold(
        target_risk=0.01, delta=0.05
    )
    assert result_299 is not None and result_299["n_selected"] == 299

    result_298 = SelectiveRiskCalibrator([float(i) for i in range(298, 0, -1)], [1] * 298).find_operating_threshold(
        target_risk=0.01, delta=0.05
    )
    assert result_298 is None


def test_error_below_the_start_point_still_stops_the_walk():
    """299 correct top items then a run of errors: the walk passes at n=299 and
    must stop at the first failing lower threshold, keeping the 299 point."""
    scores = [float(i) for i in range(400, 0, -1)]
    labels = [1] * 299 + [0] * 101
    result = SelectiveRiskCalibrator(scores, labels).find_operating_threshold(target_risk=0.01, delta=0.05)
    assert result is not None and result["n_selected"] == 299
