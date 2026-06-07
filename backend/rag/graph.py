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

from rag.graph_strategies import (
    DeepGraphStrategy,
    FastGraphStrategy,
    StandardGraphStrategy,
)
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


def build_rag_graph(
    ollama_service: OllamaService,
    embedding_service: EmbeddingService,
    qdrant_service: QdrantService,
    lightrag_service: LightRAGService,
    serene_mind_engine: SereneMindEngine = None,
) -> CompiledStateGraph:
    """
    Build and compile the complete RAG pipeline as a LangGraph.

    Delegates to ``StandardGraphStrategy`` so the actual wiring is isolated
    from this public API.
    """
    strategy = StandardGraphStrategy()
    return strategy.build(
        ollama_service=ollama_service,
        embedding_service=embedding_service,
        qdrant_service=qdrant_service,
        lightrag_service=lightrag_service,
        serene_mind_engine=serene_mind_engine,
    )


def build_fast_graph(
    ollama_service: OllamaService,
    embedding_service: EmbeddingService,
    qdrant_service: QdrantService,
    lightrag_service: LightRAGService,
    serene_mind_engine: SereneMindEngine = None,
) -> CompiledStateGraph:
    """Fast path (Path A): 5-node pipeline for simple factual queries."""
    strategy = FastGraphStrategy()
    return strategy.build(
        ollama_service=ollama_service,
        embedding_service=embedding_service,
        qdrant_service=qdrant_service,
        lightrag_service=lightrag_service,
        serene_mind_engine=serene_mind_engine,
    )


def build_deep_graph(
    ollama_service: OllamaService,
    embedding_service: EmbeddingService,
    qdrant_service: QdrantService,
    lightrag_service: LightRAGService,
    serene_mind_engine: SereneMindEngine = None,
) -> CompiledStateGraph:
    """Deep path: full standard graph with additional verification + CoT nodes."""
    strategy = DeepGraphStrategy()
    return strategy.build(
        ollama_service=ollama_service,
        embedding_service=embedding_service,
        qdrant_service=qdrant_service,
        lightrag_service=lightrag_service,
        serene_mind_engine=serene_mind_engine,
    )


# ---------------------------------------------------------------------------
# Factory for initial state
# ---------------------------------------------------------------------------

def create_initial_state(
    question: str,
    chat_history: Optional[list[dict]] = None,
    meditation_step: int = 0,
    request_id: Optional[str] = None,
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
        model_used=None,
        model_provider=None,
        route_decision=None,
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
            intent_router,
            generate_answer,
            verify_answer,
            reflect_on_answer,
            retrieve_documents,
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
