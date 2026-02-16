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

The 12-Layer Anti-Hallucination Pipeline:
  Layer 1:  NeMo Input Rail (handled externally in main.py)
  Layer 2:  intent_router — classify DISTRESS/QUERY/CASUAL
  Layer 3:  decompose_query — split complex queries
  Layer 4:  retrieve_documents — Qdrant + RAPTOR (broad top-20)
  Layer 5:  rerank_documents — CrossEncoder (precise top-3)
  Layer 6:  grade_documents — CRAG relevance binary check
  Layer 7:  rewrite_query — CRAG self-correcting loop (3x)
  Layer 8:  extract_hints — Stimulus RAG key phrases
  Layer 9:  generate_answer — Context-only generation with citations
  Layer 10: check_faithfulness — Self-RAG grounding check
  Layer 11: verify_answer — CoVe sub-question verification
  Layer 12: NeMo Output Rail (handled externally in main.py)
"""

import logging
from typing import Any

from rag.states import GraphState
from rag.prompts import (
    GURU_SYSTEM_PROMPT,
    CASUAL_SYSTEM_PROMPT,
    STIMULUS_RAG_PROMPT,
    FALLBACK_RESPONSE,
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
    Split complex queries into atomic sub-queries.
    
    Only activated for complex queries (comparisons, multi-part).
    Simple queries pass through unchanged.
    """
    question = state.get("rewritten_query") or state["question"]
    
    is_complex = await _ollama.is_complex_query(question)
    
    if is_complex:
        sub_queries = await _ollama.decompose_query(question)
        logger.info(f"Decomposed into {len(sub_queries)} sub-queries")
        return {"sub_queries": sub_queries, "is_complex": True}
    
    return {"sub_queries": [question], "is_complex": False}


# ===================================================================
# Layer 4: Retrieve Documents
# ===================================================================

@log_metrics
async def retrieve_documents(state: GraphState) -> dict:
    """
    Broad retrieval from Qdrant (top-20 by default).
    
    Searches BOTH leaf chunks (level-0) and RAPTOR summaries (level-1)
    simultaneously. The broad result set feeds the CrossEncoder reranker.
    
    If query was decomposed, retrieves for each sub-query and merges.
    """
    sub_queries = state.get("sub_queries", [state["question"]])
    all_docs = []
    seen_texts = set()

    for query in sub_queries:
        
        # HyDE (Hypothetical Document Embeddings)
        # If enabled, we embed the *hypothetical answer* instead of the question.
        # This brings the query vector closer to the document vectors in the semantic space.
        query_for_embedding = query
        if getattr(settings, "rag_use_hyde", False):
            logger.info("HyDE: Generating hypothetical answer...")
            try:
                hypothetical = await _ollama.generate_hypothetical_answer(query)
                query_for_embedding = hypothetical
                logger.debug(f"HyDE: {hypothetical[:50]}...")
            except Exception as e:
                logger.warning(f"HyDE generation failed: {e}. Using original query.")

        # Embed the query (or hypothetical answer)
        query_vector = _embedder.encode_single(query_for_embedding)
        
        # Search Qdrant (Hybrid)
        results = _qdrant.search(
            query_vector=query_vector,
            limit=settings.rag_top_k_retrieval,
            query_text=query,     # Pass text for BM25/Sparse
            hybrid=True,          # Enable hybrid search
        )

        # De-duplicate across sub-queries
        for doc in results:
            text_hash = hash(doc["text"][:100])
            if text_hash not in seen_texts:
                seen_texts.add(text_hash)
                all_docs.append(doc)

    logger.info(f"Retrieved {len(all_docs)} unique documents")
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
    CRAG: Binary relevance grading of each reranked document.
    
    Each document is independently checked for relevance.
    Documents that fail this gate are discarded.
    If ALL documents fail, triggers query rewriting.
    """
    question = state.get("rewritten_query") or state["question"]
    reranked_docs = state["reranked_docs"]

    relevant = []
    for doc in reranked_docs:
        is_relevant = await _ollama.grade_relevance(question, doc["text"])
        if is_relevant:
            relevant.append(doc)
        else:
            logger.debug(f"Doc rejected: {doc['text'][:60]}...")

    logger.info(f"CRAG: {len(relevant)}/{len(reranked_docs)} docs passed relevance check")
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
# Layer 8: Extract Hints (Stimulus RAG)
# ===================================================================

@log_metrics
async def extract_hints(state: GraphState) -> dict:
    """
    Stimulus RAG: Extract key evidence phrases from relevant documents.
    
    Instead of dumping raw documents into the generation prompt,
    we first extract 3-5 focused hint phrases. This dramatically
    improves the LLM's accuracy on rare spiritual terminology.
    """
    question = state.get("rewritten_query") or state["question"]
    relevant_docs = state["relevant_docs"]

    doc_texts = [doc["text"] for doc in relevant_docs]
    hints = await _ollama.extract_hints(question, doc_texts)

    logger.info(f"Stimulus RAG: extracted {len(hints)} hints")
    return {"hints": hints}


# ===================================================================
# Layer 9: Generate Answer
# ===================================================================

@log_metrics
async def generate_answer(state: GraphState) -> dict:
    """
    Generate the final answer using Stimulus RAG prompt template.
    
    Uses:
    - Context from relevant documents
    - Hints from Stimulus RAG
    - Strict system prompt with citation requirements
    """
    question = state.get("rewritten_query") or state["question"]
    relevant_docs = state["relevant_docs"]
    hints = state.get("hints", [])

    # Build context string
    context = "\n\n---\n\n".join(
        f"[Source: {doc.get('title', doc.get('source_url', 'Unknown'))}]\n{doc['text']}"
        for doc in relevant_docs
    )

    # Build hints string
    hints_str = "\n".join(f"- {h}" for h in hints) if hints else "No specific hints extracted."

    # Build citations list (deterministic ordering for reproducibility)
    citations = sorted(set(
        doc.get("source_url", "") for doc in relevant_docs if doc.get("source_url")
    ))

    # Generate with Stimulus RAG template
    prompt = STIMULUS_RAG_PROMPT.format(
        context=context,
        hints=hints_str,
        question=question,
    )

    answer = await _ollama.generate(
        system_prompt="",  # System prompt is embedded in the Stimulus RAG template
        user_prompt=prompt,
    )

    logger.info(f"Generated answer ({len(answer)} chars, {len(citations)} citations)")
    return {"answer": answer, "citations": citations}


# ===================================================================
# Layer 10: Check Faithfulness (Self-RAG)
# ===================================================================

@log_metrics
async def check_faithfulness(state: GraphState) -> dict:
    """
    Self-RAG: Verify generated answer is faithful to the context.
    
    Every claim in the answer must be directly supported by the
    retrieved documents. If ANY unsupported claim is detected,
    the answer is rejected and replaced with the fallback.
    """
    answer = state["answer"]
    relevant_docs = state["relevant_docs"]

    context = "\n\n".join(doc["text"] for doc in relevant_docs)
    is_faithful = await _ollama.check_faithfulness(answer, context)

    logger.info(f"Self-RAG: {'FAITHFUL ✅' if is_faithful else 'HALLUCINATED ❌'}")
    return {"is_faithful": is_faithful}


# ===================================================================
# Layer 11: Verify Answer (CoVe)
# ===================================================================

@log_metrics
async def verify_answer(state: GraphState) -> dict:
    """
    Chain of Verification: Generate sub-questions and verify claims.
    
    Final safety net. Creates 2-3 verification questions from the answer,
    checks if the context can answer them.
    
    If ANY verification fails → reject the answer.
    """
    answer = state["answer"]
    relevant_docs = state["relevant_docs"]
    
    context = "\n\n".join(doc["text"] for doc in relevant_docs)
    verification = await _ollama.verify_claims(answer, context)

    logger.info(f"CoVe: {'PASS ✅' if verification['passed'] else 'FAIL ❌'}")
    return {"verification": verification}


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


def route_after_faithfulness(state: GraphState) -> str:
    """Route after Self-RAG check."""
    if state.get("is_faithful", False):
        return "faithful"
    return "not_faithful"
