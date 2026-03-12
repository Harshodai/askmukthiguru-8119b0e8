"""
Mukthi Guru — LangGraph Node Functions

Design Patterns:
  - Command Pattern: Each node is a standalone function that modifies state
  - Chain of Responsibility: Nodes form an anti-hallucination pipeline
  - Strategy Pattern: Routing decisions based on intent/quality gates
  
Each node function:
  1. Reads specific fields from GraphState
  2. Performs ONE operation (SRP)
  3. Returns a partial dict that LangGraph merges into state

The 12-Layer Anti-Hallucination Pipeline (optimized — 5-6 LLM calls):
  Layer 1:  NeMo Input Rail (handled externally in main.py)
  Layer 2:  intent_router — classify DISTRESS/QUERY/CASUAL
  Layer 3:  decompose_query — always decompose (eliminates is_complex_query call)
  Layer 4:  retrieve_documents — Qdrant + RAPTOR (parallel sub-query retrieval)
  Layer 5:  rerank_documents — CrossEncoder (precise top-5)
  Layer 6:  grade_documents — CRAG batch relevance check (single LLM call)
  Layer 7:  rewrite_query — CRAG self-correcting loop (3x)
  Layer 8+9: generate_answer — Inline hint extraction + context-only generation
  Layer 10+11: verify_answer — Combined Self-RAG + CoVe verification
  Layer 12: NeMo Output Rail (handled externally in main.py)
"""

import logging
import asyncio
from typing import Any

from rag.states import GraphState
from rag.prompts import (
    GURU_SYSTEM_PROMPT,
    CASUAL_SYSTEM_PROMPT,
    GENERATE_WITH_HINTS_PROMPT,
    FALLBACK_RESPONSE,
    MULTI_TURN_PROMPT,
)
from rag.meditation import (
    get_distress_response,
    format_meditation_response,
    should_start_meditation,
    is_meditation_complete,
)
from services.ollama_service import OllamaService
from services.embedding_service import EmbeddingService
from services.qdrant_service import QdrantService
from app.config import settings

logger = logging.getLogger(__name__)

# Module-level service references (set during graph construction)
_ollama: OllamaService = None
_embedder: EmbeddingService = None
_qdrant: QdrantService = None


def init_services(
    ollama: OllamaService,
    embedder: EmbeddingService,
    qdrant: QdrantService,
) -> None:
    """
    Inject service dependencies into the nodes module.
    Called once during graph construction.
    
    Raises:
        ValueError: If any service is None
    """
    if not all([ollama, embedder, qdrant]):
        missing = []
        if not ollama:
            missing.append("ollama")
        if not embedder:
            missing.append("embedder")
        if not qdrant:
            missing.append("qdrant")
        raise ValueError(f"init_services: missing services: {', '.join(missing)}")
    
    global _ollama, _embedder, _qdrant
    _ollama = ollama
    _embedder = embedder
    _qdrant = qdrant


import time
import functools

def log_metrics(func):
    """Decorator to log execution time of nodes."""
    @functools.wraps(func)
    async def wrapper(state: GraphState, *args, **kwargs):
        start = time.time()
        result = await func(state, *args, **kwargs)
        duration = time.time() - start
        
        node_name = func.__name__
        logger.info(f"Node '{node_name}' finished in {duration:.4f}s")
        
        # Merge metrics into state
        metrics = state.get("metrics") or {}
        metrics[node_name] = duration
        
        # If result merges into state, ensure we preserve/update metrics
        if isinstance(result, dict):
            existing_metrics = result.get("metrics", {})
            existing_metrics.update(metrics)
            result["metrics"] = existing_metrics
            
        return result
    return wrapper


# ===================================================================
# Layer 2: Intent Router
# ===================================================================

@log_metrics
async def intent_router(state: GraphState) -> dict:
    """
    Classify user message → DISTRESS / QUERY / CASUAL.
    
    This is the first decision point. Determines the entire pipeline path:
    - DISTRESS → meditation flow (bypass RAG)
    - QUERY → full 11-layer RAG pipeline
    - CASUAL → simple conversational response
    """
    question = state["question"]
    
    # Check if we're in an active meditation session
    meditation_step = state.get("meditation_step", 0)
    if meditation_step > 0:
        if is_meditation_complete(meditation_step):
            return {"intent": "CASUAL", "meditation_step": 0}
        if should_start_meditation(question):
            return {"intent": "MEDITATION_CONTINUE", "meditation_step": meditation_step}
        return {"intent": "CASUAL", "meditation_step": 0}

    intent = await _ollama.classify_intent(question)
    logger.info(f"Intent: {intent} for query (len={len(question)})")
    return {"intent": intent}


# ===================================================================
# Layer 3: Query Decomposition
# ===================================================================

@log_metrics
async def decompose_query(state: GraphState) -> dict:
    """
    Always decompose queries into sub-queries.

    Eliminates the separate is_complex_query LLM call (saves 1 call).
    The decomposition prompt returns the original query unchanged
    if it's already simple, so no quality loss.
    """
    question = state.get("rewritten_query") or state["question"]

    sub_queries = await _ollama.decompose_query(question)
    is_complex = len(sub_queries) > 1
    logger.info(f"Decomposed into {len(sub_queries)} sub-queries (complex={is_complex})")
    return {"sub_queries": sub_queries, "is_complex": is_complex}


# ===================================================================
# Layer 4: Retrieve Documents
# ===================================================================

@log_metrics
async def retrieve_documents(state: GraphState) -> dict:
    """
    Two-phase hybrid retrieval from Qdrant.

    Phase 1: Search RAPTOR level-1 summaries (thematic overview, top 2)
    Phase 2: Search level-0 leaf chunks (specific details, top 15)
    Merge, deduplicate, and return the combined result set for reranking.

    Uses bge-m3 dense + sparse vectors with RRF fusion for hybrid search.
    If query was decomposed, retrieves for all sub-queries in parallel.
    """
    sub_queries = state.get("sub_queries", [state["question"]])
    chat_history = state.get("chat_history", [])

    async def _retrieve_for_query(query: str) -> list[dict]:
        """Retrieve documents for a single sub-query."""
        # Augment query with last user message from history for follow-up context
        augmented_query = query
        if chat_history:
            last_user_msgs = [
                m["content"] for m in chat_history[-4:]
                if m.get("role") == "user"
            ]
            if last_user_msgs:
                augmented_query = f"{last_user_msgs[-1]} {query}"

        # HyDE (Hypothetical Document Embeddings)
        query_for_embedding = augmented_query
        if settings.rag_use_hyde:
            logger.info("HyDE: Generating hypothetical answer...")
            try:
                hypothetical = await _ollama.generate_hypothetical_answer(query)
                query_for_embedding = hypothetical
                logger.debug(f"HyDE: {hypothetical[:50]}...")
            except Exception as e:
                logger.warning(f"HyDE generation failed: {e}. Using original query.")

        # Encode query with both dense and sparse for hybrid search
        query_embedding = _embedder.encode_single_full(query_for_embedding)

        # Phase 1: Search RAPTOR level-1 summaries (thematic overview)
        summary_results = _qdrant.search(
            query_vector=query_embedding['dense'],
            limit=2,
            sparse_vector=query_embedding['sparse'],
            raptor_level=1,
        )

        # Phase 2: Search level-0 leaf chunks (specific details)
        chunk_results = _qdrant.search(
            query_vector=query_embedding['dense'],
            limit=settings.rag_top_k_retrieval,
            sparse_vector=query_embedding['sparse'],
            raptor_level=0,
        )

        return summary_results + chunk_results

    # Run all sub-query retrievals in parallel
    all_results = await asyncio.gather(
        *[_retrieve_for_query(q) for q in sub_queries]
    )

    # Merge and deduplicate across all sub-query results
    all_docs = []
    seen_texts = set()
    for results in all_results:
        for doc in results:
            text_hash = hash(doc["text"][:100])
            if text_hash not in seen_texts:
                seen_texts.add(text_hash)
                all_docs.append(doc)

    logger.info(f"Retrieved {len(all_docs)} unique documents (two-phase hybrid, parallel)")
    return {"documents": all_docs}


# ===================================================================
# Layer 5: Rerank Documents (CrossEncoder)
# ===================================================================

@log_metrics
async def rerank_documents(state: GraphState) -> dict:
    """
    CrossEncoder reranking: top-20 → top-3.
    
    This is the single biggest precision boost. The CrossEncoder deeply
    compares each (query, document) pair to produce precise relevance scores.
    """
    question = state.get("rewritten_query") or state["question"]
    documents = state["documents"]

    if not documents:
        return {"reranked_docs": []}

    reranked = _embedder.rerank(question, documents)
    logger.info(f"Reranked {len(documents)} → {len(reranked)} documents")
    return {"reranked_docs": reranked}


# ===================================================================
# Layer 6: Grade Documents (CRAG)
# ===================================================================

@log_metrics
async def grade_documents(state: GraphState) -> dict:
    """
    CRAG: Batch relevance grading of all reranked documents in one LLM call.

    Instead of N separate LLM calls (one per doc), uses a single batch
    grading prompt. Reduces LLM calls from N to 1.
    If ALL documents fail, triggers query rewriting.
    """
    question = state.get("rewritten_query") or state["question"]
    reranked_docs = state["reranked_docs"]

    if not reranked_docs:
        return {"relevant_docs": []}

    doc_texts = [doc["text"] for doc in reranked_docs]
    relevance_flags = await _ollama.batch_grade_relevance(question, doc_texts)

    relevant = [
        doc for doc, is_rel in zip(reranked_docs, relevance_flags) if is_rel
    ]

    logger.info(f"CRAG batch: {len(relevant)}/{len(reranked_docs)} docs passed relevance check")
    return {"relevant_docs": relevant}


# ===================================================================
# Layer 7: Rewrite Query (CRAG Loop)
# ===================================================================

@log_metrics
async def rewrite_query(state: GraphState) -> dict:
    """
    CRAG: Self-correcting query rewrite.
    
    When no documents pass relevance grading, rewrite the query
    with expanded spiritual terminology and retry retrieval.
    
    Max 3 rewrites before falling back to "I don't know."
    """
    rewrite_count = state.get("rewrite_count", 0) + 1
    original = state.get("rewritten_query") or state["question"]

    rewritten = await _ollama.rewrite_query(original)
    logger.info(f"CRAG rewrite #{rewrite_count}: {original[:50]}... → {rewritten[:50]}...")

    return {
        "rewritten_query": rewritten,
        "rewrite_count": rewrite_count,
    }


# ===================================================================
# Layer 8+9: Generate Answer (with inline hint extraction)
# Merged: extract_hints + generate_answer into one LLM call
# ===================================================================

@log_metrics
async def generate_answer(state: GraphState) -> dict:
    """
    Generate the final answer with inline hint extraction.

    Merges the old extract_hints (layer 8) and generate_answer (layer 9)
    into a single LLM call using GENERATE_WITH_HINTS_PROMPT, which
    instructs the LLM to self-identify key evidence before answering.

    Uses:
    - Context from relevant documents
    - Last 3 turns of chat history for multi-turn context
    - Strict system prompt with citation requirements
    """
    question = state.get("rewritten_query") or state["question"]
    relevant_docs = state["relevant_docs"]
    chat_history = state.get("chat_history", [])

    # Build context string
    context = "\n\n---\n\n".join(
        f"[Source: {doc.get('title', doc.get('source_url', 'Unknown'))}]\n{doc['text']}"
        for doc in relevant_docs
    )

    # Build citations list (deterministic ordering for reproducibility)
    citations = sorted(set(
        doc.get("source_url", "") for doc in relevant_docs if doc.get("source_url")
    ))

    # Build chat history context (last 3 turns for multi-turn awareness)
    history_str = ""
    if chat_history:
        recent = chat_history[-6:]  # last 3 turns = 6 messages (user+assistant)
        history_lines = []
        for msg in recent:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")[:200]  # truncate long messages
            history_lines.append(f"{role}: {content}")
        if history_lines:
            history_str = MULTI_TURN_PROMPT.format(
                history="\n".join(history_lines)
            )

    # Generate with inline hints prompt (merges hint extraction + generation)
    prompt = GENERATE_WITH_HINTS_PROMPT.format(
        context=context,
        question=question,
    )

    if history_str:
        prompt = f"{history_str}\n\n{prompt}"

    answer = await _ollama.generate(
        system_prompt="",  # System prompt is embedded in the template
        user_prompt=prompt,
    )

    logger.info(f"Generated answer ({len(answer)} chars, {len(citations)} citations)")
    return {"answer": answer, "citations": citations}


# ===================================================================
# Layer 10+11: Combined Verification (Self-RAG + CoVe merged)
# ===================================================================

@log_metrics
async def verify_answer(state: GraphState) -> dict:
    """
    Combined Self-RAG + CoVe verification in one LLM call.

    Merges the old check_faithfulness (layer 10) and verify_answer (layer 11)
    into a single structured prompt. Reduces 2 LLM calls to 1.

    Checks:
    1. Faithfulness — every claim must be grounded in context
    2. Verification — generates sub-questions and verifies them
    Both must pass for the answer to be accepted.
    """
    answer = state["answer"]
    relevant_docs = state["relevant_docs"]

    context = "\n\n".join(doc["text"] for doc in relevant_docs)
    result = await _ollama.combined_verify(answer, context)

    is_faithful = result["is_faithful"]
    passed = result["passed"]

    logger.info(
        f"Combined verify: faithful={'YES' if is_faithful else 'NO'}, "
        f"verdict={'PASS' if passed else 'FAIL'}"
    )
    return {
        "is_faithful": is_faithful,
        "verification": {"passed": passed, "details": result["details"]},
    }


# ===================================================================
# Response Formatters
# ===================================================================

async def format_final_answer(state: GraphState) -> dict:
    """
    Format the final response based on pipeline results.
    
    Handles all terminal states:
    - Faithful + verified → return answer
    - Not faithful or not verified → return fallback
    - No relevant docs after 3 rewrites → return fallback
    """
    # Check if faithfulness passed
    if not state.get("is_faithful", False):
        logger.warning("Final: Answer rejected by Self-RAG (not faithful)")
        return {"final_answer": FALLBACK_RESPONSE}

    # Check if CoVe verification passed
    verification = state.get("verification", {})
    if not verification.get("passed", False):
        logger.warning("Final: Answer rejected by CoVe (verification failed)")
        return {"final_answer": FALLBACK_RESPONSE}

    # All checks passed — return the answer
    answer = state["answer"]
    citations = state.get("citations", [])

    # Append citation URLs if not already in the answer
    if citations:
        citation_block = "\n\n📚 *Sources:*\n" + "\n".join(f"- {url}" for url in citations[:3])
        if citation_block not in answer:
            answer += citation_block

    return {"final_answer": answer}


async def handle_casual(state: GraphState) -> dict:
    """Handle casual conversation (greetings, thanks, etc.)."""
    response = await _ollama.generate(
        system_prompt=CASUAL_SYSTEM_PROMPT,
        user_prompt=state["question"],
    )
    return {"final_answer": response}


async def handle_distress(state: GraphState) -> dict:
    """Handle distress detection — offer meditation."""
    response = get_distress_response()
    return {"final_answer": response, "meditation_step": 1}


async def handle_meditation(state: GraphState) -> dict:
    """Continue an active meditation session."""
    step = state.get("meditation_step", 1)
    response = format_meditation_response(step)
    return {
        "final_answer": response,
        "meditation_step": step + 1,
    }


async def handle_fallback(state: GraphState) -> dict:
    """Return the graceful fallback response."""
    return {"final_answer": FALLBACK_RESPONSE}


# ===================================================================
# Routing Functions (used by LangGraph conditional edges)
# ===================================================================

def route_by_intent(state: GraphState) -> str:
    """Route after intent classification."""
    intent = state.get("intent", "CASUAL")
    if intent == "DISTRESS":
        return "distress"
    elif intent == "MEDITATION_CONTINUE":
        return "meditation"
    elif intent == "QUERY":
        return "query"
    else:
        return "casual"


def route_after_grading(state: GraphState) -> str:
    """
    Route after CRAG grading.
    
    If docs are relevant → proceed to hints
    If no docs relevant AND rewrites < 3 → rewrite query
    If no docs relevant AND rewrites >= 3 → fallback
    """
    relevant = state.get("relevant_docs", [])
    rewrite_count = state.get("rewrite_count", 0)

    if relevant:
        return "relevant"
    elif rewrite_count < settings.rag_max_rewrites:
        return "rewrite"
    else:
        return "fallback"
