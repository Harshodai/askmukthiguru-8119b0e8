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

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

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
    # Service initialization
    init_services,
    # Node functions
    intent_router,
    navigate_knowledge_tree,
    reflect_on_answer,
    rerank_documents,
    retrieve_documents,
    rewrite_query,
    route_after_grading,
    # Routing functions
    route_by_intent,
    verify_answer,
)
from rag.states import GraphState


def route_after_reflection(state: GraphState) -> str:
    """Route after self-reflection."""
    if state.get("needs_correction"):
        if state.get("rewrite_count", 0) >= 3:
            return "fallback"
        return "rewrite"
    return "verify"


from rag.resolve_followup import resolve_followup
from services.embedding_service import EmbeddingService
from services.lightrag_service import LightRAGService
from services.ollama_service import OllamaService
from services.qdrant_service import QdrantService
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

    Architecture (linear — reliable asyncio.gather parallelism within retrieve_documents):

    START → intent_router
      ├─ DISTRESS → handle_distress → END
      ├─ MEDITATION_CONTINUE → handle_meditation → END
      ├─ CASUAL → handle_casual → END
      └─ QUERY → resolve_followup → decompose_query
                → navigate_knowledge_tree → generate_hyde
                → retrieve_documents (parallel sub-query fetch via asyncio.gather)
                → rerank_documents → grade_documents → check_context_sufficiency
                    ├─ relevant → enrich_context → context_engineer
                    │             → [generate_answer + explain_retrieval] (parallel)
                    │             → reflect_on_answer → verify_answer
                    │             → check_contradiction → format_final_answer → END
                    ├─ rewrite (< 3x) → rewrite_query → retrieve_documents (loop)
                    └─ fallback (≥ 3x) → handle_fallback → END

    Note: retrieve_documents handles parallel sub-query retrieval internally via
    asyncio.gather() — this avoids LangGraph Send API version compatibility issues
    while preserving full parallelism at the retrieval layer.

    Returns:
        Compiled LangGraph (CompiledStateGraph) ready for invocation
    """
    # Inject services into nodes module
    init_services(
        ollama_service, embedding_service, qdrant_service, lightrag_service, serene_mind_engine
    )

    # Create the state graph
    graph = StateGraph(GraphState)

    # === Add all nodes ===
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
            "query": "resolve_followup",
        },
    )

    # Follow-up resolution feeds into decomposition
    graph.add_edge("resolve_followup", "decompose_query")

    # === Linear edges for the RAG pipeline ===
    # Pre-retrieval optimization: tree navigation → HyDE → retrieval
    graph.add_edge("decompose_query", "navigate_knowledge_tree")
    graph.add_edge("navigate_knowledge_tree", "generate_hyde")
    graph.add_edge("generate_hyde", "retrieve_documents")

    # retrieve_documents handles parallel sub-query retrieval internally
    # via asyncio.gather — this is battle-tested and version-compatible
    graph.add_edge("retrieve_documents", "rerank_documents")
    graph.add_edge("rerank_documents", "grade_documents")
    graph.add_edge("grade_documents", "check_context_sufficiency")

    # After sufficiency check + grading → decide: proceed / rewrite / fallback
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

    # Rewrite loop → back to retrieve
    graph.add_edge("rewrite_query", "retrieve_documents")

    # Generate (with inline hints) → Reflect
    graph.add_edge("generate_answer", "reflect_on_answer")

    # Reflect → decide: verify / rewrite / fallback
    graph.add_conditional_edges(
        "reflect_on_answer",
        route_after_reflection,
        {
            "rewrite": "rewrite_query",
            "fallback": "handle_fallback",
            "verify": "verify_answer",
        },
    )

    # Verification & Explanation → format final answer
    graph.add_edge("verify_answer", "check_contradiction")
    graph.add_edge("check_contradiction", "format_final_answer")
    graph.add_edge("explain_retrieval", "format_final_answer")

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
    chat_history: list[dict] | None = None,
    meditation_step: int = 0,
    request_id: str | None = None,
) -> GraphState:
    """
    Create the initial state for a pipeline invocation.

    All fields initialized to safe defaults.
    The question and chat_history are the only required inputs.
    """
    # Cap chat history to last 4 turns (8 messages) to prevent context window overflow
    capped_history = []
    if chat_history:
        # Each "turn" is typically 1 user + 1 assistant message
        capped_history = chat_history[-8:]

    return GraphState(
        # Input
        question=question,
        chat_history=capped_history,
        request_id=request_id,
        # Routing
        intent=None,
        # Retrieval
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        # CRAG
        relevant_docs=[],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        # Decomposition
        sub_queries=[],
        is_complex=False,
        # LangGraph Send API fan-out
        sub_query=None,
        sub_results=[],
        # Tree Navigation (PageIndex-inspired)
        selected_clusters=[],
        # Stimulus RAG
        hints=[],
        # Generation
        answer=None,
        citations=[],
        # Self-RAG
        is_faithful=None,
        needs_correction=False,
        reflection_feedback=None,
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
        # Context Engineering
        context_layers=None,
        # Explainable Retrieval
        citation_reasoning={},
        # Metrics
        metrics={},
        # User & Language
        user_id=None,
        detected_language="en",
        memory_context="",
        ab_model="primary",
        query_tier=None,
        # Per-node timing (R4)
        node_timings={},
    )
