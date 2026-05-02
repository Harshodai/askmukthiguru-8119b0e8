"""
Mukthi Guru — LangGraph Pipeline Assembly

Design Patterns:
  - Builder Pattern: Constructs the graph from nodes and edges
  - State Machine: LangGraph manages state transitions
  - Mediator Pattern: The graph coordinates all node interactions
  - Open/Closed Principle: New nodes can be added without modifying existing ones

This file wires layers 2–11 (of the 12-layer pipeline) into a LangGraph StateGraph.
Layers 1 and 12 (NeMo input/output rails) are handled externally in main.py.
The graph handles:
  - Linear flow: intent → decompose → retrieve → rerank → grade → hints → generate
  - Conditional branching: intent routing, CRAG rewrite loops
  - Short circuits: distress → meditation, casual → simple reply
  - Quality gates: faithfulness check, CoVe verification
"""

import logging
from typing import Optional

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from rag.states import GraphState
from rag.nodes import (
    # Service initialization
    init_services,
    # Node functions
    intent_router,
    decompose_query,
    navigate_knowledge_tree,
    check_context_sufficiency,
    retrieve_documents,
    rerank_documents,
    grade_documents,
    rewrite_query,
    generate_answer,
    verify_answer,
    format_final_answer,
    handle_casual,
    handle_distress,
    handle_meditation,
    handle_fallback,
    # Routing functions
    route_by_intent,
    route_after_grading,
)
from services.ollama_service import OllamaService
from services.embedding_service import EmbeddingService
from services.qdrant_service import QdrantService
from services.lightrag_service import LightRAGService
from services.serene_mind_engine import SereneMindEngine

logger = logging.getLogger(__name__)


def build_rag_graph(
    ollama_service: OllamaService,
    embedding_service: EmbeddingService,
    qdrant_service: QdrantService,
    lightrag_service: LightRAGService,
    serene_mind_engine: SereneMindEngine = None,
) -> CompiledStateGraph:
    """
    Build and compile the complete RAG pipeline as a LangGraph.

    The full pipeline has 12 layers:
      - Layer 1 (NeMo input rail) and Layer 12 (NeMo output rail) are handled
        externally by the FastAPI route handler.
      - Layers 2-11 are implemented as graph nodes here.

    Architecture (optimized — 5-6 LLM calls instead of 11-13):

    START → intent_router
      ├─ DISTRESS → handle_distress → END
      ├─ MEDITATION_CONTINUE → handle_meditation → END
      ├─ CASUAL → handle_casual → END
      └─ QUERY → decompose_query → retrieve_documents → rerank_documents
                → grade_documents
                    ├─ relevant → generate_answer (with inline hints)
                    │             → verify_answer (combined Self-RAG + CoVe)
                    │             → format_final_answer → END
                    ├─ rewrite (< 3x) → rewrite_query → retrieve_documents (loop)
                    └─ fallback (≥ 3x) → handle_fallback → END

    Returns:
        Compiled LangGraph (CompiledStateGraph) ready for invocation
    """
    # Inject services into nodes module
    init_services(ollama_service, embedding_service, qdrant_service, lightrag_service, serene_mind_engine)

    # Create the state graph
    graph = StateGraph(GraphState)

    # === Add all nodes ===
    graph.add_node("intent_router", intent_router)
    graph.add_node("decompose_query", decompose_query)
    graph.add_node("navigate_knowledge_tree", navigate_knowledge_tree)
    graph.add_node("retrieve_documents", retrieve_documents)
    graph.add_node("rerank_documents", rerank_documents)
    graph.add_node("grade_documents", grade_documents)
    graph.add_node("check_context_sufficiency", check_context_sufficiency)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("verify_answer", verify_answer)
    graph.add_node("format_final_answer", format_final_answer)
    graph.add_node("handle_casual", handle_casual)
    graph.add_node("handle_distress", handle_distress)
    graph.add_node("handle_meditation", handle_meditation)
    graph.add_node("handle_fallback", handle_fallback)

    # === Set entry point ===
    graph.set_entry_point("intent_router")

    # === Add conditional edges ===

    # After intent classification → route to the appropriate handler
    graph.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "distress": "handle_distress",
            "meditation": "handle_meditation",
            "casual": "handle_casual",
            "query": "decompose_query",
        },
    )

    # === Linear edges for the RAG pipeline ===
    # PageIndex-inspired: navigate tree → retrieve (scoped) → rerank → grade → sufficiency
    graph.add_edge("decompose_query", "navigate_knowledge_tree")
    graph.add_edge("navigate_knowledge_tree", "retrieve_documents")
    graph.add_edge("retrieve_documents", "rerank_documents")
    graph.add_edge("rerank_documents", "grade_documents")
    graph.add_edge("grade_documents", "check_context_sufficiency")

    # After sufficiency check + grading → decide: proceed / rewrite / fallback
    graph.add_conditional_edges(
        "check_context_sufficiency",
        route_after_grading,
        {
            "relevant": "generate_answer",
            "rewrite": "rewrite_query",
            "fallback": "handle_fallback",
        },
    )

    # Rewrite loop → back to retrieve
    graph.add_edge("rewrite_query", "retrieve_documents")

    # Generate (with inline hints) → Combined verification → Format
    graph.add_edge("generate_answer", "verify_answer")

    # Verification → format final answer
    graph.add_edge("verify_answer", "format_final_answer")

    # === Terminal edges → END ===
    graph.add_edge("format_final_answer", END)
    graph.add_edge("handle_casual", END)
    graph.add_edge("handle_distress", END)
    graph.add_edge("handle_meditation", END)
    graph.add_edge("handle_fallback", END)

    # Compile and return
    compiled = graph.compile()
    logger.info("LangGraph RAG pipeline compiled successfully")
    return compiled


def create_initial_state(
    question: str,
    chat_history: Optional[list[dict]] = None,
    meditation_step: int = 0,
) -> GraphState:
    """
    Create the initial state for a pipeline invocation.
    
    All fields initialized to safe defaults.
    The question and chat_history are the only required inputs.
    """
    return GraphState(
        # Input
        question=question,
        chat_history=chat_history or [],
        # Routing
        intent=None,
        # Retrieval
        documents=[],
        reranked_docs=[],
        # CRAG
        relevant_docs=[],
        rewrite_count=0,
        rewritten_query=None,
        # Decomposition
        sub_queries=[],
        is_complex=False,
        # Tree Navigation (PageIndex-inspired)
        selected_clusters=[],
        # Stimulus RAG
        hints=[],
        # Generation
        answer=None,
        citations=[],
        # Self-RAG
        is_faithful=None,
        # CoVe
        verification=None,
        confidence_score=None,
        # Guardrails
        input_blocked=False,
        output_blocked=False,
        block_reason=None,
        # Meditation
        meditation_step=meditation_step,
        meditation_response=None,
        # Final
        final_answer=None,
        error=None,
    )
