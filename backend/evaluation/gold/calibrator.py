"""
Mukthi Guru — Selective Risk Calibrator (Section 5.6)

Calibrates retrieval confidence scores with Selective Risk Guarantees (SGR / Geifman et al.).
Finds the operating threshold where the 95% Clopper-Pearson upper confidence bound
on error is <= target_risk (e.g. 1% risk -> >= 99% precision).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from evaluation.gold.metrics import clopper_pearson_upper

logger = logging.getLogger(__name__)


class SelectiveRiskCalibrator:
    """
    Fits selective classification thresholds on validation data to guarantee
    bounded error rates (precision >= 1 - target_risk) with statistical confidence (1 - delta).
    """

    def __init__(self, scores: list[float], labels: list[int]) -> None:
        """
        Args:
            scores: Model prediction confidence scores (higher = more confident).
            labels: Ground truth binary labels (1 = correct/relevant, 0 = wrong/irrelevant).
        """
        if len(scores) != len(labels):
            raise ValueError(f"Length mismatch: {len(scores)} scores vs {len(labels)} labels")
        if not scores:
            raise ValueError("Cannot calibrate on empty dataset")

        self.data = sorted(zip(scores, labels), key=lambda x: x[0], reverse=True)
        self.n = len(self.data)

    def compute_precision_coverage_curve(
        self,
        delta: float = 0.05,
    ) -> list[dict[str, Any]]:
        """
        Compute precision, coverage, and Clopper-Pearson upper bound on risk across thresholds.
        """
        curve: list[dict[str, Any]] = []

        total_correct = 0
        total_selected = 0

        # Evaluate at unique score thresholds
        unique_scores = sorted(set(s for s, _ in self.data), reverse=True)

        for s_thresh in unique_scores:
            selected = [(s, y) for s, y in self.data if s >= s_thresh]
            k = len(selected)
            if k == 0:
                continue

            errors = sum(1 for _, y in selected if y == 0)
            coverage = k / self.n
            precision = (k - errors) / k
            ucb_risk = clopper_pearson_upper(k_errors=errors, n_total=k, delta=delta)

            curve.append({
                "threshold": round(s_thresh, 4),
                "n_selected": k,
                "coverage": round(coverage, 4),
                "precision": round(precision, 4),
                "empirical_risk": round(errors / k, 4),
                "ucb_risk": round(ucb_risk, 4),
                "guaranteed_precision_lower": round(1.0 - ucb_risk, 4),
            })

        return curve

    def find_operating_threshold(
        self,
        target_risk: float = 0.01,  # 1% error rate -> 99% precision
        delta: float = 0.05,        # 95% one-sided confidence
    ) -> Optional[dict[str, Any]]:
        """
        Fixed-sequence testing (Learn-then-Test; Geifman & El-Yaniv 2017,
        "Selective Classification for Deep Neural Networks"; Angelopoulos
        et al. 2021, "Learn Then Test: Calibrating Predictive Algorithms to
        Achieve Risk Control"): walk thresholds from HIGHEST to LOWEST score
        in that single, pre-declared order and stop at the FIRST threshold
        whose Clopper-Pearson UCB on risk exceeds target_risk. Return the
        last threshold that passed (the lowest threshold before that first
        failure), or None if even the highest threshold fails.

        This is valid without a multiple-testing correction because exactly
        one threshold is ever the "test" -- the walk halts at the first
        failure instead of evaluating every threshold and cherry-picking
        the best passer, which is what the previous implementation did
        (collect every threshold whose UCB happened to pass, keep the
        max-coverage one). That is an uncorrected multiple-comparisons
        procedure and voids the (1 - delta) confidence guarantee: with
        enough thresholds tested, some non-adjacent lower threshold passing
        its own UCB check by chance is expected, not evidence the whole
        interval down to it is safe.
        """
        curve = self.compute_precision_coverage_curve(delta=delta)  # highest threshold first
        # Start at the first threshold that selects n_min items: below n_min even a
        # zero-error set cannot clear the bound, so testing it only ends the walk
        # early (a 1-item top threshold has UCB 0.95). n_selected depends on score
        # ranks alone, never labels, so this pre-declared start keeps LTT valid.
        n_min = self._min_selected_for(target_risk, delta)

        best_point: Optional[dict[str, Any]] = None
        for point in curve:
            if point["n_selected"] < n_min:
                continue
            if point["ucb_risk"] > target_risk:
                break
            best_point = point

        if best_point is None:
            logger.warning(
                f"[Calibrator] No operating point found satisfying UCB risk <= {target_risk}. "
                f"Requires larger sample size (n >= 299 for 0 errors, n >= 628 for 2 errors)."
            )
        return best_point

    def _min_selected_for(self, target_risk: float, delta: float) -> int:
        """Smallest n whose zero-error Clopper-Pearson upper bound is <= target_risk
        (299 at 1% / 95%), capped at the calibration set size."""
        n = 1
        while n <= self.n and clopper_pearson_upper(k_errors=0, n_total=n, delta=delta) > target_risk:
            n += 1
        return n

    def to_profile(
        self,
        point: dict[str, Any],
        collection: str,
        target_risk: float = 0.01,
        score_kind: str = "dense_cosine",
    ) -> dict[str, Any]:
        """
        Serialize an operating point (as returned by find_operating_threshold)
        into the profile dict the serving route thresholds on at request time.

        The threshold is only meaningful applied against the SAME quantity it
        was fit on -- top-1 dense cosine similarity, `score_kind="dense_cosine"`,
        not a fused/reranked/sparse score -- and `point`'s underlying labels
        must be human-adjudicated per the B1 gold-set protocol
        (docs/agent/B1_gold_set_protocol.md), never silver/LLM labels; the 1%
        risk guarantee this profile encodes is void under silver labels.

        Raises ValueError if `point["ucb_risk"] > target_risk` -- a caller
        must never ship a profile whose own risk bound fails its own target.
        """
        if point["ucb_risk"] > target_risk:
            raise ValueError(
                f"Refusing to profile operating point with ucb_risk={point['ucb_risk']} "
                f"> target_risk={target_risk}"
            )
        return {
            "threshold": point["threshold"],
            "score_kind": score_kind,
            "n": self.n,
            "n_selected": point["n_selected"],
            "coverage": point["coverage"],
            "precision": point["precision"],
            "ucb_risk": point["ucb_risk"],
            "target_risk": target_risk,
            "collection": collection,
            "fitted_at": datetime.now(timezone.utc).isoformat(),
        }
