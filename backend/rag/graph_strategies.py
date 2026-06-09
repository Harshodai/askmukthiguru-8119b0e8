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
from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from rag.nodes import (
    check_context_sufficiency,
    check_contradiction,
    context_engineer,
    decompose_query,
    enrich_context,
    explain_retrieval,
    format_final_answer,
    generate_answer,
    generate_hyde,
    grade_documents,
    handle_casual,
    handle_distress,
    handle_fallback,
    handle_meditation,
    init_services,
    intent_router,
    navigate_knowledge_tree,
    reflect_on_answer,
    rerank_documents,
    retrieve_documents,
    rewrite_query,
    route_after_grading,
    route_by_intent,
    verify_answer,
)
from app.config import settings
from rag.resolve_followup import resolve_followup
from rag.states import GraphState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from services.embedding_service import EmbeddingService
    from services.lightrag_service import LightRAGService
    from services.ollama_service import OllamaService
    from services.qdrant_service import QdrantService
    from services.serene_mind_engine import SereneMindEngine

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing helpers (previously in graph.py) — moved here to keep graph wiring
# fully encapsulated inside the strategies.
# ---------------------------------------------------------------------------

def _route_after_reflection(state: GraphState) -> str:
    """Route after self-reflection."""
    if state.get("needs_correction"):
        if state.get("rewrite_count", 0) >= 3:
            return "fallback"
        return "rewrite"
    return "verify"


def _map_docs_to_relevant(state: GraphState) -> dict:
    """Bridge node: maps retrieved documents → relevant_docs for fast path."""
    return {"relevant_docs": state.get("documents", [])}


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
    ) -> "CompiledStateGraph":
        """Build and return the compiled LangGraph."""
        ...


class StandardGraphStrategy(GraphStrategy):
    """Standard graph for most queries (~8 LLM calls)."""

    @property
    def name(self) -> str:
        return "standard"

    def build(self, **kwargs) -> "CompiledStateGraph":
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
        )

        graph = StateGraph(GraphState)

        # --- Add all nodes ---
        graph.add_node("intent_router", intent_router)
        graph.add_node("resolve_followup", resolve_followup)
        graph.add_node("decompose_query", decompose_query)
        graph.add_node("navigate_knowledge_tree", navigate_knowledge_tree)
        graph.add_node("generate_hyde", generate_hyde)
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

        # --- Entry point ---
        graph.set_entry_point("intent_router")

        # --- Conditional edges ---
        graph.add_conditional_edges(
            "intent_router",
            route_by_intent,
            {
                "distress": "handle_distress",
                "meditation": "handle_meditation",
                "casual": "handle_casual",
                "query": "resolve_followup",
            },
        )

        graph.add_edge("resolve_followup", "decompose_query")
        graph.add_edge("decompose_query", "navigate_knowledge_tree")
        graph.add_edge("decompose_query", "generate_hyde")
        graph.add_edge("navigate_knowledge_tree", "retrieve_documents")
        graph.add_edge("generate_hyde", "retrieve_documents")
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

        graph.add_edge("verify_answer", "check_contradiction")
        graph.add_edge("check_contradiction", "format_final_answer")
        graph.add_edge("explain_retrieval", "format_final_answer")

        # --- Terminal edges ---
        graph.add_edge("format_final_answer", END)
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

    def build(self, **kwargs) -> "CompiledStateGraph":
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
        )

        graph = StateGraph(GraphState)

        # Core fast-path nodes  (resolve_followup removed for speed)
        graph.add_node("intent_router", intent_router)
        graph.add_node("retrieve_documents", retrieve_documents)
        graph.add_node("_map_docs_to_relevant", _map_docs_to_relevant)
        graph.add_node("generate_answer", generate_answer)
        graph.add_node("format_final_answer", format_final_answer)

        # Terminal handlers
        graph.add_node("handle_casual", handle_casual)
        graph.add_node("handle_distress", handle_distress)
        graph.add_node("handle_meditation", handle_meditation)
        graph.add_node("handle_fallback", handle_fallback)

        graph.set_entry_point("intent_router")

        graph.add_conditional_edges(
            "intent_router",
            route_by_intent,
            {
                "distress": "handle_distress",
                "meditation": "handle_meditation",
                "casual": "handle_casual",
                # Resolve follow-up skipped for fast graph to reduce latency
                "query": "retrieve_documents",
            },
        )

        graph.add_edge("retrieve_documents", "_map_docs_to_relevant")
        graph.add_edge("_map_docs_to_relevant", "generate_answer")
        graph.add_edge("generate_answer", "format_final_answer")
        graph.add_edge("format_final_answer", END)

        graph.add_edge("handle_casual", END)
        graph.add_edge("handle_distress", END)
        graph.add_edge("handle_meditation", END)
        graph.add_edge("handle_fallback", END)

        compiled = graph.compile()
        logger.info("LangGraph FAST pipeline compiled successfully")
        return compiled


class DeepGraphStrategy(GraphStrategy):
    """Deep graph for complex queries (~19 LLM calls)."""

    @property
    def name(self) -> str:
        return "deep"

    def build(self, **kwargs) -> "CompiledStateGraph":
        # Currently a thin wrapper around the standard graph with potential
        # for extra deep-dive nodes (multi-hop reasoning, adversarial check).
        # Reuse the standard wiring; per-node config read at runtime via
        # state["query_tier"] == "deep".
        strategy = StandardGraphStrategy()
        return strategy.build(**kwargs)
