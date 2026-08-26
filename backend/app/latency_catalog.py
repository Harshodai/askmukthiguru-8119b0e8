"""Cross-tier latency budget catalog for measurement and shadow analysis.

This module does not select a graph, skip a quality gate, or alter provider
routing. Budgets are explicitly unvalidated hypotheses until enough repeated
samples exist. The catalog is intentionally language-agnostic: language is an
observational dimension, not a shortcut or quality exception.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RouteClass(StrEnum):
    CASUAL = "casual"
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"
    DISTRESS = "distress"
    TEMPORAL = "temporal"
    MULTILINGUAL = "multilingual"


@dataclass(frozen=True)
class LatencyBudget:
    route_class: RouteClass
    first_status_ms: int
    ttft_ms: int | None
    complete_ms: int
    quality_floor: str = "grounded_or_abstain"
    required_checks: tuple[str, ...] = (
        "input_guardrails",
        "tenant_scope",
        "citation_or_abstention",
        "output_guardrails",
    )
    validated: bool = False
    minimum_samples: int = 20


# Initial operational hypotheses only. These values are for dashboards and
# shadow-policy comparison; they must not be used as per-route cutoffs yet.
LATENCY_BUDGET_CATALOG: dict[RouteClass, LatencyBudget] = {
    RouteClass.CASUAL: LatencyBudget(RouteClass.CASUAL, 250, None, 1500),
    RouteClass.FAST: LatencyBudget(RouteClass.FAST, 500, 2500, 5000),
    RouteClass.STANDARD: LatencyBudget(RouteClass.STANDARD, 500, 5000, 15000),
    RouteClass.DEEP: LatencyBudget(RouteClass.DEEP, 500, 8000, 30000),
    RouteClass.DISTRESS: LatencyBudget(
        RouteClass.DISTRESS,
        250,
        1500,
        4000,
        quality_floor="safe_redirect_or_grounded_support",
        required_checks=("input_guardrails", "distress_policy", "output_guardrails"),
    ),
    RouteClass.TEMPORAL: LatencyBudget(RouteClass.TEMPORAL, 500, 5000, 15000),
    RouteClass.MULTILINGUAL: LatencyBudget(RouteClass.MULTILINGUAL, 500, 7000, 20000),
}


def budget_for(route_class: RouteClass | str) -> LatencyBudget:
    """Return a catalog entry without changing runtime routing behavior."""
    key = RouteClass(route_class)
    return LATENCY_BUDGET_CATALOG[key]


def route_axis(*, intent: str | None, selected_variant: str | None, language: str | None) -> RouteClass:
    """Classify an observed request for reporting only.

    The precedence preserves safety and temporal reporting, then uses the
    actual selected graph variant. Non-English requests are marked as a
    measurement axis only when no more specific safety/route class applies.
    """
    normalized_intent = (intent or "").upper()
    variant = (selected_variant or "").lower()
    if normalized_intent == "DISTRESS":
        return RouteClass.DISTRESS
    if normalized_intent in {"CASUAL", "GREETING"}:
        return RouteClass.CASUAL
    if variant == "deep":
        return RouteClass.DEEP
    if variant in {"fast", "tier2_simple"}:
        return RouteClass.FAST
    if variant in {"standard", "tier3_complex"}:
        return RouteClass.STANDARD
    if language and not language.lower().startswith("en"):
        return RouteClass.MULTILINGUAL
    return RouteClass.STANDARD
