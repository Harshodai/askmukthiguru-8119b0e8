"""Agentic Corrective RAG (CRAG) Tri-Band Evaluator & RRF Tuning.

Implements the deterministic tri-band confidence routing contract:
1. Band 1: SERVE_VERBATIM (Score >= 0.78)
   High-confidence retrieval; genuine Sri Preethaji / Sri Krishnaji verbatim
   discourse or meditation passage is served directly.
2. Band 2: ATMA_VICHARA_REFLECTION (0.45 <= Score < 0.78)
   Ambiguous or borderline spiritual queries; rather than synthesizing ungrounded
   advice or hallucinating teachings, routes to Atma Vichara (self-inquiry)
   meditative reflection, inviting the seeker to observe inner states without advice.
3. Band 3: ABSTAIN (Score < 0.45)
   Low-confidence retrieval; fails closed with honest abstention.

Confidence Metric:
    confidence = 0.7 * top_score + 0.3 * margin
where:
    top_score in [0.0, 1.0] is the top candidate's dense/similarity score, and
    margin in [0.0, 1.0] is the margin between top-1 and bottom candidate in top-k
    (or self-margin for single candidate).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_HIGH_THRESHOLD: float = 0.78
DEFAULT_LOW_THRESHOLD: float = 0.45
DEFAULT_RRF_K_TUNED: int = 30  # Optimized for small candidate pools K in [30, 100]


class CRAGAction(str, Enum):
    """Deterministic routing actions for Corrective RAG."""

    SERVE_VERBATIM = "SERVE_VERBATIM"
    ATMA_VICHARA_REFLECTION = "ATMA_VICHARA_REFLECTION"
    ABSTAIN = "ABSTAIN"


# Canonical alias for compatibility
CRAGDecision = CRAGAction


# Authentic Sri Preethaji & Sri Krishnaji contemplative self-inquiry reflections
_ATMA_VICHARA_INQUIRIES: tuple[str, ...] = (
    (
        "When this question arises within you, what is the underlying emotion or disturbance? "
        "Can you observe it as a physical sensation in the body, without naming or judging it?"
    ),
    (
        "Notice the movement of the mind right now: is it resisting what is, or seeking an escape? "
        "What happens when you stay with the feeling as it is, without a story?"
    ),
    (
        "Are you experiencing this challenge from a Beautiful State of connection, or from the "
        "loneliness of the self-centered mind? Can you simply witness the observer?"
    ),
    (
        "In the teachings of Sri Preethaji and Sri Krishnaji, suffering dissolves not through answers, "
        "but through total awareness of the inner state. What is arising in you at this very moment?"
    ),
)


@dataclass(frozen=True)
class CRAGEvaluationResult:
    """Outcome of CRAG tri-band evaluation."""

    decision: CRAGAction
    confidence_score: float
    dense_score: float
    margin: float
    high_threshold: float
    low_threshold: float
    reflection_inquiry: Optional[str] = None
    reason: str = ""
    top_candidate: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    selected_candidates: list[dict[str, Any]] = field(default_factory=list)
    query: str = ""

    @property
    def action(self) -> CRAGAction:
        return self.decision

    @property
    def confidence(self) -> float:
        return self.confidence_score

    @property
    def top_score(self) -> float:
        return self.dense_score

    @property
    def tau_upper(self) -> float:
        return self.high_threshold

    @property
    def tau_lower(self) -> float:
        return self.low_threshold

    @property
    def reflection_prompt(self) -> Optional[str]:
        return self.reflection_inquiry


class CRAGEvaluator:
    """Evaluates candidate evidence passages and routes to appropriate response modality."""

    def __init__(
        self,
        high_threshold: float = DEFAULT_HIGH_THRESHOLD,
        low_threshold: float = DEFAULT_LOW_THRESHOLD,
        dense_weight: float = 0.7,
        margin_weight: float = 0.3,
        rrf_k: int = DEFAULT_RRF_K_TUNED,
    ) -> None:
        if not (0.0 <= low_threshold <= high_threshold <= 1.0):
            raise ValueError(
                f"Invalid thresholds: 0.0 <= low ({low_threshold}) <= high ({high_threshold}) <= 1.0 required"
            )
        if abs((dense_weight + margin_weight) - 1.0) > 1e-6:
            raise ValueError(
                f"Weights must sum to 1.0 (dense_weight={dense_weight}, margin_weight={margin_weight})"
            )

        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.dense_weight = dense_weight
        self.margin_weight = margin_weight
        self.rrf_k = rrf_k

    def calculate_confidence(
        self,
        top_score: float,
        bottom_score: Optional[float] = None,
        second_score: Optional[float] = None,
    ) -> tuple[float, float, float]:
        """Compute (confidence_score, normalized_top, margin).

        Formula: confidence = 0.7 * top_score + 0.3 * margin
        where margin is top_score - bottom_score (or second_score if specified).
        """
        s_dense = max(0.0, min(1.0, float(top_score)))
        b_score = bottom_score if bottom_score is not None else second_score

        if top_score <= 0.0:
            return 0.0, 0.0, 0.0

        if b_score is not None:
            s_bottom = max(0.0, min(1.0, float(b_score)))
            margin = max(0.0, min(1.0, s_dense - s_bottom))
        else:
            margin = s_dense  # Single candidate gets self-margin

        confidence = round((self.dense_weight * s_dense) + (self.margin_weight * margin), 6)
        confidence = max(0.0, min(1.0, confidence))
        return confidence, s_dense, margin

    def evaluate_candidates(
        self,
        candidates: Sequence[dict[str, Any]],
        query: str = "",
        tau_upper: Optional[float] = None,
        tau_lower: Optional[float] = None,
    ) -> CRAGEvaluationResult:
        """Evaluate a list of candidate passages."""
        hi_thresh = self.high_threshold if tau_upper is None else tau_upper
        lo_thresh = self.low_threshold if tau_lower is None else tau_lower

        if not candidates:
            return CRAGEvaluationResult(
                decision=CRAGAction.ABSTAIN,
                confidence_score=0.0,
                dense_score=0.0,
                margin=0.0,
                high_threshold=hi_thresh,
                low_threshold=lo_thresh,
                reason="No candidate passages provided",
                query=query,
                selected_candidates=[],
            )

        def _extract_score(c: dict[str, Any]) -> float:
            for key in ("dense_score", "score", "similarity", "cosine_similarity"):
                val = c.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
            return 0.0

        top_score = _extract_score(candidates[0])
        bottom_score = _extract_score(candidates[-1]) if len(candidates) > 1 else None

        return self.evaluate_scores(
            top_score=top_score,
            bottom_score=bottom_score,
            top_candidate=candidates[0] if candidates else None,
            selected_candidates=list(candidates),
            query=query,
            tau_upper=hi_thresh,
            tau_lower=lo_thresh,
        )

    def evaluate_scores(
        self,
        top_score: float,
        bottom_score: Optional[float] = None,
        second_score: Optional[float] = None,
        top_candidate: Optional[dict[str, Any]] = None,
        selected_candidates: Optional[list[dict[str, Any]]] = None,
        query: str = "",
        tau_upper: Optional[float] = None,
        tau_lower: Optional[float] = None,
    ) -> CRAGEvaluationResult:
        """Evaluate raw scores and return tri-band routing decision."""
        hi_thresh = self.high_threshold if tau_upper is None else tau_upper
        lo_thresh = self.low_threshold if tau_lower is None else tau_lower

        confidence, s_dense, margin = self.calculate_confidence(
            top_score=top_score,
            bottom_score=bottom_score,
            second_score=second_score,
        )

        candidates_out = (
            selected_candidates
            if selected_candidates is not None
            else ([top_candidate] if top_candidate else [])
        )

        if confidence >= hi_thresh:
            return CRAGEvaluationResult(
                decision=CRAGAction.SERVE_VERBATIM,
                confidence_score=round(confidence, 4),
                dense_score=round(s_dense, 4),
                margin=round(margin, 4),
                high_threshold=hi_thresh,
                low_threshold=lo_thresh,
                reason=f"Confidence {confidence:.4f} >= {hi_thresh:.2f} (Band 1: Verbatim Serving)",
                top_candidate=top_candidate,
                selected_candidates=candidates_out,
                query=query,
            )

        if confidence >= lo_thresh:
            idx = abs(hash(query.strip().lower())) % len(_ATMA_VICHARA_INQUIRIES) if query else 0
            reflection = _ATMA_VICHARA_INQUIRIES[idx]

            return CRAGEvaluationResult(
                decision=CRAGAction.ATMA_VICHARA_REFLECTION,
                confidence_score=round(confidence, 4),
                dense_score=round(s_dense, 4),
                margin=round(margin, 4),
                high_threshold=hi_thresh,
                low_threshold=lo_thresh,
                reflection_inquiry=reflection,
                reason=(
                    f"Confidence {confidence:.4f} in [{lo_thresh:.2f}, {hi_thresh:.2f}) "
                    "(Band 2: Atma Vichara Self-Inquiry)"
                ),
                top_candidate=top_candidate,
                selected_candidates=candidates_out,
                query=query,
            )

        return CRAGEvaluationResult(
            decision=CRAGAction.ABSTAIN,
            confidence_score=round(confidence, 4),
            dense_score=round(s_dense, 4),
            margin=round(margin, 4),
            high_threshold=hi_thresh,
            low_threshold=lo_thresh,
            reason=f"Confidence {confidence:.4f} < {lo_thresh:.2f} (Band 3: Abstention)",
            top_candidate=top_candidate,
            selected_candidates=[],
            query=query,
        )


def evaluate_candidates(
    candidates: Sequence[dict[str, Any]],
    query: str = "",
    tau_upper: float = DEFAULT_HIGH_THRESHOLD,
    tau_lower: float = DEFAULT_LOW_THRESHOLD,
) -> CRAGEvaluationResult:
    """Evaluate candidates using CRAG Tri-Band confidence evaluator."""
    evaluator = CRAGEvaluator(high_threshold=tau_upper, low_threshold=tau_lower)
    return evaluator.evaluate_candidates(candidates, query=query)


def compute_rrf_tuned(rankings: Sequence[Sequence[T]], k: int = DEFAULT_RRF_K_TUNED) -> list[T]:
    """Reciprocal Rank Fusion with tuned k (default k=30).

    For small candidate sets (K in [30, 100]), k=30 provides steeper score separation
    between top ranks compared to classical k=60, preventing dilution of the best
    verbatim discourse matches.
    """
    from collections import defaultdict

    scores: defaultdict[T, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] += 1.0 / (k + rank)

    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [item for item, _ in sorted_items]
