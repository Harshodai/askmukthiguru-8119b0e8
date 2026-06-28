"""Reranking, relevance grading, and context enrichment nodes."""

from __future__ import annotations

import asyncio
import logging

from rag.compressor import compress_documents
from rag.states import GraphState
from rag.timeout_utils import get_node_timeout
from rag.tree_navigator import check_sufficiency

from . import _services
from .utils import _grounded_citation_urls, _trace_update, emit_status, log_metrics, settings

logger = logging.getLogger(__name__)


@log_metrics
async def rerank_documents(state: GraphState, config: dict = None) -> dict:
    """Rerank Documents (CrossEncoder) with adaptive thresholds and MMR."""
    question = state.get("rewritten_query") or state["question"]
    documents = state.get("documents", [])
    reranker = _services._reranker
    embedder = _services._embedder
    qdrant = _services._qdrant

    if not documents:
        return {"reranked_docs": []}

    await emit_status(config, "Ranking the most relevant teachings...")
    
    # Separate web search docs from database docs
    web_docs = [doc for doc in documents if doc.get("content_type") == "web_search"]
    db_docs = [doc for doc in documents if doc.get("content_type") != "web_search"]
    
    # Finding #29: web docs no longer get unconditional 0.95 score
    # They receive a moderate default (0.7) since grading will validate relevance
    for doc in web_docs:
        if "rerank_score" not in doc:
            doc["rerank_score"] = 0.70

    def _apply_rerank_score_cutoff(docs: list[dict], score_key: str = "rerank_score", ratio: float = 0.5) -> list[dict]:
        if not docs or not getattr(settings, "rerank_score_delta_enabled", False):
            return docs
        scores = [doc.get(score_key, 0.0) for doc in docs]
        top_score = max(scores) if scores else 0.0
        if top_score <= 0:
            return docs
        floor = top_score * ratio
        filtered = [doc for doc in docs if doc.get(score_key, 0.0) >= floor]
        logger.debug(f"Rerank score-delta: top={top_score:.3f} floor={floor:.3f} {len(docs)} -> {len(filtered)}")
        return filtered

    reranked_db = []
    if db_docs:
        is_complex = state.get("is_complex", False)
        query_tier = state.get("query_tier", "")
        base_threshold = getattr(settings, "rerank_min_score", 0.2)
        threshold = settings.rerank_threshold_complex if is_complex else max(settings.rerank_threshold_simple, base_threshold - 0.1)

        # Dynamic top-k by query tier — fewer chunks for simpler queries reduces
        # LLM context window usage and lowers TTFT without hurting answer quality.
        _TIER_TOP_K = {
            "fast":          3,
            "tier2_simple":  4,
            "standard":      5,
            "tier3_complex": 8,
        }
        rerank_top_k = _TIER_TOP_K.get(query_tier, getattr(settings, "rag_top_k_rerank", 10))

        # For complex queries: prefer cross-encoder (higher precision) over FlashRank
        # when reranker_enabled_for_complex is True. FlashRank is ~5× faster but
        # sacrifices recall for multi-hop / nuanced doctrinal queries.
        force_cross_encoder = (
            getattr(settings, "reranker_enabled_for_complex", True)
            and query_tier == "tier3_complex"
        )

        if settings.use_flashrank and reranker is not None and not force_cross_encoder:
            reranked_db = await reranker.rerank(
                question,
                db_docs,
                top_k=rerank_top_k,
                min_score=threshold,
            )
        else:
            reranked_db = await asyncio.to_thread(
                embedder.cascaded_rerank,
                question,
                db_docs,
                colbert_top_k=rerank_top_k * 2,
                cross_top_k=rerank_top_k,
                min_score=threshold,
            )


        # Apply score-delta cutoff to keep fewer but better chunks
        reranked_db = _apply_rerank_score_cutoff(reranked_db)

        # Apply MMR selection to database documents if they exceed the budget
        web_docs_count = len(web_docs)
        db_budget = max(0, settings.rag_top_k_retrieval - web_docs_count)
        if len(reranked_db) > db_budget and db_budget > 0:
            doc_texts = [doc["text"] for doc in reranked_db]
            batch_enc = await asyncio.to_thread(embedder.encode_batch, doc_texts)
            doc_embeddings = batch_enc["dense"]

            query_enc = await asyncio.to_thread(embedder.encode_single_full, question)
            query_emb = query_enc["dense"]

            reranked_db = qdrant.mmr_select(
                query_embedding=query_emb,
                documents=reranked_db,
                doc_embeddings=doc_embeddings,
                top_k=db_budget,
                lambda_param=0.7,
            )
        elif db_budget == 0:
            reranked_db = []

    # Combined list starts with web search results, followed by best database docs
    reranked = web_docs + reranked_db

    logger.info(
        f"Reranked total={len(documents)} (web={len(web_docs)}, db={len(db_docs)}) -> "
        f"final={len(reranked)} documents"
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
async def grade_documents(state: GraphState, config: dict = None) -> dict:
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

    reranked_docs = state["reranked_docs"]

    if not reranked_docs:
        return {"relevant_docs": []}

    rerank_scores = [d.get("rerank_score") for d in reranked_docs if d.get("rerank_score") is not None]
    if rerank_scores:
        top_score = max(rerank_scores)
        min_score = settings.rerank_min_score
        if top_score < min_score:
            logger.warning(
                f"Confidence gate: top rerank score {top_score:.3f} < min {min_score}. "
                f"Rejecting {len(reranked_docs)} docs."
            )
            return {
                "relevant_docs": [],
                "low_confidence_retrieval": True,
                "evaluation_trace": _trace_update(
                    state,
                    relevant_count=0,
                    low_confidence=True,
                    top_rerank_score=round(top_score, 4),
                ),
            }

        # CRAG relevance floor: drop docs that fall below a fraction of the top score
        crag_floor = top_score * getattr(settings, "crag_score_delta_ratio", 0.5)
        crag_floor = max(crag_floor, min_score)
        before_count = len(reranked_docs)
        reranked_docs = [
            doc for doc in reranked_docs
            if doc.get("rerank_score", 0.0) >= crag_floor
        ]
        if before_count != len(reranked_docs):
            logger.info(
                f"CRAG floor applied: top={top_score:.3f} floor={crag_floor:.3f} "
                f"{before_count} -> {len(reranked_docs)} docs"
            )

    await emit_status(config, "Filtering for relevance...")
    question = state.get("rewritten_query") or state["question"]

    intent = state.get("intent", "FACTUAL")
    if intent == "DISTRESS":
        relevant = reranked_docs[:3]
        state["grading_reasons"] = ["Distress intent bypass" for _ in relevant]
        logger.info(
            f"CRAG batch: DISTRESS intent, bypassing grading, accepted {len(relevant)} docs"
        )
    else:
        # Grade ALL docs — web search must pass relevance too (finding #44)
        web_docs = [doc for doc in reranked_docs if doc.get("content_type") == "web_search"]
        db_docs = [doc for doc in reranked_docs if doc.get("content_type") != "web_search"]

        relevant_web = []
        web_reasons = []

        if web_docs:
            try:
                web_texts = [doc["text"] for doc in web_docs]
                t_out_web = get_node_timeout("grade_documents", 20.0)
                web_results = await ollama.grade_relevance(
                    question=question, doc_texts=web_texts, timeout=t_out_web
                )
                for doc, res in zip(web_docs, web_results):
                    if res["relevant"]:
                        relevant_web.append(doc)
                    web_reasons.append(res["reason"])
            except Exception as e:
                # Unit 9 fail-safe: if web grading raises, keep only the top-3
                # reranked web docs instead of unconditionally accepting all of them.
                logger.warning(
                    f"Grading failed for web docs: {e}. Falling back to top-3 reranked web docs."
                )
                relevant_web = web_docs[:3]
                web_reasons = [f"Grading fallback: {e}" for _ in relevant_web]

        relevant_db = []
        db_reasons = []

        if db_docs:
            try:
                doc_texts = [doc["text"] for doc in db_docs]
                t_out = get_node_timeout("grade_documents", 20.0)
                relevance_results = await ollama.grade_relevance(question=question, doc_texts=doc_texts, timeout=t_out)
                for doc, res in zip(db_docs, relevance_results):
                    if res["relevant"]:
                        relevant_db.append(doc)
                    db_reasons.append(res["reason"])
            except Exception as e:
                logger.warning(f"Grading failed for DB docs: {e}. Falling back to keeping all.")
                relevant_db = list(db_docs)
                db_reasons = [f"Grading fallback due to error: {e}" for _ in db_docs]

        # Compress only the relevant DB documents (do not compress temporal web search results)
        if relevant_db:
            try:
                relevant_db = await asyncio.to_thread(
                    compress_documents,
                    question,
                    relevant_db,
                    embedder._reranker,
                    threshold=settings.rerank_floor,
                    min_sentences=2,
                )
            except Exception as e:
                logger.warning(f"Document compression failed: {e}. Keeping uncompressed.")

        relevant = relevant_web + relevant_db
        state["grading_reasons"] = web_reasons + db_reasons

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
async def check_context_sufficiency(state: GraphState, config: dict = None) -> dict:
    """PageIndex-inspired iterative sufficiency check."""
    ollama = _services._ollama

    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Sufficiency check: bypassing for simple query tier")
        return {}

    intent = state.get("intent")
    if intent == "DISTRESS":
        logger.info("Sufficiency check: bypassing for DISTRESS intent")
        return {}

    await emit_status(config, "Checking if I have enough to answer well...")
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
async def enrich_context(state: GraphState, config: dict = None) -> dict:
    """Fetch neighbor chunks for the top relevant documents (RAG Made Simple Ch 8)."""
    relevant_docs = state.get("relevant_docs", [])
    qdrant = _services._qdrant

    if state.get("query_tier") in ("fast", "tier2_simple"):
        logger.info("Enrich context: bypassing for simple query tier")
        return {"relevant_docs": relevant_docs}

    if not relevant_docs or settings.rag_context_window <= 0:
        return {"relevant_docs": relevant_docs}

    await emit_status(config, "Gathering surrounding context...")
    enriched_docs = []
    seen_hashes = set()

    for doc in relevant_docs[:3]:
        source_url = doc.get("source_url")
        chunk_index = doc.get("chunk_index")

        # Bypass neighbor lookup for web search results since they are not in Qdrant
        if source_url and chunk_index is not None and doc.get("content_type") != "web_search":
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
