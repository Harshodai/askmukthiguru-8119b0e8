"""Query decomposition and hybrid document retrieval nodes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from rag.states import GraphState
from rag.timeout_utils import get_node_timeout
from rag.tree_navigator import navigate_tree
from services.cache_service import InMemoryCacheAdapter
from services.embedding_service import EmbeddingService
from services.lightrag_service import LightRAGService
from services.qdrant_service import QdrantService

from . import _services
from .utils import (
    _grounded_citation_urls,
    _llm_retrieval_expansions,
    _rrf_docs,
    _trace_update,
    emit_status,
    expand_query_with_synonyms,
    inject_doctrine_keywords,
    log_metrics,
    settings,
)

logger = logging.getLogger(__name__)

# Module-level semantic cache instance (lazy-initialized)
_semantic_cache: Optional[Any] = None


@log_metrics
async def decompose_query(state: GraphState, config: dict = None) -> dict:
    """Always decompose queries into sub-queries."""
    question = state["question"]
    ollama = _services._ollama

    if state.get("query_tier") in ("fast", "tier2_simple"):
        return {"sub_queries": [question], "is_complex": False}

    await emit_status(config, "Breaking the question into deeper parts...")
    t_out = get_node_timeout("decompose_query", 15)
    sub_queries = await ollama.decompose_query(question=question, timeout=t_out)
    is_complex = len(sub_queries) > 1
    expanded = [expand_query_with_synonyms(q) for q in sub_queries]
    logger.info(f"Decomposed into {len(sub_queries)} sub-queries (complex={is_complex})")
    return {"sub_queries": expanded, "is_complex": is_complex}


@log_metrics
async def generate_hyde(state: GraphState, config: dict = None) -> dict:
    """HyDE (Hypothetical Document Embeddings): Generate a fake answer."""
    ollama = _services._ollama

    if state.get("query_tier") in ("fast", "tier2_simple"):
        return {"hyde_text": None}

    if not settings.rag_use_hyde:
        return {"hyde_text": None}

    await emit_status(config, "Imagining the shape of the answer...")
    question = state.get("rewritten_query") or state["question"]
    t_out = get_node_timeout("generate_hyde", 30.0)
    hyde_text = await ollama.generate_hyde(question=question, timeout=t_out)
    logger.info(f"HyDE generated hypothetical answer ({len(hyde_text)} chars)")
    return {"hyde_text": hyde_text}


@log_metrics
async def navigate_knowledge_tree(state: GraphState, config: dict = None) -> dict:
    """PageIndex-inspired reasoning-based pre-retrieval."""
    question = state["question"]
    ollama = _services._ollama
    embedder = _services._embedder
    qdrant = _services._qdrant

    if state.get("query_tier") in ("fast", "tier2_simple"):
        return {"selected_clusters": []}

    await emit_status(config, "Walking the teaching graph...")
    try:
        query_enc = await asyncio.to_thread(embedder.encode_single_full, question)
        summary_nodes = qdrant.get_summary_nodes(query_vector=query_enc["dense"], limit=10)

        if not summary_nodes:
            logger.info("Tree navigation: No summary nodes in DB, skipping")
            return {"selected_clusters": []}

        t_out = get_node_timeout("navigate_knowledge_tree", 12)
        selected = await navigate_tree(
            question, summary_nodes, ollama, max_clusters=3, timeout=t_out, max_retries=1
        )
        return {"selected_clusters": selected}
    except Exception as e:
        logger.warning(
            f"navigate_knowledge_tree node failed/timed out: {e}. Searching all clusters."
        )
        return {"selected_clusters": []}


async def retrieve_for_single_query(
    query: str,
    chat_history: list,
    hyde_text: Optional[str],
    intent: str,
    selected_clusters: list,
    embedder: EmbeddingService,
    qdrant: QdrantService,
    lightrag: Optional[LightRAGService],
) -> list[dict]:
    """Retrieve documents for a single sub-query, decoupled from state."""
    augmented_query = query
    if chat_history:
        last_user_msgs = [m["content"] for m in chat_history[-4:] if m.get("role") == "user"]
        if last_user_msgs:
            augmented_query = f"{last_user_msgs[-1]} {query}"

    query_for_embedding = hyde_text or augmented_query
    query_embedding = await asyncio.to_thread(embedder.encode_single_full, query_for_embedding)

    summary_task = asyncio.to_thread(
        qdrant.search,
        query_vector=query_embedding["dense"],
        limit=2,
        sparse_vector=query_embedding["sparse"],
        raptor_level=1,
        query=query_for_embedding,
    )

    chunk_task = asyncio.to_thread(
        qdrant.search,
        query_vector=query_embedding["dense"],
        limit=settings.rag_top_k_retrieval,
        sparse_vector=query_embedding["sparse"],
        raptor_level=0,
        cluster_ids=selected_clusters if selected_clusters else None,
        query=query_for_embedding,
    )

    tasks = [summary_task, chunk_task]

    lightrag_index = -1
    if lightrag and intent in ["RELATIONAL", "FACTUAL", "QUERY"]:
        lightrag_index = len(tasks)
        t_out = get_node_timeout("default_fast", 30.0)
        tasks.append(
            asyncio.wait_for(
                lightrag.aquery(query, mode="hybrid", only_need_context=True),
                timeout=t_out,
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    summary_results = results[0] if not isinstance(results[0], Exception) else []
    chunk_results = results[1] if not isinstance(results[1], Exception) else []

    resolved_chunks = []
    seen_parents = set()
    for doc in chunk_results:
        parent_id = doc.get("parent_id")
        parent_text = doc.get("parent_text")

        if parent_id and parent_text:
            if parent_id not in seen_parents:
                seen_parents.add(parent_id)
                doc["text"] = parent_text
                resolved_chunks.append(doc)
        else:
            resolved_chunks.append(doc)

    chunk_results = resolved_chunks

    lightrag_results = []
    if lightrag_index != -1 and results[lightrag_index]:
        graph_answer = results[lightrag_index]
        if isinstance(graph_answer, (asyncio.TimeoutError, Exception)):
            logger.warning(f"LightRAG returned an exception (timeout or error): {graph_answer}")
            graph_answer = ""
        if graph_answer and isinstance(graph_answer, str):
            seen_lg: set[str] = set()
            deduped_lines: list[str] = []
            for lg_line in graph_answer.splitlines():
                key = lg_line.strip()
                if key and key not in seen_lg:
                    seen_lg.add(key)
                    deduped_lines.append(lg_line)
                elif not key:
                    deduped_lines.append(lg_line)
            graph_answer = "\n".join(deduped_lines)
            lg_node_lines = [line for line in deduped_lines if line.strip()]
            if len(lg_node_lines) > 50:
                graph_answer = "\n".join(deduped_lines[:50]) + "\n[LightRAG context capped at 5 nodes]"
            lightrag_results.append(
                {
                    "text": graph_answer,
                    "title": "Knowledge Graph (LightRAG)",
                    "source_url": "knowledge_graph",
                    "content_type": "graph_summary",
                    "chunk_index": 0,
                    "raptor_level": 0,
                    "score": 1.0,
                }
            )

    rrf_ranked = _rrf_docs([summary_results, chunk_results], k=60)
    merged = lightrag_results + rrf_ranked

    seen: set[int] = set()
    deduped: list[dict] = []
    for doc in merged:
        th = hash(doc["text"][:120])
        if th not in seen:
            seen.add(th)
            deduped.append(doc)

    logger.debug(
        f"RRF merge: summaries={len(summary_results)} chunks={len(chunk_results)} "
        f"graph={len(lightrag_results)} -> {len(deduped)} unique docs"
    )
    return deduped


@log_metrics
async def retrieve_documents(state: GraphState, config: dict = None) -> dict:
    """Two-phase hybrid retrieval from Qdrant."""
    from .utils import _require_state
    contract_err = _require_state(state, ["question"])
    if contract_err:
        return contract_err

    query_tier = state.get("query_tier", "standard")
    configurable = {}
    global _semantic_cache

    if getattr(settings, "SEMANTIC_CACHE_ENABLED", True):
        query = state.get("rewritten_query") or state["question"]
        if _semantic_cache is None:
            _semantic_cache = InMemoryCacheAdapter()
        cached = _semantic_cache.get(query)
        if cached:
            logger.info("Cache HIT in retrieve_documents — returning cached answer")
            return {
                "answer": cached["response"],
                "citations": cached.get("citations", []),
                "intent": cached.get("intent", "QUERY"),
                "cache_hit": True,
            }
    if config:
        if hasattr(config, "get"):
            configurable = config.get("configurable", {})
        elif hasattr(config, "configurable"):
            configurable = config.configurable
    stream_queue = configurable.get("stream_queue")
    if stream_queue:
        await stream_queue.put({"event": "status", "data": "Searching knowledge base..."})

    base_question = state.get("rewritten_query") or state["question"]
    # Doctrine keyword injection & synonym expansion for better retrieval
    base_question = inject_doctrine_keywords(expand_query_with_synonyms(base_question))
    sub_queries = state.get("sub_queries", [base_question]) or [base_question]

    # OPTIMIZATION (Phase-3 / Truth-3): Fire LLM expansion CONCURRENTLY with
    # the first retrieval batch instead of awaiting it serially. The
    # expansion call is ~2s on the fast model; running it in parallel with
    # the primary retrievals (which take ~1-3s themselves) hides that
    # latency entirely in 80% of cases.
    #
    # Ordering preserved: primary sub_queries retrieved first, then any
    # expansion-generated queries (capped at 6 total). RRF reranking later
    # is order-independent so this does not change the result set quality.
    #
    # --- LEGACY (preserved per "do not delete, just comment") ---
    # expansion_queries: list[str] = await _llm_retrieval_expansions(state)
    # if expansion_queries:
    #     logger.info(...)
    # sub_queries = list(dict.fromkeys([*sub_queries, *expansion_queries]))
    # ------------------------------------------------------------
    expansion_task = asyncio.create_task(_llm_retrieval_expansions(state))

    chat_history = state.get("chat_history", [])
    selected_clusters = state.get("selected_clusters", [])
    hyde_text = state.get("hyde_text")
    intent = state.get("intent", "FACTUAL")
    embedder = _services._embedder
    qdrant = _services._qdrant
    lightrag = _services._lightrag

    primary_queries = list(dict.fromkeys(sub_queries))[:6]
    primary_results = await asyncio.gather(
        *[
            asyncio.wait_for(
                retrieve_for_single_query(
                    q,
                    chat_history,
                    hyde_text,
                    intent,
                    selected_clusters,
                    embedder,
                    qdrant,
                    lightrag if query_tier != "fast" else None,
                ),
                timeout=get_node_timeout("default_main", getattr(settings, "node_timeout_main", 60)),
            )
            for q in primary_queries
        ],
        return_exceptions=True,
    )

    # Now consume the (likely already-completed) expansion task.
    # Cap total retrievals at 6 to bound LLM/Qdrant load.
    try:
        expansion_queries = await expansion_task
    except Exception as exp_err:
        logger.warning(f"LLM retrieval expansion failed (non-fatal): {exp_err}")
        expansion_queries = []

    expansion_results: list = []
    remaining_budget = max(0, 6 - len(primary_queries))
    if expansion_queries and remaining_budget > 0:
        # Dedupe against the queries we already ran
        already = set(primary_queries)
        novel_expansions = [q for q in expansion_queries if q not in already][:remaining_budget]
        if novel_expansions:
            logger.info(
                f"LLM retrieval planner: adding {len(novel_expansions)} expansion query/queries "
                f"(parallel-fire saved up to ~{round(2.0)}s vs serial)"
            )
            expansion_results = await asyncio.gather(
                *[
                    asyncio.wait_for(
                        retrieve_for_single_query(
                            q,
                            chat_history,
                            hyde_text,
                            intent,
                            selected_clusters,
                            embedder,
                            qdrant,
                            lightrag if query_tier != "fast" else None,
                        ),
                        timeout=get_node_timeout("default_main", getattr(settings, "node_timeout_main", 60)),
                    )
                    for q in novel_expansions
                ],
                return_exceptions=True,
            )

    # Keep `sub_queries` populated for downstream nodes / observability
    sub_queries = list(dict.fromkeys([*primary_queries, *(expansion_queries or [])]))
    retrieval_queries = primary_queries + [
        q for q in (expansion_queries or []) if q not in set(primary_queries)
    ][: max(0, 6 - len(primary_queries))]
    all_results = list(primary_results) + list(expansion_results)

    normalized_results = []
    for res in all_results:
        if isinstance(res, Exception):
            logger.warning(f"Sub-query retrieval failed but pipeline will continue: {res}")
            normalized_results.append([])
        else:
            normalized_results.append(res)
    all_results = normalized_results

    _RRF_K2 = 60
    rrf2_scores: dict[int, float] = {}
    id_to_doc2: dict[int, dict] = {}

    for results in all_results:
        for rank, doc in enumerate(results):
            key = id(doc)
            id_to_doc2[key] = doc
            rrf2_scores[key] = rrf2_scores.get(key, 0.0) + 1.0 / (_RRF_K2 + rank + 1)

    seen_texts: set[int] = set()
    all_docs: list[dict] = []
    for doc in sorted(id_to_doc2.values(), key=lambda d: rrf2_scores[id(d)], reverse=True):
        th = hash(doc["text"][:100])
        if th not in seen_texts:
            seen_texts.add(th)
            all_docs.append(doc)

    if len(all_docs) < 3:
        logger.info(f"Low document count ({len(all_docs)}), triggering broader fallback search...")
        fallback_query = sub_queries[0]
        query_embedding = await asyncio.to_thread(embedder.encode_single_full, fallback_query)

        fallback_results = await asyncio.to_thread(
            qdrant.search,
            query_vector=query_embedding["dense"],
            limit=10,
            sparse_vector=query_embedding["sparse"],
            raptor_level=0,
            cluster_ids=None,
        )

        for doc in fallback_results:
            text_hash = hash(doc["text"][:100])
            if text_hash not in seen_texts:
                seen_texts.add(text_hash)
                all_docs.append(doc)

        logger.info(
            f"Fallback search added {len(all_docs) - (len(all_docs) - len(fallback_results))} docs. Total: {len(all_docs)}"
        )

    if len(all_docs) > settings.rag_top_k_retrieval:
        question = state.get("rewritten_query") or state["question"]
        doc_texts = [doc["text"] for doc in all_docs]

        batch_enc = await asyncio.to_thread(embedder.encode_batch, doc_texts)
        doc_embeddings = batch_enc["dense"]

        query_enc = await asyncio.to_thread(embedder.encode_single_full, question)
        query_emb = query_enc["dense"]

        all_docs = qdrant.mmr_select(
            query_embedding=query_emb,
            documents=all_docs,
            doc_embeddings=doc_embeddings,
            top_k=settings.rag_top_k_retrieval,
            lambda_param=0.7,
        )

    logger.info(f"Retrieved {len(all_docs)} unique documents (two-phase hybrid, parallel)")
    return {
        "documents": all_docs,
        "evaluation_trace": _trace_update(
            state,
            retrieval_queries=retrieval_queries,
            retrieved_count=len(all_docs),
            llm_expansion_count=len(expansion_queries),
            retrieved_sources=_grounded_citation_urls(all_docs),
        ),
    }


def route_sub_queries(state: GraphState) -> list[Send]:  # noqa: F821 — Send imported lazily inside function body to avoid module-load cost
    """Fan-out router: spawn one retrieve_single branch per sub-query via Send."""
    from langgraph.types import Send
    sub_queries = state.get("sub_queries") or [state["question"]]
    chat_history = state.get("chat_history", [])
    hyde_text = state.get("hyde_text")
    intent = state.get("intent", "FACTUAL")
    selected_clusters = state.get("selected_clusters", [])

    logger.info(f"route_sub_queries: dispatching {len(sub_queries)} parallel branch(es) via Send")

    return [
        Send(
            "retrieve_single",
            {
                "question": state["question"],
                "chat_history": chat_history,
                "sub_query": q,
                "hyde_text": hyde_text,
                "intent": intent,
                "selected_clusters": selected_clusters,
                "request_id": state.get("request_id"),
                "user_id": state.get("user_id"),
                "query_tier": state.get("query_tier"),
                "sub_results": [],
            },
        )
        for q in sub_queries
    ]


@log_metrics
async def retrieve_single(state: GraphState) -> dict:
    """Branch node: retrieve documents for ONE sub-query."""
    sub_query: str = state.get("sub_query") or state["question"]
    embedder = _services._embedder
    qdrant = _services._qdrant
    lightrag = _services._lightrag

    docs = await retrieve_for_single_query(
        query=sub_query,
        chat_history=state.get("chat_history", []),
        hyde_text=state.get("hyde_text"),
        intent=state.get("intent", "FACTUAL"),
        selected_clusters=state.get("selected_clusters", []),
        embedder=embedder,
        qdrant=qdrant,
        lightrag=lightrag,
    )

    logger.debug(f"retrieve_single[{sub_query[:40]}]: {len(docs)} docs retrieved")
    return {"sub_results": docs}


@log_metrics
async def merge_sub_results(state: GraphState) -> dict:
    """Fan-in node: collect all per-branch results and apply two-level RRF."""
    all_results: list[list[dict]] = state.get("sub_results", [])
    embedder = _services._embedder
    qdrant = _services._qdrant

    if not all_results:
        logger.warning("merge_sub_results: no sub_results to merge, returning empty")
        return {"documents": []}

    rrf_ranked = _rrf_docs(all_results, k=60)

    seen: set[int] = set()
    all_docs: list[dict] = []
    for doc in rrf_ranked:
        th = hash(doc["text"][:100])
        if th not in seen:
            seen.add(th)
            all_docs.append(doc)

    if len(all_docs) < 3:
        logger.info(f"merge_sub_results: only {len(all_docs)} docs, triggering fallback search")
        fallback_query = state.get("sub_queries", [state["question"]])[0]
        query_embedding = await asyncio.to_thread(embedder.encode_single_full, fallback_query)
        fallback_results = await asyncio.to_thread(
            qdrant.search,
            query_vector=query_embedding["dense"],
            limit=10,
            sparse_vector=query_embedding["sparse"],
            raptor_level=0,
            cluster_ids=None,
        )
        for doc in fallback_results:
            th = hash(doc["text"][:100])
            if th not in seen:
                seen.add(th)
                all_docs.append(doc)

    if len(all_docs) > settings.rag_top_k_retrieval:
        question = state.get("rewritten_query") or state["question"]
        doc_texts = [doc["text"] for doc in all_docs]
        batch_enc = await asyncio.to_thread(embedder.encode_batch, doc_texts)
        doc_embeddings = batch_enc["dense"]
        query_enc = await asyncio.to_thread(embedder.encode_single_full, question)
        query_emb = query_enc["dense"]
        all_docs = qdrant.mmr_select(
            query_embedding=query_emb,
            documents=all_docs,
            doc_embeddings=doc_embeddings,
            top_k=settings.rag_top_k_retrieval,
            lambda_param=0.7,
        )

    logger.info(
        f"merge_sub_results: {len(all_results)} branch(es) -> {len(all_docs)} unique docs (RRF + MMR applied)"
    )
    return {"documents": all_docs}
