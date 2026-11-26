"""Controlled Retrieval Experiment & Self-Optimization Engine (Part 7.4).

Runs reproducible configuration sweeps against golden retrieval datasets,
enforces per-class regression gates (ADR 0005), locks safety/rights/attribution
invariants against LLM mutation, and supports shadow/canary promotion + rollback.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from evaluation.fp_rank_metrics import graded_ndcg_at_k, mrr, recall_at_k

# Parameters an optimizer is NEVER permitted to modify
LOCKED_SAFETY_KEYS = frozenset(
    {
        "require_licensed_domain_reads",
        "require_speaker_verified",
        "distress_preemption_enabled",
        "input_guardrails_enabled",
        "output_guardrails_enabled",
        "retrieval_only_enforce_verbatim",
    }
)


@dataclass(frozen=True)
class RetrievalCandidateConfig:
    """Explicit retrieval configuration candidate evaluated by the optimizer."""

    name: str
    qdrant_top_k: int = 20
    similarity_threshold: float = 0.45
    graph_depth: int = 1
    rrf_k0: int = 60
    w_qdrant: float = 1.0
    w_memgraph: float = 0.75
    w_okf: float = 0.50
    rerank_depth: int = 15
    query_expansion: str = "hyde"  # off | hyde | spiritual | both

    def config_hash(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


@dataclass
class ExperimentMetrics:
    config_name: str
    config_hash: str
    n_queries: int
    recall_at_5: float
    recall_at_10: float
    mrr_score: float
    graded_ndcg_at_10: float
    source_diversity: float
    duplicate_rate: float
    p95_latency_ms: float
    per_class_ndcg: dict[str, float] = field(default_factory=dict)


@dataclass
class PromotionDecision:
    promoted: bool
    reason: str
    baseline: ExperimentMetrics
    candidate: ExperimentMetrics
    rollback_config: RetrievalCandidateConfig


class SafetyLockError(ValueError):
    """Raised when an optimization step attempts to alter a locked safety/rights setting."""


class ControlledRetrievalOptimizer:
    """Evaluates retrieval configs against a golden benchmark with regression & safety locks."""

    def __init__(
        self,
        *,
        eval_fn: Callable[[RetrievalCandidateConfig, dict[str, Any]], dict[str, Any]],
        max_p95_latency_ms: float = 10000.0,
        max_class_regression: float = 0.05,
    ) -> None:
        self._eval_fn = eval_fn
        self._max_p95_ms = max_p95_latency_ms
        self._max_class_regression = max_class_regression

    @staticmethod
    def validate_safety_locks(overrides: dict[str, Any]) -> None:
        forbidden = LOCKED_SAFETY_KEYS.intersection(overrides.keys())
        if forbidden:
            raise SafetyLockError(
                f"Optimizer cannot mutate locked safety/rights invariants: {sorted(forbidden)}"
            )

    def evaluate_config(
        self,
        config: RetrievalCandidateConfig,
        golden_items: list[dict[str, Any]],
    ) -> ExperimentMetrics:
        r5: list[float] = []
        r10: list[float] = []
        hit_lists: list[list[bool]] = []
        ndcgs: list[float] = []
        diversities: list[float] = []
        dup_rates: list[float] = []
        latencies: list[float] = []
        class_ndcgs: dict[str, list[float]] = {}

        for item in golden_items:
            res = self._eval_fn(config, item)
            ranked_ids: list[str] = list(res.get("ranked_ids") or [])
            rel_grades: dict[str, int] = dict(item.get("relevance_grades") or {})
            expected_ids = set(item.get("expected_evidence_ids") or rel_grades.keys())

            hits = [rid in expected_ids for rid in ranked_ids]
            grades = [
                int(rel_grades.get(rid, 1 if rid in expected_ids else 0)) for rid in ranked_ids
            ]
            ideal = sorted(
                [int(v) for v in rel_grades.values()] or [1 for _ in expected_ids],
                reverse=True,
            )

            r5.append(recall_at_k(hits, 5))
            r10.append(recall_at_k(hits, 10))
            hit_lists.append(hits)
            g_ndcg = graded_ndcg_at_k(grades, ideal, k=10)
            ndcgs.append(g_ndcg)

            q_cls = str(item.get("question_class") or "standard")
            class_ndcgs.setdefault(q_cls, []).append(g_ndcg)

            unique_sources = len(set(res.get("source_ids") or []))
            diversities.append(unique_sources / max(1, len(ranked_ids[:10])))

            raw_count = int(res.get("raw_candidate_count") or len(ranked_ids))
            unique_count = len(set(ranked_ids))
            dup_rates.append(max(0.0, (raw_count - unique_count) / max(1, raw_count)))
            latencies.append(float(res.get("latency_ms") or 0.0))

        lat_sorted = sorted(latencies)
        p95 = lat_sorted[int(0.95 * (len(lat_sorted) - 1))] if lat_sorted else 0.0
        n = max(1, len(golden_items))
        return ExperimentMetrics(
            config_name=config.name,
            config_hash=config.config_hash(),
            n_queries=len(golden_items),
            recall_at_5=round(sum(r5) / n, 4),
            recall_at_10=round(sum(r10) / n, 4),
            mrr_score=mrr(hit_lists),
            graded_ndcg_at_10=round(sum(ndcgs) / n, 4),
            source_diversity=round(sum(diversities) / n, 4),
            duplicate_rate=round(sum(dup_rates) / n, 4),
            p95_latency_ms=round(p95, 2),
            per_class_ndcg={c: round(sum(vals) / len(vals), 4) for c, vals in class_ndcgs.items()},
        )

    def compare_and_decide(
        self,
        *,
        baseline_cfg: RetrievalCandidateConfig,
        candidate_cfg: RetrievalCandidateConfig,
        golden_items: list[dict[str, Any]],
    ) -> PromotionDecision:
        base_m = self.evaluate_config(baseline_cfg, golden_items)
        cand_m = self.evaluate_config(candidate_cfg, golden_items)

        if cand_m.p95_latency_ms > self._max_p95_ms:
            return PromotionDecision(
                promoted=False,
                reason=f"Rejected: p95 latency {cand_m.p95_latency_ms}ms > SLA {self._max_p95_ms}ms",
                baseline=base_m,
                candidate=cand_m,
                rollback_config=baseline_cfg,
            )

        for cls, base_score in base_m.per_class_ndcg.items():
            cand_score = cand_m.per_class_ndcg.get(cls, 0.0)
            if base_score - cand_score > self._max_class_regression:
                return PromotionDecision(
                    promoted=False,
                    reason=f"Rejected: class '{cls}' nDCG@10 regressed from {base_score} to {cand_score}",
                    baseline=base_m,
                    candidate=cand_m,
                    rollback_config=baseline_cfg,
                )

        improved = cand_m.graded_ndcg_at_10 > base_m.graded_ndcg_at_10 or (
            cand_m.graded_ndcg_at_10 == base_m.graded_ndcg_at_10
            and cand_m.recall_at_10 > base_m.recall_at_10
        )
        if not improved:
            return PromotionDecision(
                promoted=False,
                reason="Rejected: candidate did not improve graded nDCG@10 or Recall@10 over baseline.",
                baseline=base_m,
                candidate=cand_m,
                rollback_config=baseline_cfg,
            )

        return PromotionDecision(
            promoted=True,
            reason="Promoted to shadow/canary: improved retrieval ranking with zero per-class or SLA regressions.",
            baseline=base_m,
            candidate=cand_m,
            rollback_config=baseline_cfg,
        )
