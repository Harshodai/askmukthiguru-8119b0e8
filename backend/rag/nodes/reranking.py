"""Reranking, relevance grading, and context enrichment nodes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .utils import settings
from rag.compressor import compress_documents
from rag.states import GraphState
from rag.timeout_utils import get_node_timeout
from rag.tree_navigator import check_sufficiency
from .utils import log_metrics, _trace_update, _grounded_citation_urls
from . import _services

logger = logging.getLogger(__name__)


@log_metrics
async def rerank_documents(state: GraphState) -> dict:
    """Rerank Documents (CrossEncoder) with adaptive thresholds and MMR."""
    question = state.get("rewritten_query") or state["question"]
    documents = state.get("documents", [])
    reranker = _services._reranker
    embedder = _services._embedder
    qdrant = _services._qdrant

    if not documents:
        return {"reranked_docs": []}

    is_complex = state.get("is_complex", False)
    base_threshold = getattr(settings, "rerank_min_score", 0.2)
    threshold = 0.01 if is_complex else max(0.05, base_threshold - 0.1)

    if settings.use_flashrank and reranker is not None:
        reranked = await reranker.rerank(
            question,
            documents,
            top_k=10,
            min_score=threshold,
        )
    else:
        reranked = await asyncio.to_thread(
            embedder.cascaded_rerank,
            question,
            documents,
            colbert_top_k=20,
            cross_top_k=10,
            min_score=threshold,
        )

    if len(reranked) > settings.rag_top_k_retrieval:
        doc_texts = [doc["text"] for doc in reranked]
        batch_enc = await asyncio.to_thread(embedder.encode_batch, doc_texts)
        doc_embeddings = batch_enc["dense"]

        query_enc = await asyncio.to_thread(embedder.encode_single_full, question)
        query_emb = query_enc["dense"]

        reranked = qdrant.mmr_select(
            query_embedding=query_emb,
            documents=reranked,
            doc_embeddings=doc_embeddings,
            top_k=settings.rag_top_k_retrieval,
            lambda_param=0.7,
        )

    logger.info(
        f"Reranked {len(documents)} -> {len(reranked)} documents "
        f"(complex={is_complex}, threshold={threshold:.2f}, MMR applied)"
    )
    return {
        "reranked_docs": reranked,
        "evaluation_trace": _trace_update(
            state,
            reranked_count=len(reranked),
            reranked_sources=_grounded_citation_urls(reranked),
        ),
    }


@log_metrics
async def grade_documents(state: GraphState) -> dict:
    """CRAG: Batch relevance grading of all reranked documents in one LLM call."""
    ollama = _services._ollama
    embedder = _services._embedder

    if state.get("query_tier") in ("fast", "tier2_simple"):
        reranked_docs = state["reranked_docs"]
        relevant = reranked_docs[:3]
        state["grading_reasons"] = ["Simple query bypass" for _ in relevant]
        logger.info(f"CRAG batch: simple query tier, bypassing grading, accepted {len(relevant)} docs")
        return {
            "relevant_docs": relevant,
            "evaluation_trace": _trace_update(
                state,
                relevant_count=len(relevant),
                relevant_sources=_grounded_citation_urls(relevant),
            ),
        }

    question = state.get("rewritten_query") or state["question"]
    reranked_docs = state["reranked_docs"]

    if not reranked_docs:
        return {"relevant_docs": []}

    intent = state.get("intent", "FACTUAL")
    if intent == "DISTRESS":
        relevant = reranked_docs[:3]
        state["grading_reasons"] = ["Distress intent bypass" for _ in relevant]
        logger.info(
            f"CRAG batch: DISTRESS intent, bypassing grading, accepted {len(relevant)} docs"
        )
    else:
        doc_texts = [doc["text"] for doc in reranked_docs]
        t_out = get_node_timeout("grade_documents", 20.0)
        relevance_results = await ollama.batch_grade_relevance(question, doc_texts, timeout=t_out)

        relevant = []
        reasons = []
        for doc, res in zip(reranked_docs, relevance_results):
            if res["relevant"]:
                relevant.append(doc)
            reasons.append(res["reason"])

        state["grading_reasons"] = reasons

    if relevant:
        relevant = await asyncio.to_thread(
            compress_documents,
            question,
            relevant,
            embedder._reranker,
            threshold=0.3,
            min_sentences=2,
        )

    if reranked_docs:
        try:
            from app.metrics import RETRIEVAL_RELEVANCE_RATIO
            RETRIEVAL_RELEVANCE_RATIO.set(len(relevant) / len(reranked_docs))
        except Exception:
            pass

    logger.info(f"CRAG batch: {len(relevant)}/{len(reranked_docs)} docs passed relevance check")
    return {
        "relevant_docs": relevant,
        "evaluation_trace": _trace_update(
            state,
            relevant_count=len(relevant),
            relevant_sources=_grounded_citation_urls(relevant),
        ),
    }


@log_metrics
async def check_context_sufficiency(state: GraphState) -> dict:
    """PageIndex-inspired iterative sufficiency check."""
    ollama = _services._ollama

    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Sufficiency check: bypassing for simple query tier")
        return {}

    intent = state.get("intent")
    if intent == "DISTRESS":
        logger.info("Sufficiency check: bypassing for DISTRESS intent")
        return {}

    question = state["question"]
    relevant_docs = state.get("relevant_docs", [])

    if not relevant_docs:
        return {}

    context = "\n\n".join(doc["text"] for doc in relevant_docs)
    t_out = get_node_timeout("check_context_sufficiency", 12)
    result = await check_sufficiency(question, context, ollama, timeout=t_out, max_retries=1)

    if not result["sufficient"]:
        logger.info("Sufficiency check: INSUFFICIENT — widening search scope")
        return {"selected_clusters": []}

    return {}


@log_metrics
async def enrich_context(state: GraphState) -> dict:
    """Fetch neighbor chunks for the top relevant documents (RAG Made Simple Ch 8)."""
    relevant_docs = state.get("relevant_docs", [])
    qdrant = _services._qdrant

    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Enrich context: bypassing for simple query tier")
        return {"relevant_docs": relevant_docs}

    if not relevant_docs or settings.rag_context_window <= 0:
        return {"relevant_docs": relevant_docs}

    enriched_docs = []
    seen_hashes = set()

    for doc in relevant_docs[:3]:
        source_url = doc.get("source_url")
        chunk_index = doc.get("chunk_index")

        if source_url and chunk_index is not None:
            neighbors = qdrant.get_neighbor_chunks(
                source_url, chunk_index, window=settings.rag_context_window
            )
            for n in neighbors:
                h = hash(n["text"][:100])
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    enriched_docs.append(n)
        else:
            h = hash(doc["text"][:100])
            if h not in seen_hashes:
                seen_hashes.add(h)
                enriched_docs.append(doc)

    for doc in relevant_docs[3:]:
        h = hash(doc["text"][:100])
        if h not in seen_hashes:
            seen_hashes.add(h)
            enriched_docs.append(doc)

    logger.info(
        f"Enriched {len(relevant_docs)} -> {len(enriched_docs)} chunks using window={settings.rag_context_window}"
    )
    return {"relevant_docs": enriched_docs}
