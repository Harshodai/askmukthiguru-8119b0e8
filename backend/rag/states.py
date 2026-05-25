"""
Mukthi Guru — LangGraph State Definition

Design Patterns:
  - State Machine: TypedDict defines the complete state shape
  - Immutable by Convention: State is passed between nodes, each node returns
    a partial update dict that LangGraph merges

This state flows through all 11 layers of the anti-hallucination pipeline.
Every node reads what it needs and writes what it produces.
"""

from typing import Annotated

from typing_extensions import TypedDict


def add_dicts(left: dict, right: dict) -> dict:
    if not left:
        return right
    if not right:
        return left
    return {**left, **right}


class GraphState(TypedDict):
    """
    Complete state for the Mukthi Guru RAG pipeline.

    Each field documents which node reads/writes it:

    Input Fields (set by the API handler):
      - question:     Original user question
      - chat_history: Previous messages for context

    Routing Fields:
      - intent:       Set by intent_router. DISTRESS | QUERY | CASUAL

    Retrieval Fields:
      - documents:    Set by retrieve_documents. List of retrieved doc dicts
      - reranked_docs: Set by rerank_documents. Top-k after CrossEncoder

    CRAG Fields:
      - relevant_docs: Set by grade_documents. Docs that passed relevance check
      - rewrite_count: Tracks CRAG rewrite iterations (max 3)
      - rewritten_query: The most recent rewritten query

    Decomposition Fields:
      - sub_queries:    Set by decompose_query. Atomic sub-questions
      - is_complex:     Whether query needs decomposition

    Stimulus RAG Fields:
      - hints:          Set by extract_hints. Key evidence phrases

    Generation Fields:
      - answer:         Set by generate_answer. The LLM's response
      - citations:      Source URLs cited in the answer

    Self-RAG Fields:
      - is_faithful:    Set by check_faithfulness. Boolean grounding check

    CoVe Fields:
      - verification:   Set by verify_answer. Verification result dict

    Guardrail Fields:
      - input_blocked:  Set by NeMo input rail. Was input harmful?
      - output_blocked: Set by NeMo output rail. Was output harmful?
      - block_reason:   Why the message was blocked

    Meditation Fields:
      - meditation_step: Current step in Serene Mind flow (0-4)
      - meditation_response: The meditation guidance text

    Final Fields:
      - final_answer:   The response sent to the user
      - error:          Error message if pipeline failed
    """

    # Input
    question: str
    chat_history: list[dict]

    # Request correlation ID ( propagated through every node for log correlation )
    request_id: str | None

    # Routing
    intent: str | None

    # Retrieval
    documents: list[dict]
    reranked_docs: list[dict]
    hyde_text: str | None  # Hypothetical answer for HyDE retrieval

    # CRAG
    relevant_docs: list[dict]
    grading_reasons: list[str]  # Reasoning for document relevance/irrelevance
    rewrite_count: int
    rewritten_query: str | None

    # Decomposition
    sub_queries: list[str]
    is_complex: bool

    # Tree Navigation (PageIndex-inspired)
    selected_clusters: list[int]

    # Stimulus RAG
    hints: list[str]

    # Generation
    answer: str | None
    citations: list[str]

    # Self-RAG
    is_faithful: bool | None

    # Self-Reflection RAG (Nir Diamant pattern)
    needs_correction: bool
    reflection_feedback: str | None

    # CoVe
    verification: dict | None
    confidence_score: float | None  # 1-10 confidence from combined verification

    # Guardrails
    input_blocked: bool
    output_blocked: bool
    block_reason: str | None

    # Meditation
    meditation_step: int
    meditation_response: str | None

    # Final
    final_answer: str | None
    error: str | None

    # Context Engineering
    context_layers: dict | None  # {persona, knowledge, instructions, user_state}

    # Explainable Retrieval
    citation_reasoning: Annotated[dict, add_dicts]  # {url: reasoning}

    # Metrics
    metrics: Annotated[dict, add_dicts]

    # NEW: User & Language Context
    user_id: str | None
    detected_language: str | None
    memory_context: str | None
    ab_model: str | None  # "primary" or "krutrim" for A/B testing
    query_tier: str | None  # "tier2_simple" vs "tier3_complex"
