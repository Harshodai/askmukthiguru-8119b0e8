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
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.config import settings
from rag.nodes import (
    check_context_sufficiency,
    check_contradiction,
    context_engineer,
    decompose_query,
    enrich_context,
    explain_retrieval,
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
        graph.add_node("check_context_sufficiency", check_context_sufficiency)
        graph.add_node("rewrite_query", rewrite_query)
        graph.add_node("generate_answer", generate_answer)
        graph.add_node("reflect_on_answer", reflect_on_answer)
        graph.add_node("verify_answer", verify_answer)
        graph.add_node("explain_retrieval", explain_retrieval)
        graph.add_node("context_engineer", context_engineer)
        graph.add_node("format_final_answer", format_final_answer)
        graph.add_node("handle_casual", handle_casual)
        graph.add_node("handle_distress", handle_distress)
        graph.add_node("handle_meditation", handle_meditation)
        graph.add_node("handle_fallback", handle_fallback)
        graph.add_node("web_search", web_search_node)

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
        graph.add_edge("resolve_followup", "decompose_query")
        graph.add_edge("decompose_query", "navigate_and_hyde")
        graph.add_edge("navigate_and_hyde", "retrieve_documents")
        graph.add_edge("retrieve_documents", "rerank_documents")
        graph.add_edge("rerank_documents", "grade_documents")
        graph.add_edge("grade_documents", "check_context_sufficiency")

        graph.add_conditional_edges(
            "check_context_sufficiency",
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
        graph.add_edge("context_engineer", "explain_retrieval")

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
        graph.add_edge("verify_answer", "format_final_answer")
        graph.add_edge("explain_retrieval", "format_final_answer")

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
    """Deep graph for complex queries (~19 LLM calls). Uses full verification chain."""

    @property
    def name(self) -> str:
        return "deep"

    def build(self, **kwargs) -> CompiledStateGraph:
        ollama_service = kwargs.get("ollama_service")
        embedding_service = kwargs.get("embedding_service")
        qdrant_service = kwargs.get("qdrant_service")
        lightrag_service = kwargs.get("lightrag_service")
        serene_mind_engine = kwargs.get("serene_mind_engine")

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

        # --- Add all nodes (full chain including verification) ---
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
        graph.add_node("check_context_sufficiency", check_context_sufficiency)
        graph.add_node("rewrite_query", rewrite_query)
        graph.add_node("generate_answer", generate_answer)
        graph.add_node("reflect_on_answer", reflect_on_answer)
        graph.add_node("verify_answer", verify_answer)
        graph.add_node("explain_retrieval", explain_retrieval)
        graph.add_node("context_engineer", context_engineer)
        graph.add_node("format_final_answer", format_final_answer)
        graph.add_node("check_contradiction", check_contradiction)
        graph.add_node("handle_casual", handle_casual)
        graph.add_node("handle_distress", handle_distress)
        graph.add_node("handle_meditation", handle_meditation)
        graph.add_node("handle_fallback", handle_fallback)
        graph.add_node("web_search", web_search_node)

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
        graph.add_edge("resolve_followup", "decompose_query")
        graph.add_edge("decompose_query", "navigate_and_hyde")
        graph.add_edge("navigate_and_hyde", "retrieve_documents")
        graph.add_edge("retrieve_documents", "rerank_documents")
        graph.add_edge("rerank_documents", "grade_documents")
        graph.add_edge("grade_documents", "check_context_sufficiency")

        graph.add_conditional_edges(
            "check_context_sufficiency",
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
        graph.add_edge("context_engineer", "explain_retrieval")

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

        # -----------------------------------------------------------------------
        # Parallel verification fan-out (DeepGraph optimisation — [2.3.3])
        # -----------------------------------------------------------------------
        # verify_answer (LettuceDetect faithfulness) runs AFTER reflect_on_answer
        # (needs the final corrected answer). check_contradiction (history scan) and
        # explain_retrieval (citation reasoning) can run CONCURRENTLY from generate_answer
        # since they only need `answer` + `relevant_docs` / `chat_history`, not the
        # reflection corrections.
        #
        # Topology:
        #   generate_answer ─┬─► reflect_on_answer ──► verify_answer ─────────────┐
        #                    ├─► check_contradiction (parallel, no LLM deps)        ├─► format_final_answer → END
        #                    └─► explain_retrieval (parallel citation reasoning)  ──┘
        #
        # Net saving vs. sequential verify→contradiction: ~5-10s/query on tier3_complex.
        # -----------------------------------------------------------------------
        graph.add_edge("generate_answer", "check_contradiction")  # parallel branch
        graph.add_edge("verify_answer", "format_final_answer")
        graph.add_edge("check_contradiction", "format_final_answer")
        graph.add_edge("explain_retrieval", "format_final_answer")

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
        logger.info("LangGraph DEEP pipeline compiled successfully")
        return compiled
