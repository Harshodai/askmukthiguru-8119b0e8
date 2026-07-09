"""
Mukthi Guru — Graph Strategy Pattern

Allows different graph construction strategies (fast, standard, deep)
to be selected at runtime without modifying the graph builder code.

Design Patterns:
  - Strategy Pattern: GraphStrategy ABC with concrete implementations
  - Open/Closed: New graph variants added without changing existing code

This module now contains the actual graph wiring logic.  The strategy
classes import nodes and assemble the LangGraph themselves, eliminating
the previous reverse dependency (strategies → graph.py).
"""

from __future__ import annotations

import abc
import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.config import settings
from rag.nodes import (
    context_engineer,
    decompose_query,
    enrich_context,
    extract_citations,
    format_final_answer,
    generate_answer,
    grade_documents,
    handle_casual,
    handle_distress,
    handle_distress_check,
    handle_fallback,
    handle_meditation,
    init_services,
    intent_router,
    navigate_and_hyde,
    reflect_on_answer,
    rerank_documents,
    retrieve_documents,
    rewrite_query,
    route_after_grading,
    verify_answer,
    web_search_node,
    cross_teacher_reasoning,
)
from rag.resolve_followup import resolve_followup
from rag.states import GraphState


def route_after_intent(state: GraphState) -> str:
    """Route after intent classification, checking for web search needs."""
    intent = state.get("intent", "CASUAL")
    needs_web_search = state.get("needs_web_search", False)
    if intent == "DISTRESS":
        return "distress"
    elif intent in ["MEDITATION", "MEDITATION_CONTINUE"]:
        return "meditation"
    elif intent in ["QUERY", "FACTUAL", "RELATIONAL", "FOLLOW_UP", "ADVERSARIAL", "SAFETY_VIOLATION", "GUIDED_TOUR"]:
        if needs_web_search:
            return "temporal"
        return "query"
    elif intent in ["ERROR"]:
        return "casual"
    else:
        return "casual"

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


logger = logging.getLogger(__name__)


async def lightweight_verify(state: GraphState) -> dict:
    """
    Lightweight verification node using LettuceDetect for faithfulness checking.

    - Skips verification entirely for fast/tier2_simple queries (returns is_faithful=True)
    - Uses LettuceDetectService for standard queries with settings.lettuce_detect_threshold
    - FAIL-CLOSED: missing score/faithfulness result, empty inputs, or any error is
      treated as unfaithful.
    """
    query_tier = state.get("query_tier", "standard")
    if query_tier in ("fast", "tier2_simple"):
        return {"is_faithful": True, "verification": {"skipped": True, "reason": f"query_tier={query_tier}"}}

    answer = state.get("answer", "")
    context = state.get("relevant_docs", [])
    if isinstance(context, list):
        context = "\n\n".join(d.get("content", "") for d in context if isinstance(d, dict))

    if not answer or not context:
        return {"is_faithful": False, "confidence_score": 0.0, "verification": {"skipped": False, "reason": "empty answer or context"}}

    try:
        from app.dependencies import get_container
        from services.lettuce_detect_service import LettuceDetectService

        embedder = get_container().embedding
        lettuce = LettuceDetectService(embedder=embedder)
        result = lettuce.score_faithfulness(
            query=state.get("question", ""),
            context=context,
            answer=answer,
        )

        # Fail-closed: missing keys default to unfaithful / zero score.
        is_faithful = result.get("is_faithful", False)
        score = result.get("score", 0.0)

        # Apply settings threshold (stricter than Lettuce's internal 0.22)
        if score < settings.lettuce_detect_threshold:
            is_faithful = False

        # REMOVED: Doctrine-boost auto-pass (findings #1/#49). Pure LettuceDetect score + threshold is sufficient.

        return {
            "is_faithful": is_faithful,
            "verification": {
                "score": score,
                "details": result.get("details", ""),
                "unsupported_sentences": result.get("unsupported_sentences", []),
            },
        }
    except Exception as e:
        logger.error(f"lightweight_verify failed: {e}, marking as unverified")
        return {"is_faithful": False, "confidence_score": 0.0, "verification": {"error": str(e)}}


# ---------------------------------------------------------------------------
# Routing helpers (previously in graph.py) — moved here to keep graph wiring
# fully encapsulated inside the strategies.
# ---------------------------------------------------------------------------

def _route_after_reflection(state: GraphState) -> str:
    """Route after self-reflection."""
    if state.get("needs_correction"):
        max_rewrites = getattr(settings, "rag_max_rewrites", 2)
        if state.get("rewrite_count", 0) >= max_rewrites:
            return "fallback"
        return "rewrite"
    return "verify"


def parallel_start(state: GraphState):
    return [Send("intent_router", state), Send("handle_distress_check", state)]


async def resolve_parallel(state: GraphState, config: dict = None) -> dict:
    if state.get("parallel_distress_found", False):
        return {"intent": "DISTRESS", "query_tier": "tier2_simple", "confidence_tier": "high"}
    return {}


def route_after_formatting(state: GraphState) -> str:
    if state.get("_needs_retry", False) and state.get("retry_count", 0) < 2:
        return "retry_generate"
    return "end"


def _map_docs_to_relevant(state: GraphState) -> dict:
    """Bridge node: maps retrieved documents → relevant_docs for fast path."""
    return {"relevant_docs": state.get("documents", [])[:5]}


class GraphStrategy(abc.ABC):
    """Abstract strategy for building RAG graphs."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable strategy identifier."""
        ...

    @abc.abstractmethod
    def build(
        self,
        *,
        ollama_service,
        embedding_service,
        qdrant_service,
        lightrag_service,
        serene_mind_engine=None,
    ) -> CompiledStateGraph:
        """Build and return the compiled LangGraph."""
        ...


class StandardGraphStrategy(GraphStrategy):
    """Standard graph for most queries (~8 LLM calls)."""

    @property
    def name(self) -> str:
        return "standard"

    def build(self, **kwargs) -> CompiledStateGraph:
        ollama_service = kwargs.get("ollama_service")
        embedding_service = kwargs.get("embedding_service")
        qdrant_service = kwargs.get("qdrant_service")
        lightrag_service = kwargs.get("lightrag_service")
        serene_mind_engine = kwargs.get("serene_mind_engine")

        # ponytail: skip init_services when no services passed — the cached
        # compile path (build_cached) relies on the facade having already
        # called init_services to set module globals. Ceiling: if a caller
        # invokes build() directly with no services AND globals are unset,
        # nodes will fail at invoke; upgrade by requiring services at compile.
        if ollama_service is not None:
            init_services(
                ollama_service,
                embedding_service,
                qdrant_service,
                lightrag_service,
                serene_mind_engine,
                web_search=kwargs.get("web_search"),
                semantic_cache=kwargs.get("semantic_cache"),
                sarvam_cloud=kwargs.get("sarvam_cloud"),
            )

        graph = StateGraph(GraphState)

        # --- Add all nodes ---
        graph.add_node("intent_router", intent_router)
        graph.add_node("handle_distress_check", handle_distress_check)
        graph.add_node("resolve_parallel", resolve_parallel)
        graph.add_node("resolve_followup", resolve_followup)
        graph.add_node("decompose_query", decompose_query)
        graph.add_node("navigate_and_hyde", navigate_and_hyde)
        graph.add_node("retrieve_documents", retrieve_documents)
        graph.add_node("rerank_documents", rerank_documents)
        graph.add_node("grade_documents", grade_documents)
        graph.add_node("enrich_context", enrich_context)
        graph.add_node("rewrite_query", rewrite_query)
        graph.add_node("generate_answer", generate_answer)
        graph.add_node("reflect_on_answer", reflect_on_answer)
        graph.add_node("verify_answer", verify_answer)
        graph.add_node("extract_citations", extract_citations)
        graph.add_node("context_engineer", context_engineer)
        graph.add_node("format_final_answer", format_final_answer)
        graph.add_node("handle_casual", handle_casual)
        graph.add_node("handle_distress", handle_distress)
        graph.add_node("handle_meditation", handle_meditation)
        graph.add_node("handle_fallback", handle_fallback)
        graph.add_node("web_search", web_search_node)
        graph.add_node("cross_teacher_reasoning", cross_teacher_reasoning)

        # --- Parallel entry: intent_router + handle_distress_check ---
        graph.add_conditional_edges(START, parallel_start, ["intent_router", "handle_distress_check"])
        graph.add_edge("intent_router", "resolve_parallel")
        graph.add_edge("handle_distress_check", "resolve_parallel")

        # --- Conditional edges from merge point ---
        graph.add_conditional_edges(
            "resolve_parallel",
            route_after_intent,
            {
                "distress": "handle_distress",
                "meditation": "handle_meditation",
                "casual": "handle_casual",
                "temporal": "web_search",
                "query": "resolve_followup",
            },
        )

        graph.add_edge("web_search", "resolve_followup")
        # To avoid LangGraph OR-join race condition (and prevent intermittently degraded retrieval quality
        # if both nodes fail or execute out of sync), we chain decompose_query and navigate_and_hyde
        # sequentially. This ensures they execute in a predictable order and satisfies validate_graph.py.
        graph.add_edge("resolve_followup", "decompose_query")
        graph.add_edge("decompose_query", "navigate_and_hyde")
        graph.add_edge("navigate_and_hyde", "retrieve_documents")
        graph.add_edge("retrieve_documents", "rerank_documents")
        graph.add_edge("rerank_documents", "grade_documents")
        graph.add_edge("grade_documents", "cross_teacher_reasoning")

        graph.add_conditional_edges(
            "cross_teacher_reasoning",
            route_after_grading,
            {
                "relevant": "enrich_context",
                "distress": "handle_distress",
                "rewrite": "rewrite_query",
                "fallback": "handle_fallback",
            },
        )

        graph.add_edge("enrich_context", "context_engineer")
        graph.add_edge("context_engineer", "generate_answer")

        graph.add_edge("rewrite_query", "retrieve_documents")

        graph.add_edge("generate_answer", "reflect_on_answer")
        graph.add_conditional_edges(
            "reflect_on_answer",
            _route_after_reflection,
            {
                "rewrite": "rewrite_query",
                "fallback": "handle_fallback",
                "verify": "verify_answer",
            },
        )
        graph.add_edge("verify_answer", "extract_citations")
        graph.add_edge("extract_citations", "format_final_answer")

        # --- Reject-and-retry loop ---
        graph.add_conditional_edges(
            "format_final_answer",
            route_after_formatting,
            {"retry_generate": "generate_answer", "end": END},
        )

        # --- Terminal edges ---
        graph.add_edge("handle_casual", END)
        graph.add_edge("handle_distress", END)
        graph.add_edge("handle_meditation", END)
        graph.add_edge("handle_fallback", END)

        compiled = graph.compile()
        logger.info("LangGraph STANDARD pipeline compiled successfully")
        return compiled


class FastGraphStrategy(GraphStrategy):
    """Minimal graph for simple queries (~3 LLM calls)."""

    @property
    def name(self) -> str:
        return "fast"

    def build(self, **kwargs) -> CompiledStateGraph:
        ollama_service = kwargs.get("ollama_service")
        embedding_service = kwargs.get("embedding_service")
        qdrant_service = kwargs.get("qdrant_service")
        lightrag_service = kwargs.get("lightrag_service")
        serene_mind_engine = kwargs.get("serene_mind_engine")

        # ponytail: skip init_services when no services passed — the cached
        # compile path (build_cached) relies on the facade having already
        # called init_services to set module globals. Ceiling: if a caller
        # invokes build() directly with no services AND globals are unset,
        # nodes will fail at invoke; upgrade by requiring services at compile.
        if ollama_service is not None:
            init_services(
                ollama_service,
                embedding_service,
                qdrant_service,
                lightrag_service,
                serene_mind_engine,
                web_search=kwargs.get("web_search"),
                semantic_cache=kwargs.get("semantic_cache"),
                sarvam_cloud=kwargs.get("sarvam_cloud"),
            )

        graph = StateGraph(GraphState)

        # Core fast-path nodes  (resolve_followup removed for speed)
        graph.add_node("intent_router", intent_router)
        graph.add_node("handle_distress_check", handle_distress_check)
        graph.add_node("resolve_parallel", resolve_parallel)
        graph.add_node("retrieve_documents", retrieve_documents)
        graph.add_node("_map_docs_to_relevant", _map_docs_to_relevant)
        graph.add_node("generate_answer", generate_answer)
        graph.add_node("format_final_answer", format_final_answer)

        # Terminal handlers
        graph.add_node("handle_casual", handle_casual)
        graph.add_node("handle_distress", handle_distress)
        graph.add_node("handle_meditation", handle_meditation)
        graph.add_node("handle_fallback", handle_fallback)
        graph.add_node("web_search", web_search_node)

        # --- Parallel entry: intent_router + handle_distress_check ---
        graph.add_conditional_edges(START, parallel_start, ["intent_router", "handle_distress_check"])
        graph.add_edge("intent_router", "resolve_parallel")
        graph.add_edge("handle_distress_check", "resolve_parallel")

        graph.add_conditional_edges(
            "resolve_parallel",
            route_after_intent,
            {
                "distress": "handle_distress",
                "meditation": "handle_meditation",
                "casual": "handle_casual",
                "temporal": "web_search",
                # Resolve follow-up skipped for fast graph to reduce latency
                "query": "retrieve_documents",
            },
        )

        graph.add_edge("web_search", "retrieve_documents")
        graph.add_edge("retrieve_documents", "_map_docs_to_relevant")
        graph.add_edge("_map_docs_to_relevant", "generate_answer")
        graph.add_edge("generate_answer", "format_final_answer")

        # --- Reject-and-retry loop ---
        graph.add_conditional_edges(
            "format_final_answer",
            route_after_formatting,
            {"retry_generate": "generate_answer", "end": END},
        )

        graph.add_edge("handle_casual", END)
        graph.add_edge("handle_distress", END)
        graph.add_edge("handle_meditation", END)
        graph.add_edge("handle_fallback", END)

        compiled = graph.compile()
        logger.info("LangGraph FAST pipeline compiled successfully")
        return compiled


class DeepGraphStrategy(GraphStrategy):
    """Deep graph — alias to StandardStrategy (identical wiring).

    Was a separate class with an identical graph structure. The parallel
    check_contradiction / explain_retrieval branches were removed as buggy
    (OR-edges caused format_final_answer to fire before verify_answer wrote
    is_faithful). Remains as a distinct name for config-driven routing.
    """

    @property
    def name(self) -> str:
        return "deep"

    def build(self, **kwargs) -> CompiledStateGraph:
        return StandardGraphStrategy().build(**kwargs)


# ---------------------------------------------------------------------------
# Compile cache
# ---------------------------------------------------------------------------
# ponytail: one lru_cache, no new class. Graph wiring is static (node
# function references + edges); services are NOT baked into the compiled
# graph — nodes read module globals set by init_services at invoke time.
# So caching the compiled graph by strategy name alone is safe. The facade
# (graph.py) calls init_services with the caller's services BEFORE
# build_cached, so the globals are set before any invoke. Ceiling: maxsize=4
# covers the 3 strategies + headroom; if a strategy variant is added beyond
# that, raise maxsize. LangGraph compiled graphs are thread-safe for invoke.

_STRATEGY_FACTORIES = {
    "standard": StandardGraphStrategy,
    "fast": FastGraphStrategy,
    "deep": DeepGraphStrategy,
}


@lru_cache(maxsize=4)
def build_cached(strategy_name: str) -> "CompiledStateGraph":
    """Compile a strategy ONCE and return the cached CompiledStateGraph.

    Caller must have called ``init_services`` with valid services beforehand
    (the facade in ``rag.graph`` does this). Repeated calls return the same
    compiled graph instance, avoiding the 50-200ms per-call compile cost.
    """
    try:
        factory = _STRATEGY_FACTORIES[strategy_name]
    except KeyError as exc:
        raise ValueError(f"build_cached: unknown strategy {strategy_name!r}") from exc
    # No service kwargs: build() skips init_services (globals already set by
    # the facade) and only assembles the static graph wiring.
    return factory().build()


def clear_graph_cache() -> None:
    """Reset the compile cache (tests / container rebuild)."""
    build_cached.cache_clear()
