"""Adaptive context-graph planning for ontology-aware retrieval.

The planner is deliberately deterministic and cheap. It decides whether the
existing GraphRAG fusion engine should run for a request, which keeps ordinary
FAQs on the low-latency Qdrant path while giving entity-rich and comparative
questions a bounded graph context.
"""

from __future__ import annotations

from dataclasses import dataclass

from rag.kg_expansion import resolve_concepts_in_query


@dataclass(frozen=True)
class ContextGraphPlan:
    mode: str  # "none", "local", or "multi_hop"
    entity_ids: list[str]
    max_hops: int
    token_budget: int
    reason: str


def plan_context_graph(
    question: str,
    *,
    intent: str = "",
    query_tier: str = "",
) -> ContextGraphPlan:
    """Select a bounded graph retrieval mode without an LLM call.

    Local mode is for a small number of canonical ontology entities. Multi-hop
    mode is reserved for comparative/complex questions and remains capped at
    two hops. Queries without a deterministic entity match stay on Qdrant-only
    retrieval instead of paying graph latency.
    """
    entities = resolve_concepts_in_query(question)[:8]
    normalized_intent = (intent or "").upper()
    normalized_tier = (query_tier or "").lower()
    if not entities:
        return ContextGraphPlan("none", [], 0, 0, "no_canonical_entity_match")
    if normalized_intent in {"COMPARATIVE", "RELATIONAL"} or normalized_tier in {
        "tier3_complex",
        "deep",
    }:
        return ContextGraphPlan(
            "multi_hop",
            entities,
            2,
            2600,
            "complex_or_comparative_entity_question",
        )
    return ContextGraphPlan(
        "local",
        entities,
        1,
        1400,
        "entity_specific_local_context",
    )
