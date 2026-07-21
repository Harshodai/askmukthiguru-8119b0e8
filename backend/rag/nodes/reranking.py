"""Reranking, relevance grading, and context enrichment nodes."""

from __future__ import annotations

import asyncio
import logging
import re

from rag.compressor import compress_documents
from rag.states import GraphState
from rag.timeout_utils import get_node_timeout
from rag.tree_navigator import check_sufficiency
from rag.doc_utils import doc_text

from app.tracing import trace_rag_node
from . import _services
from .utils import _grounded_citation_urls, _trace_update, emit_status, log_metrics, settings

logger = logging.getLogger(__name__)


@trace_rag_node("rerank_documents")
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
            "fast": 3,
            "tier2_simple": 4,
            "standard": 5,
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

    # ponytail: Gap 2 — important_kwd post-rerank additive boost.
    if getattr(settings, "important_kwd_boost_enabled", True) and reranked_db:
        boost_per_term = getattr(settings, "important_kwd_boost_per_term", 0.2)
        query_terms = {t.lower() for t in re.findall(r"\b\w{3,}\b", question)}
        for doc in reranked_db:
            kwd_meta = doc.get("metadata", {}).get("important_kwd", [])
            if not kwd_meta:
                continue
            overlap = len({k.lower() for k in kwd_meta} & query_terms)
            if overlap > 0:
                doc["rerank_score"] = min(
                    doc.get("rerank_score", 0.0) + boost_per_term * overlap, 1.0
                )
        reranked_db.sort(key=lambda d: d.get("rerank_score", 0.0), reverse=True)

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


@trace_rag_node("grade_documents")
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

    # Adaptive-RAG confidence gate: reranker already confident → skip the LLM
    # grading round-trip entirely (scores are sigmoid-normalized to [0,1]).
    # DISTRESS intent is excluded: always continue through the full grading path.
    skip_conf = getattr(settings, "crag_skip_confidence", 0.75)
    if skip_conf > 0 and state.get("intent") != "DISTRESS":
        confident = [d for d in reranked_docs if d.get("rerank_score", 0.0) >= skip_conf]
        if len(confident) >= 2:
            relevant = confident[: settings.rag_top_k_rerank]
            state["grading_reasons"] = ["High-confidence rerank bypass" for _ in relevant]
            logger.info(
                f"CRAG batch: {len(confident)} docs >= {skip_conf} rerank confidence, "
                f"skipping LLM grading, accepted {len(relevant)} docs"
            )
            return {
                "relevant_docs": relevant,
                "evaluation_trace": _trace_update(
                    state,
                    relevant_count=len(relevant),
                    relevant_sources=_grounded_citation_urls(relevant),
                    grading_skipped_high_confidence=True,
                ),
            }

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
        # Grade ALL docs in a single batch LLM call (web + db combined)
        web_docs = [doc for doc in reranked_docs if doc.get("content_type") == "web_search"]
        db_docs = [doc for doc in reranked_docs if doc.get("content_type") != "web_search"]

        relevant_web = []
        relevant_db = []
        all_reasons = []

        all_docs = web_docs + db_docs
        if all_docs:
            try:
                doc_texts = [doc["text"] for doc in all_docs]
                t_out = get_node_timeout("grade_documents", 20.0)
                all_results = await ollama.grade_relevance(
                    question=question, doc_texts=doc_texts, timeout=t_out
                )
                for doc, res in zip(all_docs, all_results):
                    is_web = doc.get("content_type") == "web_search"
                    if res["relevant"]:
                        if is_web:
                            relevant_web.append(doc)
                        else:
                            relevant_db.append(doc)
                    all_reasons.append(res["reason"])
            except Exception as e:
                logger.warning(
                    f"Grading failed for all docs: {e}. Falling back to top-3 reranked docs."
                )
                top3 = all_docs[:3]
                for doc in top3:
                    if doc.get("content_type") == "web_search":
                        relevant_web.append(doc)
                    else:
                        relevant_db.append(doc)
                all_reasons = [f"Grading fallback: {e}" for _ in top3]

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
        state["grading_reasons"] = all_reasons

    # Compute context sufficiency from grading results (replaces separate check_context_sufficiency node)
    # Context is sufficient when at least 2 relevant docs exist with reasonable scores,
    # OR there are any relevant docs with scores above the high-confidence threshold.
    context_sufficient = True
    if relevant:
        high_conf_docs = [d for d in relevant if d.get("rerank_score", 0.0) >= 0.75]
        moderate_docs = [d for d in relevant if d.get("rerank_score", 0.0) >= 0.5]
        context_sufficient = len(high_conf_docs) >= 1 or len(moderate_docs) >= 2
    else:
        context_sufficient = False

    if reranked_docs:
        try:
            from app.metrics import RETRIEVAL_RELEVANCE_RATIO
            RETRIEVAL_RELEVANCE_RATIO.set(len(relevant) / len(reranked_docs))
        except Exception:
            pass

    logger.info(
        f"CRAG batch: {len(relevant)}/{len(reranked_docs)} docs passed relevance check "
        f"(context_sufficient={context_sufficient})"
    )
    return {
        "relevant_docs": relevant,
        "_context_sufficient": context_sufficient,
        "low_confidence_retrieval": not context_sufficient,
        "evaluation_trace": _trace_update(
            state,
            relevant_count=len(relevant),
            relevant_sources=_grounded_citation_urls(relevant),
        ),
    }




@trace_rag_node("enrich_context")
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
            h = hash(doc_text(doc)[:100])
            if h not in seen_hashes:
                seen_hashes.add(h)
                enriched_docs.append(doc)

    for doc in relevant_docs[3:]:
        h = hash(doc_text(doc)[:100])
        if h not in seen_hashes:
            seen_hashes.add(h)
            enriched_docs.append(doc)

    logger.info(
        f"Enriched {len(relevant_docs)} -> {len(enriched_docs)} chunks using window={settings.rag_context_window}"
    )
    return {"relevant_docs": enriched_docs}
