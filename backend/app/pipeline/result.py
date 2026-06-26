"""Pipeline result types for Mukthi Guru orchestration.

These dataclasses are intentionally immutable (frozen) to prevent
accidental mutation during the pipeline flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PipelineResult:
    """Result of a full pipeline execution.

    Attributes
    ----------
    final_answer: str
        The response text (already translated if needed).
    intent: str
        Detected intent (QUERY, CASUAL, MEDITATION, DISTRESS, ERROR).
    meditation_step: int
        Current meditation step if applicable.
    citations: list
        List of citation dicts with source_url, score, etc.
    trace_id: str
        Unique query identifier.
    latency_ms: int
        Total end-to-end latency in milliseconds.
    model_used: str | None
        Name of the LLM model that generated the response.
    model_provider: str | None
        Provider name (sarvam_cloud, ollama, etc.).
    route_decision: str
        Routing decision (semantic_cache, fast, standard, deep, error).
    query_tier: str | None
        Graph tier selected (fast, standard, deep).
    blocked: bool
        Whether the response was blocked by guardrails.
    block_reason: str | None
        Reason for blocking, if applicable.
    cache_hit: bool
        Whether the response came from cache.
    proactive_serene_mind: dict | None
        Proactive Serene Mind trigger data, if any.
    faithfulness_score: float
        LettuceDetect / Self-RAG faithfulness score.
    hallucination_flag: bool
        Whether the answer was flagged as potentially hallucinated.
    retrieval_metadata: dict | None
        Metadata about retrieved chunks (chunk_ids, scores, top_k).
    trigger_events: list[dict]
        List of trigger events (e.g., DISTRESS).
    safety_events: list[dict]
        List of safety events (guardrail blocks).
    spans: list[dict]
        Per-node timing spans from LangGraph.
    """

    final_answer: str = ""
    intent: str = "CASUAL"
    meditation_step: int = 0
    citations: list = field(default_factory=list)
    trace_id: str = ""
    latency_ms: int = 0
    model_used: str | None = None
    model_provider: str | None = None
    route_decision: str = ""
    query_tier: str | None = None
    blocked: bool = False
    block_reason: str | None = None
    cache_hit: bool = False
    proactive_serene_mind: dict | None = None
    faithfulness_score: float = 1.0
    hallucination_flag: bool = False
    answer_relevancy: float = 1.0
    context_precision: float = 1.0
    context_recall: float = 1.0
    confidence_score: float | None = None
    judge_reasoning: str = ""
    evaluation_trace: dict | None = None
    retrieval_metadata: dict | None = None
    trigger_events: list[dict] = field(default_factory=list)
    safety_events: list[dict] = field(default_factory=list)
    spans: list[dict] = field(default_factory=list)
    follow_up_suggestions: list[str] = field(default_factory=list)

    def with_latency(self, latency_ms: int) -> "PipelineResult":
        """Return a new PipelineResult with updated latency."""
        return PipelineResult(
            final_answer=self.final_answer,
            intent=self.intent,
            meditation_step=self.meditation_step,
            citations=self.citations,
            trace_id=self.trace_id,
            latency_ms=latency_ms,
            model_used=self.model_used,
            model_provider=self.model_provider,
            route_decision=self.route_decision,
            query_tier=self.query_tier,
            blocked=self.blocked,
            block_reason=self.block_reason,
            cache_hit=self.cache_hit,
            proactive_serene_mind=self.proactive_serene_mind,
            faithfulness_score=self.faithfulness_score,
            hallucination_flag=self.hallucination_flag,
            answer_relevancy=self.answer_relevancy,
            context_precision=self.context_precision,
            context_recall=self.context_recall,
            confidence_score=self.confidence_score,
            judge_reasoning=self.judge_reasoning,
            evaluation_trace=self.evaluation_trace,
            retrieval_metadata=self.retrieval_metadata,
            trigger_events=self.trigger_events,
            safety_events=self.safety_events,
            spans=self.spans,
            follow_up_suggestions=self.follow_up_suggestions,
        )

    def to_chat_response(self) -> dict[str, Any]:
        """Convert to a dict compatible with ChatResponse schema."""
        return {
            "response": self.final_answer,
            "intent": self.intent,
            "meditation_step": self.meditation_step,
            "citations": self.citations,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "trace_id": self.trace_id,
            "latency_ms": self.latency_ms,
            "model_used": self.model_used,
            "model_provider": self.model_provider,
            "route_decision": self.route_decision,
            "query_tier": self.query_tier,
            "cache_hit": self.cache_hit,
            "proactive_serene_mind": self.proactive_serene_mind,
            "faithfulness_score": self.faithfulness_score,
            "hallucination_flag": self.hallucination_flag,
            "follow_up_suggestions": self.follow_up_suggestions,
        }
