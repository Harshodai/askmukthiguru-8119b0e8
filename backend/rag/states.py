"""
Mukthi Guru — LangGraph State Definition

Design Patterns:
  - State Machine: TypedDict defines the complete state shape
  - Immutable by Convention: State is passed between nodes, each node returns
    a partial update dict that LangGraph merges

This state flows through all 11 layers of the anti-hallucination pipeline.
Every node reads what it needs and writes what it produces.
"""

from typing import Annotated, Optional

from typing_extensions import TypedDict


def add_dicts(left: dict, right: dict) -> dict:
    if not left:
        return right
    if not right:
        return left
    return {**left, **right}


def collect_sub_results(existing: list, new: list) -> list:
    """
    Fan-in reducer for LangGraph Send API parallel sub-query branches.

    Each Send branch returns {"sub_results": [doc, doc, ...]}.  This reducer
    collects each branch's list as a separate element so merge_sub_results can
    apply RRF across sub-queries independently::

        existing=[]           new=[doc1, doc2]  →  [[doc1, doc2]]
        existing=[[d1,d2]]    new=[doc3]        →  [[d1,d2],[doc3]]
    """
    return existing + [new]


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
    request_id: Optional[str]

    # Routing
    intent: Optional[str]

    # Retrieval
    documents: list[dict]
    reranked_docs: list[dict]
    hyde_text: Optional[str]  # Hypothetical answer for HyDE retrieval

    # CRAG
    relevant_docs: list[dict]
    grading_reasons: list[str]  # Reasoning for document relevance/irrelevance
    rewrite_count: int
    rewritten_query: Optional[str]

    # Decomposition
    sub_queries: list[str]
    is_complex: bool

    # LangGraph Send API — parallel sub-query retrieval
    # sub_query: injected per-branch via Send({"sub_query": q, ...})
    # sub_results: fan-in collector; each branch appends its result list
    sub_query: Optional[str]
    sub_results: Annotated[list, collect_sub_results]

    # Tree Navigation (PageIndex-inspired)
    selected_clusters: list[int]

    # Stimulus RAG
    hints: list[str]

    # Generation
    answer: Optional[str]
    citations: list[str]

    # Self-RAG
    is_faithful: Optional[bool]

    # Self-Reflection RAG (Nir Diamant pattern)
    needs_correction: bool
    reflection_feedback: Optional[str]

    # CoVe
    verification: Optional[dict]
    confidence_score: Optional[float]  # 1-10 confidence from combined verification

    # Guardrails
    input_blocked: bool
    output_blocked: bool
    block_reason: Optional[str]

    # Meditation
    meditation_step: int
    meditation_response: Optional[str]

    # Final
    final_answer: Optional[str]
    error: Optional[str]

    # Context Engineering
    context_layers: Optional[dict]  # {persona, knowledge, instructions, user_state}

    # Explainable Retrieval
    citation_reasoning: Annotated[dict, add_dicts]  # {url: reasoning}

    # Metrics
    metrics: Annotated[dict, add_dicts]

    # NEW: User & Language Context
    user_id: Optional[str]
    detected_language: Optional[str]
    memory_context: Optional[str]
    ab_model: Optional[str]  # "primary" or "krutrim" for A/B testing
    query_tier: Optional[str]  # "fast" vs "standard" vs "deep"
    model_used: Optional[str]
    model_provider: Optional[str]
    route_decision: Optional[str]

    # Assistant context (custom assistants + notes)
    assistant_slug: Optional[str]
    knowledge_tags: list[str]
    assistant_system_prompt: Optional[str]

    # Confidence Gate
    low_confidence_retrieval: Optional[bool]

    # Web Search (real-time temporal queries)
    needs_web_search: bool
    web_search_results: list[dict]

    # Per-node timing (R4 — structured observability)
    # Each node appends {"node_name": latency_ms} so we get full pipeline breakdown.
    # Reducer add_dicts merges timing dicts from parallel branches without overwriting.
    node_timings: Annotated[dict, add_dicts]

    # Evaluation trace (production AI reliability)
    # Machine-readable trajectory data for benchmarks and trace dashboards.
    evaluation_trace: Annotated[dict, add_dicts]

    # Context Window Budget (Phase 3.2)
    # Remaining token budget for generation, decremented as context is packed.
    # Initialized from settings.context_window_total before the generation node.
    token_budget_remaining: int

    # Confidence Tier (Phase 1.1)
    # Tier classification for P90/P99 path selection: "high" | "medium" | "low"
    # Set by intent_router based on confidence score thresholds.
    confidence_tier: Optional[str]
