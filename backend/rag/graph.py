"""
Mukthi Guru — LangGraph Pipeline Assembly

Design Patterns:
  - Builder Pattern: Constructs the graph from nodes and edges
  - State Machine: LangGraph manages state transitions
  - Mediator Pattern: The graph coordinates all node interactions
  - Open/Closed Principle: New nodes can be added without modifying existing ones
  - Strategy Pattern: Graph variants (fast, standard, deep) via GraphStrategy

This file is now a thin facade around ``rag.graph_strategies``.  The actual
graph wiring lives in the strategy classes so that new variants can be added
without touching this module.

Entry points:
  - ``build_rag_graph(...)``      → StandardGraphStrategy
  - ``build_fast_graph(...)``     → FastGraphStrategy
  - ``build_deep_graph(...)``     → DeepGraphStrategy
  - ``create_initial_state(...)`` → factory for GraphState
"""

import logging
from typing import Optional

from rag.graph_strategies import build_cached
from rag.nodes import init_services
from rag.states import GraphState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API: thin wrappers that delegate to GraphStrategy implementations
# ---------------------------------------------------------------------------

from langgraph.graph.state import CompiledStateGraph

from services.embedding_service import EmbeddingService
from services.lightrag_service import LightRAGService
from services.ollama_service import OllamaService
from services.qdrant_service import QdrantService
from services.serene_mind_engine import SereneMindEngine


def _init_then_compile(
    strategy_name: str,
    ollama_service,
    embedding_service,
    qdrant_service,
    lightrag_service,
    serene_mind_engine=None,
    web_search=None,
    doctrine_service=None,
    llm_gateway=None,
    graphrag_fusion=None,
) -> CompiledStateGraph:
    """Inject services into module globals, then return the cached compile.

    init_services is idempotent (sets the same singletons); the compiled graph
    is cached by strategy name and reused across calls. The service args are
    retained for backward compatibility and so the first call establishes the
    module-level service globals the nodes read at invoke time.
    """
    init_services(
        ollama=ollama_service,
        embedder=embedding_service,
        qdrant=qdrant_service,
        lightrag=lightrag_service,
        serene_mind=serene_mind_engine,
        web_search=web_search,
        doctrine_service=doctrine_service,
        llm_gateway=llm_gateway,
        graphrag_fusion=graphrag_fusion,
    )
    return build_cached(strategy_name)


def build_rag_graph(
    ollama_service: OllamaService,
    embedding_service: EmbeddingService,
    qdrant_service: QdrantService,
    lightrag_service: LightRAGService,
    serene_mind_engine: SereneMindEngine = None,
    web_search=None,
    doctrine_service=None,
    llm_gateway=None,
    graphrag_fusion=None,
) -> CompiledStateGraph:
    """
    Build and compile the complete RAG pipeline as a LangGraph.

    Delegates to ``StandardGraphStrategy`` so the actual wiring is isolated
    from this public API. The compiled graph is cached by strategy name.
    """
    return _init_then_compile(
        "standard",
        ollama_service,
        embedding_service,
        qdrant_service,
        lightrag_service,
        serene_mind_engine,
        web_search,
        doctrine_service,
        llm_gateway,
        graphrag_fusion,
    )


def build_fast_graph(
    ollama_service: OllamaService,
    embedding_service: EmbeddingService,
    qdrant_service: QdrantService,
    lightrag_service: LightRAGService,
    serene_mind_engine: SereneMindEngine = None,
    web_search=None,
    doctrine_service=None,
    llm_gateway=None,
    graphrag_fusion=None,
) -> CompiledStateGraph:
    """Fast path (Path A): 5-node pipeline for simple factual queries."""
    return _init_then_compile(
        "fast",
        ollama_service,
        embedding_service,
        qdrant_service,
        lightrag_service,
        serene_mind_engine,
        web_search,
        doctrine_service,
        llm_gateway,
        graphrag_fusion,
    )


def build_deep_graph(
    ollama_service: OllamaService,
    embedding_service: EmbeddingService,
    qdrant_service: QdrantService,
    lightrag_service: LightRAGService,
    serene_mind_engine: SereneMindEngine = None,
    web_search=None,
    doctrine_service=None,
    llm_gateway=None,
    graphrag_fusion=None,
) -> CompiledStateGraph:
    """Deep path: full standard graph with additional verification + CoT nodes."""
    return _init_then_compile(
        "deep",
        ollama_service,
        embedding_service,
        qdrant_service,
        lightrag_service,
        serene_mind_engine,
        web_search,
        doctrine_service,
        llm_gateway,
        graphrag_fusion,
    )


# ---------------------------------------------------------------------------
# Factory for initial state
# ---------------------------------------------------------------------------

def create_initial_state(
    question: str,
    chat_history: Optional[list[dict]] = None,
    meditation_step: int = 0,
    request_id: Optional[str] = None,
    assistant_slug: Optional[str] = None,
    knowledge_tags: Optional[list[str]] = None,
    assistant_system_prompt: Optional[str] = None,
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
        # headroom CCR raw documents
        raw_documents=[],
        # Claude-style follow-up suggestions (populated by format_final_answer)
        follow_up_suggestions=[],
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
        model_used=None,
        model_provider=None,
        route_decision=None,
        # Assistant context
        assistant_slug=assistant_slug,
        knowledge_tags=knowledge_tags or [],
        assistant_system_prompt=assistant_system_prompt,
        # Web Search
        needs_web_search=False,
        web_search_results=[],
        # Per-node timing (R4)
        node_timings={},
        # Production AI reliability trajectory metadata
        evaluation_trace={},
    )


# ---------------------------------------------------------------------------
# Node Registry integration (registry defined in node_registry.py)
# ---------------------------------------------------------------------------

def _register_graph_nodes() -> None:
    """
    Register key pipeline nodes in the global NodeRegistry.

    This demonstrates how nodes can be registered for discovery without
    hard-coding imports in ``graph.py``.  The registry can be used by
    monitoring, debugging, and dynamic graph-building tools.
    """
    try:
        from rag.node_registry import registry
        from rag.nodes import (
            generate_answer,
            intent_router,
            reflect_on_answer,
            retrieve_documents,
            verify_answer,
        )

        registry.register("intent_router", is_llm=True)(intent_router)
        registry.register("generate_answer", is_llm=True)(generate_answer)
        registry.register("verify_answer", is_llm=True)(verify_answer)
        registry.register("reflect_on_answer", is_llm=True)(reflect_on_answer)
        registry.register("retrieve_documents", is_llm=False)(retrieve_documents)

        logger.info(f"NodeRegistry: registered {len(registry)} nodes ({registry.list()})")
    except Exception as exc:
        logger.warning(f"NodeRegistry node registration skipped: {exc}")


# Register nodes at module import time so they are discoverable
_register_graph_nodes()


def get_registered_nodes() -> list[str]:
    """Return a list of all registered node names."""
    from rag.node_registry import registry

    return registry.list()
