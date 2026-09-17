"""Stable result schema for the unified eval harness (backend/evaluation/bench.py).

ponytail: two pydantic models (one row, one report) instead of five ad-hoc dict
shapes across the old scripts. Gates come from app.config.settings so a
threshold change is a config edit, not a code edit.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvalRow(BaseModel):
    """One question, one answer, one scored outcome. Union of every field the
    old golden_bank_eval / authenticated_golden_eval / live_golden_eval_openrouter
    / ragas_eval scripts each tracked separately."""

    id: str
    category: str
    source: Literal[
        "golden_qa_bank",
        "golden_dataset",
        "question_bank",
        "abstention_eval",
        "golden_questions",
        "priority_languages",
        "mukthi_guru_v1",
        "injection_crosslingual",
        "injection_multilingual",
    ]
    mode: Literal["anonymous", "authenticated"]
    question: str

    # Transport
    http_status: int | None = None
    error: str | None = None
    latency_s: float = 0.0

    # Answer + grounding
    answer: str = ""
    refused: bool = False
    should_abstain: bool | None = None
    abstention_correct: bool | None = Field(
        default=None,
        description="None when should_abstain is unset (not an abstention probe).",
    )
    grounding_state: str | None = None
    query_tier: str | None = None
    cache_hit: bool = False

    # Doctrinal correctness (non-circular signal — must_mention/reject_if are
    # hand-authored, never derived from the same corpus being graded)
    must_mention_total: int = 0
    must_mention_hit: int = 0
    coverage: float = 0.0
    contradictions: list[str] = Field(default_factory=list)

    # Faithfulness / verification, as returned by the pipeline itself
    faithfulness_score: float | None = None
    hallucination_flag: bool | None = None
    verification: dict | None = None

    # Citations
    citations_count: int = 0
    citations_valid_count: int = 0

    # Per-lane provenance (evaluation_trace passthrough)
    retrieved_count: int | None = None
    okf_injected_count: int | None = None
    kg_context_chars: int | None = None
    lightrag_context_chars: int | None = None
    retrieval_lane: str | None = None

    # Corpus-provenance proxy for THIS answer's citations (Qdrant read-only
    # lookup by source_url -- see bench.py::_machine_summary_share)
    machine_summary_share: float | None = None

    # Content-independent stylometry (services/voice/style.py)
    guru_voice_distance: float | None = None

    # Misattribution -- top-severity failure class (owner, 2026-09-16): this
    # product is a disciple that transmits + attributes teachings, never
    # speaks as the teacher. See bench.py::_misattribution_flags.
    misattribution_flags: list[str] = Field(default_factory=list)
    evidence: list[dict] = Field(
        default_factory=list,
        description="Qdrant chunks matched by this answer's citation source_urls: "
        "url, provenance, teacher_ids, text_snippet. For the human review pass.",
    )

    # First-class failure signals (what tonight's incident needed)
    zero_retrieval_canary: bool = Field(
        default=False,
        description="retrieved_count==0 on a question that was not expected to abstain.",
    )
    possible_node_error: bool = Field(
        default=False,
        description=(
            "HTTP 200 but the shape looks like an internal exception was "
            "swallowed into a refusal: zero retrieval, zero citations, "
            "refused, on a question with real corpus grounding."
        ),
    )
    system_error: bool = Field(
        default=False,
        description=(
            "Direct signal, not a heuristic: response carries "
            "grounding_state=system_error / intent=ERROR / route_decision=error "
            "-- the pipeline broke (e.g. upstream circuit breaker OPEN) and "
            "papered over it with a generic apology at HTTP 200, rather than "
            "a considered abstention."
        ),
    )

    memory_used: bool | None = None
    personalized: bool | None = None


class GateResult(BaseModel):
    name: str
    passed: bool
    measured: float
    threshold: float
    comparator: Literal["<=", ">="]


class EvalReport(BaseModel):
    mode: str
    sources: list[str]
    total_questions: int
    completed: int
    started_at: str
    finished_at: str | None = None

    refusal_rate: float = 0.0
    must_mention_coverage_all: float = 0.0
    must_mention_coverage_answered: float = 0.0
    contradiction_count: int = 0
    citation_validity_rate: float = 0.0
    abstention_correctness: float | None = None
    machine_summary_share_mean: float | None = None
    guru_voice_distance_median: float | None = None
    zero_retrieval_rate: float = 0.0
    possible_node_error_rate: float = 0.0
    system_error_rate: float = 0.0
    hallucination_flag_rate: float = 0.0
    misattribution_rate: float = 0.0
    # Rows where citation->chunk evidence could not be resolved at all, so the
    # misattribution check could not run. Tracked separately because an
    # unmeasured row is neither clean nor misattributed, and a run that cannot
    # measure its own top-severity gate must not be reportable as passing it.
    misattribution_unmeasured_rate: float = 0.0
    lane_fired: dict[str, int] = Field(default_factory=dict)

    latency_p50_s: float = 0.0
    latency_p95_s: float = 0.0
    latency_max_s: float = 0.0

    category_breakdown: dict[str, dict[str, Any]] = Field(default_factory=dict)
    gates: list[GateResult] = Field(default_factory=list)
    gates_passed: bool = True

    rows: list[EvalRow] = Field(default_factory=list)


def build_gates(report: EvalReport, settings: Any) -> list[GateResult]:
    """Evaluate report metrics against app.config.settings thresholds.

    ponytail: a flat list of (name, measured, threshold, comparator) tuples,
    not a rule-engine. Add a line here when a new metric needs a CI gate.
    """
    checks: list[tuple[str, float | None, float, str]] = [
        ("refusal_rate", report.refusal_rate, settings.eval_max_refusal_rate, "<="),
        (
            "must_mention_coverage_answered",
            report.must_mention_coverage_answered,
            settings.eval_min_must_mention_coverage,
            ">=",
        ),
        (
            "contradiction_count",
            float(report.contradiction_count),
            float(settings.eval_max_contradictions),
            "<=",
        ),
        (
            "citation_validity_rate",
            report.citation_validity_rate,
            settings.eval_min_citation_validity,
            ">=",
        ),
        (
            "zero_retrieval_rate",
            report.zero_retrieval_rate,
            settings.eval_max_zero_retrieval_rate,
            "<=",
        ),
        ("system_error_rate", report.system_error_rate, settings.eval_max_system_error_rate, "<="),
        ("latency_p95_s", report.latency_p95_s, settings.eval_max_latency_p95_s, "<="),
        (
            "misattribution_rate",
            report.misattribution_rate,
            settings.eval_max_misattribution_rate,
            "<=",
        ),
        # Fail closed on an unmeasurable top-severity gate. A run that could
        # not resolve citation evidence cannot claim a misattribution rate at
        # all, so it must not be able to report PASS by scoring an empty
        # haystack (live 2026-09-17: a host-side run with the compose-internal
        # QDRANT_URL printed a confident "25%" from zero evidence).
        (
            "misattribution_unmeasured_rate",
            report.misattribution_unmeasured_rate,
            getattr(settings, "eval_max_misattribution_unmeasured_rate", 0.0),
            "<=",
        ),
    ]
    if report.abstention_correctness is not None:
        checks.append(
            (
                "abstention_correctness",
                report.abstention_correctness,
                settings.eval_min_abstention_correctness,
                ">=",
            )
        )
    if report.machine_summary_share_mean is not None:
        checks.append(
            (
                "machine_summary_share_mean",
                report.machine_summary_share_mean,
                settings.eval_max_machine_summary_share,
                "<=",
            )
        )

    results = []
    for name, measured, threshold, cmp in checks:
        if measured is None:
            continue
        passed = measured <= threshold if cmp == "<=" else measured >= threshold
        results.append(
            GateResult(
                name=name,
                passed=passed,
                measured=round(measured, 4),
                threshold=threshold,
                comparator=cmp,
            )
        )
    return results


if __name__ == "__main__":
    # ponytail self-check: gate math is right in both directions.
    r = EvalReport(
        mode="e2e",
        sources=["golden_qa_bank"],
        total_questions=1,
        completed=1,
        started_at="t0",
        refusal_rate=0.1,
        must_mention_coverage_answered=0.9,
        citation_validity_rate=0.9,
        latency_p95_s=10.0,
    )

    class _S:
        eval_max_refusal_rate = 0.35
        eval_min_must_mention_coverage = 0.5
        eval_max_contradictions = 0
        eval_min_citation_validity = 0.6
        eval_max_machine_summary_share = 0.3
        eval_min_abstention_correctness = 0.8
        eval_max_zero_retrieval_rate = 0.05
        eval_max_latency_p95_s = 90.0
        eval_max_misattribution_rate = 0.05
        eval_max_misattribution_unmeasured_rate = 0.0
        eval_max_system_error_rate = 0.0

    gates = build_gates(r, _S())
    assert all(g.passed for g in gates), gates
    r2 = r.model_copy(update={"refusal_rate": 0.9})
    gates2 = build_gates(r2, _S())
    assert not [g for g in gates2 if g.name == "refusal_rate"][0].passed
    print("schema self-check OK:", len(gates), "gates evaluated")
