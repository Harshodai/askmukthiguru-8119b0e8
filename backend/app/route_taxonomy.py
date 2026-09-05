import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

class RouteLayer(str, Enum):
    CACHE_CHECK = "CACHE_CHECK"
    INPUT_GUARDRAILS = "INPUT_GUARDRAILS"
    DOCTRINE_CACHE = "DOCTRINE_CACHE"
    CASUAL_SHORT_CIRCUIT = "CASUAL_SHORT_CIRCUIT"
    DISTRESS_STAGE = "DISTRESS_STAGE"
    BOUNDED_COMPARISON = "BOUNDED_COMPARISON"
    GRAPH_INTENT_ROUTER = "GRAPH_INTENT_ROUTER"
    GRAPH_GENERATION = "GRAPH_GENERATION"
    PIPELINE_COORDINATOR = "PIPELINE_COORDINATOR"

class RouteDecision(str, Enum):
    # Cache
    HOT_CACHE = "hot_cache"
    VECTOR_CACHE_P90 = "vector_cache_p90"
    SEMANTIC_CACHE = "semantic_cache"
    DOCTRINE_CACHE = "doctrine_cache"
    
    # Short-circuits
    INSTANT_GREETING = "instant_greeting"
    CRISIS_PREEMPTED = "crisis_preempted"
    BOUNDED_COMPARISON = "bounded_comparison_short_circuit"
    NO_CONTEXT_SHORT_CIRCUIT = "no_context_short_circuit"
    
    # Graph execution
    QUERY = "query"
    FACTUAL = "factual"
    CASUAL = "casual"
    DISTRESS = "distress"
    MEDITATION = "meditation"
    ADVERSARIAL = "adversarial"
    SAFETY_VIOLATION = "safety_violation"
    LIVE_LOGISTICS = "live_logistics"
    COMPARATIVE = "comparative"
    
    # Fallbacks
    LIMITED_COMPARISON_FALLBACK = "limited_comparison_fallback"
    REFLECTIVE_FALLBACK = "reflective_fallback"
    
    # Generation engines
    GROUNDED_PARTIAL = "grounded_partial_evidence"
    WEB_RESULTS = "official_live_web_results"
    
    # Error states
    ERROR = "error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"

@dataclass
class RoutingProvenance:
    layer: str
    decision: str
    method: str
    confidence: float = 0.0
    reason: str = ""
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    upstream_decision: Optional[str] = None

    def to_dict(self):
        return {
            "layer": self.layer,
            "decision": self.decision,
            "method": self.method,
            "confidence": self.confidence,
            "reason": self.reason,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "upstream_decision": self.upstream_decision
        }

# Mapping of sub-variants / legacy aliases to canonical RouteDecision values
ROUTE_DECISION_ALIASES: dict[str, str] = {
    "grounded_partial_fast_tier": RouteDecision.GROUNDED_PARTIAL.value,
    "grounded_partial_fallback": RouteDecision.GROUNDED_PARTIAL.value,
    "reflective_peace_meaning_fallback": RouteDecision.REFLECTIVE_FALLBACK.value,
    "reflective_meaning_fallback": RouteDecision.REFLECTIVE_FALLBACK.value,
    "reflective_practice_fallback": RouteDecision.REFLECTIVE_FALLBACK.value,
}


def canonicalize_route_decision(decision: str | None) -> str:
    """Map raw or sub-variant route decisions to canonical RouteDecision values."""
    if not decision:
        return RouteDecision.ERROR.value
    cleaned = str(decision).strip().lower()
    return ROUTE_DECISION_ALIASES.get(cleaned, cleaned)


def record_routing_decision(ctx: object, provenance: "RoutingProvenance") -> None:
    """Append a routing provenance record to ctx.routing_chain.

    Uses duck-typing so this module never imports PipelineContext (which would
    create a circular dependency). Safe to call unconditionally — a missing or
    non-list attribute is silently skipped.
    """
    chain = getattr(ctx, "routing_chain", None)
    if isinstance(chain, list):
        provenance.decision = canonicalize_route_decision(provenance.decision)
        chain.append(provenance.to_dict())

