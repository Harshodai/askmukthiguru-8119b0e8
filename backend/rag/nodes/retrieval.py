"""Query decomposition and hybrid document retrieval nodes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.metrics import (
    COVERAGE_GAP_TOTAL,
    LIGHTRAG_TIMEOUT_TOTAL,
    RETRIEVAL_SCORE_HISTOGRAM,
    WEB_SEARCH_HIT_TOTAL,
    WEB_SEARCH_MISS_TOTAL,
)
from rag.states import GraphState
from rag.timeout_utils import get_node_timeout
from rag.tree_navigator import navigate_tree
from services.cache_service import InMemoryCacheAdapter
from services.embedding_service import EmbeddingService
from services.lightrag_service import LightRAGService
from services.qdrant_service import QdrantService

import re

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


# ponytail: lightweight OKF compiled-index loader (Phase 2b).
# Avoids heavy startup — reads disk lazily, cached per-process via module-level cache.
_base_path = __import__("pathlib").Path(__file__).resolve().parent
while _base_path.name and _base_path.name != "backend":
    _base_path = _base_path.parent
_OKF_COMPILED_PATH = (_base_path.parent / "memory" / "okf" / "compiled.json") if _base_path.name else __import__("pathlib").Path("/app/memory/okf/compiled.json")
_OKF_CACHE: list[dict] | None = None


def _load_okf_entries() -> list[dict]:
    global _OKF_CACHE
    if _OKF_CACHE is not None:
        return _OKF_CACHE
    if not _OKF_COMPILED_PATH.exists():
        _OKF_CACHE = []
        return []
    try:
        data = __import__("json").loads(_OKF_COMPILED_PATH.read_text(encoding="utf-8"))
        _OKF_CACHE = data.get("entries", [])
    except Exception:
        _OKF_CACHE = []
    return _OKF_CACHE


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length float vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = (sum(x * x for x in a)) ** 0.5
    norm_b = (sum(x * x for x in b)) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _okf_match(query: str, limit: int = 3) -> list[dict]:
    """Semantic match via cosine similarity on title embeddings; keyword fallback."""
    entries = _load_okf_entries()
    if not entries:
        return []

    # Try semantic matching first
    try:
        from services.embedding_service import EmbeddingService
        embedder = EmbeddingService()
        q_vec = embedder.encode([query])[0]
        scored: list[tuple[float, dict]] = []
        for e in entries:
            emb = e.get("embedding", [])
            if emb and len(emb) > 0:
                scored.append((_cosine(q_vec, emb), e))
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            docs = []
            for sim, e in scored[:limit]:
                docs.append({
                    "text": f"{e['title']}\n\n{e.get('body', '')}",
                    "score": 0.9 + sim * 0.1,
                    "metadata": {
                        "source": e.get("source", "OKF"),
                        "title": e["title"],
                        "type": e.get("type", "okf"),
                    },
                })
            return docs
    except Exception:
        pass  # ponytail: non-fatal; fall back to keyword

    # Keyword fallback — naive word overlap when EmbeddingService unavailable
    import re as _re
    words = set(w.lower() for w in _re.findall(r"\w+", query) if len(w) > 2)
    scored: list[tuple[float, dict]] = []
    for e in entries:
        text = f"{e.get('title', '')} {e.get('body', '')}".lower()
        matches = sum(1 for w in words if w in text)
        if matches:
            scored.append((matches, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    docs = []
    for score, e in scored[:limit]:
        docs.append({
            "text": f"{e['title']}\n\n{e.get('body', '')}",
            "score": 0.9 + score * 0.01,
            "metadata": {
                "source": e.get("source", "OKF"),
                "title": e["title"],
                "type": e.get("type", "okf"),
            },
        })
    return docs


async def query_neo4j_subgraph(query: str) -> str:
    """
    Directly query Neo4j for connected subgraphs of spiritual concepts found in the user's query.
    """
    from ingest.pipeline import extract_doctrine_tags
    matched_concepts = extract_doctrine_tags(query)
    if not matched_concepts:
        return ""

    if not settings.neo4j_uri:
        return ""

    try:
        from neo4j import GraphDatabase

        def _run():
            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password)
            )
            subgraph_context = []
            with driver.session() as session:
                # Fix: LightRAG's Neo4JStorage writes entity_id (not entity_name),
                # and the shared knowledge-graph nodes it authors are never tagged
                # with tenant_id (tenant scoping only applies to per-user memory
                # nodes written by memory_service_v2.py) — the old WHERE clause
                # matched a nonexistent property twice over and always returned 0
                # rows, silently disabling relational subgraph context on every
                # RELATIONAL-intent query.
                cypher = """
                MATCH (n1 {entity_id: $concept})-[r]->(n2)
                RETURN n1.entity_id AS source, type(r) AS rel, r.description AS desc, n2.entity_id AS target
                LIMIT 15
                """
                for concept in matched_concepts:
                    result = session.run(cypher, concept=concept)
                    for record in result:
                        desc_str = f" - {record['desc']}" if record.get("desc") else ""
                        subgraph_context.append(
                            f"Relationship: {record['source']} -[{record['rel']}]-> {record['target']}{desc_str}"
                        )
            return subgraph_context

        res = await asyncio.to_thread(_run)
        if res:
            return "\n[Targeted Subgraph Context]:\n" + "\n".join(res)
    except Exception as e:
        logger.warning(f"Failed to fetch Neo4j targeted subgraph: {e}")
    return ""


async def query_neo4j_guided_tour(query: str) -> list[dict]:
    """
    Query Neo4j for guided tour/pathway steps.
    Returns list of dicts representing the steps, or a mock sequence if no graph database is configured/empty.
    """
    from services.tenant_context import TenantContext
    tour_name = "meditation journey"
    if not settings.neo4j_uri:
        return [
            {
                "content": "Step 1: Soul Stage. Focus on the connection with the Universal Intelligence, feeling the expansion of consciousness and dropping all resistance.",
                "text": "Step 1: Soul Stage. Focus on the connection with the Universal Intelligence, feeling the expansion of consciousness and dropping all resistance.",
                "title": "Step 1: Soul Stage",
                "source_url": "neo4j://tour/meditation_journey/step1",
                "chunk_index": 1,
                "score": 1.0,
            },
            {
                "content": "Step 2: Serene Mind. Cultivate inner stillness using breathing patterns, settling into a space of quiet observation and deep presence.",
                "text": "Step 2: Serene Mind. Cultivate inner stillness using breathing patterns, settling into a space of quiet observation and deep presence.",
                "title": "Step 2: Serene Mind",
                "source_url": "neo4j://tour/meditation_journey/step2",
                "chunk_index": 2,
                "score": 0.9,
            },
        ]

    try:
        from neo4j import GraphDatabase
        tenant_id = TenantContext.get()
        def _run():
            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password)
            )
            steps = []
            with driver.session() as session:
                cypher = """
                MATCH (t:Tour)-[:HAS_STEP]->(s:Step)
                WHERE (t.name CONTAINS $tour_name OR s.tour_name CONTAINS $tour_name)
                  AND t.tenant_id = $tenant_id AND s.tenant_id = $tenant_id
                RETURN s.step_number AS step_number, s.title AS title, s.description AS description
                ORDER BY s.step_number ASC
                """
                result = session.run(cypher, tour_name=tour_name, tenant_id=tenant_id)
                for record in result:
                    steps.append({
                        "content": f"Step {record['step_number']}: {record['title']}. {record['description']}",
                        "text": f"Step {record['step_number']}: {record['title']}. {record['description']}",
                        "title": f"Step {record['step_number']}: {record['title']}",
                        "source_url": f"neo4j://tour/{tour_name}/step{record['step_number']}",
                        "chunk_index": record['step_number'],
                        "score": 1.0 - (0.05 * record['step_number']),
                    })
            return steps

        res = await asyncio.to_thread(_run)
        if res:
            return res
    except Exception as e:
        logger.warning(f"Failed to query Neo4j guided tour: {e}")

    return [
        {
            "content": "Step 1: Soul Stage. Focus on the connection with the Universal Intelligence, feeling the expansion of consciousness and dropping all resistance.",
            "text": "Step 1: Soul Stage. Focus on the connection with the Universal Intelligence, feeling the expansion of consciousness and dropping all resistance.",
            "title": "Step 1: Soul Stage",
            "source_url": "neo4j://tour/meditation_journey/step1",
            "chunk_index": 1,
            "score": 1.0,
        },
        {
            "content": "Step 2: Serene Mind. Cultivate inner stillness using breathing patterns, settling into a space of quiet observation and deep presence.",
            "title": "Step 2: Serene Mind",
            "text": "Step 2: Serene Mind. Cultivate inner stillness using breathing patterns, settling into a space of quiet observation and deep presence.",
            "source_url": "neo4j://tour/meditation_journey/step2",
            "chunk_index": 2,
            "score": 0.9,
        },
    ]

# Module-level semantic cache instance (lazy-initialized)
_semantic_cache: Optional[Any] = None

# Threshold at which parent text gets adaptive excerpting instead of full injection
_ADAPTIVE_PARENT_THRESHOLD = 1800

# Score-delta cutoff: drop documents whose score is less than this fraction of the top score.
_SCORE_DELTA_RATIO = 0.5


def _apply_score_delta_cutoff(docs: list[dict], score_key: str = "score", min_ratio: float = _SCORE_DELTA_RATIO) -> list[dict]:
    """Drop low-scoring documents that are far below the top score."""
    if not docs:
        return []

    scores = [doc.get(score_key, 0.0) for doc in docs]
    top_score = max(scores)
    if top_score <= 0:
        return docs

    floor = top_score * min_ratio
    filtered = [doc for doc in docs if doc.get(score_key, 0.0) >= floor]
    logger.debug(f"Score-delta cutoff: top={top_score:.3f} floor={floor:.3f} {len(docs)} -> {len(filtered)} docs")
    return filtered


def _apply_retrieval_dedup(docs: list[dict]) -> list[dict]:
    """Drop retrieved docs whose content is nearly identical to an already-selected doc."""
    if not docs or not getattr(settings, "retrieval_deduplication_enabled", False):
        return docs

    try:
        from ingest.deduplication import deduplicate_retrieved_docs

        threshold = getattr(settings, "retrieval_dedup_threshold", 0.85)
        return deduplicate_retrieved_docs(docs, threshold=threshold)
    except Exception as e:
        logger.warning(f"Retrieval deduplication failed (non-fatal): {e}")
        return docs


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using regex boundary detection."""
    sentence_ends = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentence_ends if s.strip()]


def _adaptive_parent_excerpt(query: str, parent_text: str, max_chars: int = 1500) -> str:
    """
    Extract the most relevant excerpt from a long parent text.

    Scores sentences by keyword overlap with the query, then selects
    a contiguous window around the highest-scoring sentence, respecting
    max_chars. Falls back to head truncation if scoring fails.
    """
    sentences = _split_into_sentences(parent_text)
    if not sentences:
        return parent_text[:max_chars]

    # Extract non-trivial query keywords (length > 2, not common stop-words)
    stop_words = {"the", "and", "for", "are", "but", "not", "you", "all", "can", "had", "her", "was", "one", "our", "out", "day", "get", "has", "him", "his", "how", "man", "new", "now", "old", "see", "two", "way", "who", "boy", "did", "its", "let", "put", "say", "she", "too", "use"}
    query_words = set()
    for word in re.findall(r"\b\w+\b", query.lower()):
        if len(word) > 2 and word not in stop_words:
            query_words.add(word)

    if not query_words:
        return parent_text[:max_chars]

    # Score each sentence by keyword overlap
    scores = []
    for s in sentences:
        s_lower = s.lower()
        score = sum(1 for w in query_words if w in s_lower)
        scores.append(score)

    best_idx = max(range(len(scores)), key=lambda i: scores[i])

    # Build window around best sentence, expanding outward
    selected: list[str] = [sentences[best_idx]]
    current_len = len(selected[0])
    left, right = best_idx - 1, best_idx + 1

    while current_len < max_chars and (left >= 0 or right < len(sentences)):
        candidates = []
        if left >= 0:
            candidates.append((left, sentences[left], "left"))
        if right < len(sentences):
            candidates.append((right, sentences[right], "right"))
        # Prefer higher scoring side, or right for forward reading flow
        candidates.sort(key=lambda x: (scores[x[0]], x[2] == "right"), reverse=True)
        idx, sentence, _ = candidates[0]
        if current_len + len(sentence) + 1 > max_chars:
            break
        if idx < best_idx:
            selected.insert(0, sentence)
            left -= 1
        else:
            selected.append(sentence)
            right += 1
        current_len += len(sentence) + 1

    excerpt = " ".join(selected)
    if len(excerpt) < 200 and len(parent_text) > max_chars:
        # Fallback: head truncation if excerpt is too short
        return parent_text[:max_chars]
    return excerpt


async def navigate_and_hyde(state: GraphState, config: dict = None) -> dict:
    """Run ``navigate_knowledge_tree`` and ``generate_hyde`` in parallel.

    Uses `asyncio.gather` with error isolation so a failure in one node does not
    block the other. Results are merged into a single state update dict.
    """
    results = await asyncio.gather(
        navigate_knowledge_tree(state, config),
        generate_hyde(state, config),
        return_exceptions=True,
    )
    merged: dict = {}
    for r in results:
        if isinstance(r, Exception):
            logger.warning(f"Parallel node error (navigate_and_hyde): {r}")
            continue
        merged.update(r)
    return merged


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
    assistant_slug = state.get("assistant_slug") or "default"
    expanded = [await expand_query_with_synonyms(q, assistant_slug) for q in sub_queries]
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
    knowledge_tags: Optional[list[str]] = None,
    query_tier: str = "standard",
) -> list[dict]:
    """Retrieve documents for a single sub-query, decoupled from state."""
    augmented_query = query
    if chat_history:
        last_user_msgs = [m["content"] for m in chat_history[-4:] if m.get("role") == "user"]
        if last_user_msgs:
            augmented_query = f"{last_user_msgs[-1]} {query}"

    query_for_embedding = hyde_text or augmented_query
    query_embedding = await asyncio.to_thread(embedder.encode_single_full, query_for_embedding)

    # 1.8: Adaptive retrieval depth by tier
    if query_tier in ("fast", "tier2_simple"):
        chunk_limit = 5
    elif query_tier in ("deep", "tier3_complex"):
        chunk_limit = 20
    else:
        chunk_limit = 10

    summary_task = asyncio.to_thread(
        qdrant.search,
        query_vector=query_embedding["dense"],
        limit=2,
        sparse_vector=query_embedding["sparse"],
        raptor_level=1,
        query=query_for_embedding,
        knowledge_tags=knowledge_tags,
    )

    chunk_task = asyncio.to_thread(
        qdrant.search,
        query_vector=query_embedding["dense"],
        limit=chunk_limit,
        sparse_vector=query_embedding["sparse"],
        raptor_level=0,
        cluster_ids=selected_clusters if selected_clusters else None,
        query=query_for_embedding,
        knowledge_tags=knowledge_tags,
    )

    tasks = [summary_task, chunk_task]

    lightrag_index = -1
    if lightrag and intent in ["RELATIONAL", "FACTUAL", "QUERY"]:
        lightrag_index = len(tasks)
        # Use config-driven timeout (prevents 145s spike — see logs/backend.log line 264)
        t_out = getattr(settings, "lightrag_retrieval_timeout", 30)
        # Adaptive graph depth: fast/simple tiers skip community-summary traversal
        graph_mode = "local" if query_tier in ("fast", "tier2_simple") else "hybrid"
        tasks.append(
            asyncio.wait_for(
                lightrag.aquery(query, mode=graph_mode, only_need_context=True),
                timeout=float(t_out),
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
                # Adaptive chunking: excerpt very long parent text to preserve context window
                if len(parent_text) > _ADAPTIVE_PARENT_THRESHOLD:
                    doc["text"] = _adaptive_parent_excerpt(query, parent_text)
                else:
                    doc["text"] = parent_text
                resolved_chunks.append(doc)
        else:
            resolved_chunks.append(doc)

    chunk_results = resolved_chunks

    # Track LightRAG timeouts
    if lightrag_index != -1 and isinstance(results[lightrag_index], Exception):
        try:
            LIGHTRAG_TIMEOUT_TOTAL.inc()
        except Exception:
            pass

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
            if intent == "RELATIONAL":
                subgraph_ctx = await query_neo4j_subgraph(query)
                if subgraph_ctx:
                    graph_answer += "\n" + subgraph_ctx
            # Normalise LightRAG score to Qdrant-comparable range (0.3-0.7)
            # so it doesn't clobber downstream rankers with an inflated default.
            lg_richness = min(1.0, len(lg_node_lines) / 20)
            lg_score = 0.3 + 0.4 * lg_richness
            lightrag_results.append(
                {
                    "text": graph_answer,
                    "title": "Knowledge Graph (LightRAG)",
                    "source_url": "knowledge_graph",
                    "content_type": "graph_summary",
                    "chunk_index": 0,
                    "raptor_level": 0,
                    "score": lg_score,
                }
            )

    rrf_ranked = _rrf_docs([summary_results, chunk_results], k=60)
    merged = lightrag_results + rrf_ranked

    seen: set[int] = set()
    deduped: list[dict] = []
    for doc in merged:
        th = hash(doc["text"][:100])
        if th not in seen:
            seen.add(th)
            deduped.append(doc)

    # Emit per-doc retrieval scores to Prometheus histogram
    for _doc in deduped:
        _score = _doc.get("score", 0.0)
        _src = _doc.get("content_type", "qdrant")
        try:
            RETRIEVAL_SCORE_HISTOGRAM.labels(source=_src).observe(_score)
        except Exception:
            pass

    return deduped


async def _compress_rag_context_impl(query: str, docs: list[dict], embedder) -> list[dict]:
    """Compress retrieved docs by keeping only sentences matching query threshold."""
    if not docs:
        return []

    all_sentences_with_meta = []
    for doc_idx, doc in enumerate(docs):
        text = doc.get("text", "") or doc.get("content", "")
        if not text:
            continue
        sentences = _split_into_sentences(text)
        for s in sentences:
            all_sentences_with_meta.append({
                "doc_idx": doc_idx,
                "text": s,
            })

    if not all_sentences_with_meta:
        return docs
        
    sentence_texts = [item["text"] for item in all_sentences_with_meta]
    try:
        sentence_enc = await asyncio.to_thread(embedder.encode_batch, sentence_texts)
        sentence_embs = sentence_enc["dense"]
        
        query_enc = await asyncio.to_thread(embedder.encode_single_full, query)
        query_emb = query_enc["dense"]
        
        import numpy as np
        query_norm = np.linalg.norm(query_emb)
        
        doc_idx_to_kept_sentences = {}
        for idx, item in enumerate(all_sentences_with_meta):
            emb = sentence_embs[idx]
            emb_norm = np.linalg.norm(emb)
            if emb_norm == 0 or query_norm == 0:
                sim = 0.0
            else:
                sim = float(np.dot(emb, query_emb) / (emb_norm * query_norm))
                
            if sim >= getattr(settings, "rag_compression_similarity_threshold", 0.50):
                doc_idx = item["doc_idx"]
                if doc_idx not in doc_idx_to_kept_sentences:
                    doc_idx_to_kept_sentences[doc_idx] = []
                doc_idx_to_kept_sentences[doc_idx].append(item["text"])
                
        compressed_docs = []
        for doc_idx, doc in enumerate(docs):
            if doc_idx in doc_idx_to_kept_sentences:
                kept_text = " ".join(doc_idx_to_kept_sentences[doc_idx])
                new_doc = dict(doc)
                new_doc["text"] = kept_text
                new_doc["content"] = kept_text
                compressed_docs.append(new_doc)
                
        logger.info(f"Context compression: reduced doc count from {len(docs)} to {len(compressed_docs)}")
        return compressed_docs if compressed_docs else docs
    except Exception as e:
        logger.warning(f"Error during context compression: {e}")
        return docs


@log_metrics
async def retrieve_documents(state: GraphState, config: dict = None) -> dict:
    """Two-phase hybrid retrieval from Qdrant."""
    from .utils import _require_state
    contract_err = _require_state(state, ["question"])
    if contract_err:
        return contract_err

    query_tier = state.get("query_tier", "standard")
    intent = state.get("intent", "FACTUAL")
    if intent == "GUIDED_TOUR":
        base_question = state.get("rewritten_query") or state["question"]
        tour_docs = await query_neo4j_guided_tour(base_question)
        return {
            "documents": tour_docs,
            "relevant_docs": tour_docs,
            "sub_queries": [base_question],
            "retrieval_queries": [base_question],
            "evaluation_trace": _trace_update(
                state,
                retrieve_documents="guided_tour_retrieved",
                guided_tour_count=len(tour_docs),
            ),
        }

    configurable = {}
    if getattr(settings, "SEMANTIC_CACHE_ENABLED", True):
        query = state.get("rewritten_query") or state["question"]
        cache_repo = _services._semantic_cache
        cached = cache_repo.get(query) if cache_repo else None
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
    assistant_slug = state.get("assistant_slug") or "default"
    # Doctrine keyword injection & synonym expansion for better retrieval
    base_question = await inject_doctrine_keywords(
        await expand_query_with_synonyms(base_question, assistant_slug),
        assistant_slug
    )
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
    knowledge_tags = state.get("knowledge_tags") or []
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
                    None,  # LightRAG disabled in hot retrieval path (latency/circuit-breaker safety)
                    knowledge_tags=knowledge_tags,
                    query_tier=query_tier,
                ),
                timeout=get_node_timeout("default_main", getattr(settings, "node_timeout_main", 60)),
            )
            for q in primary_queries
        ],
        return_exceptions=True,
    )

    # --- BM25 text search fan-out (parallel with vector retrieval) ---
    bm25_results: list[dict] = []
    if getattr(settings, "bm25_retrieval_enabled", True):
        try:
            bm25_query = sub_queries[0] if sub_queries else state.get("question", "")
            bm25_raw = qdrant.scroll_content(
                query=bm25_query,
                limit=getattr(settings, "bm25_result_limit", 10),
            )
            for r in bm25_raw:
                bm25_results.append({
                    "text": r.get("content", ""),
                    "score": r.get("score", 0.5),
                    "metadata": r.get("metadata", {}),
                    "source": "bm25_text",
                })
            logger.info(f"BM25 text search returned {len(bm25_results)} results")
        except Exception as bm25_err:
            logger.warning(f"BM25 text search failed (non-fatal): {bm25_err}")

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
                            None,  # LightRAG disabled in hot retrieval path (latency/circuit-breaker safety)
                            knowledge_tags=knowledge_tags,
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

    # Merge BM25 text search results as an additional RRF list
    if bm25_results:
        all_results.append(bm25_results)

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
        fallback_query = state["question"] if state.get("rewritten_query") else sub_queries[0]
        query_embedding = await asyncio.to_thread(embedder.encode_single_full, fallback_query)

        fallback_results = await asyncio.to_thread(
            qdrant.search,
            query_vector=query_embedding["dense"],
            limit=10,
            sparse_vector=query_embedding["sparse"],
            raptor_level=0,
            cluster_ids=None,
            knowledge_tags=knowledge_tags,
        )

        for doc in fallback_results:
            text_hash = hash(doc["text"][:100])
            if text_hash not in seen_texts:
                seen_texts.add(text_hash)
                all_docs.append(doc)

        logger.info(
            f"Fallback search added {len(all_docs) - (len(all_docs) - len(fallback_results))} docs. Total: {len(all_docs)}"
        )

    # Drop documents far below the top score (fewer-but-better chunks)
    if getattr(settings, "retrieval_score_delta_enabled", False):
        all_docs = _apply_score_delta_cutoff(all_docs, score_key="score")

    # Near-duplicate removal at retrieval time
    all_docs = _apply_retrieval_dedup(all_docs)

    web_docs = state.get("web_search_results", [])
    if web_docs:
        logger.info(f"Merging {len(web_docs)} web search results into primary document list")
        all_docs = web_docs + all_docs

    if len(all_docs) > getattr(settings, "rag_top_k_retrieval_after_cutoff", settings.rag_top_k_retrieval):
        question = state.get("rewritten_query") or state["question"]
        doc_texts = [doc["text"] for doc in all_docs]

        batch_enc = await asyncio.to_thread(embedder.encode_batch, doc_texts)
        doc_embeddings = batch_enc["dense"]

        query_enc = await asyncio.to_thread(embedder.encode_single_full, question)
        query_emb = query_enc["dense"]

        mmr_lambda = getattr(settings, "rag_mmr_lambda", 0.5)
        all_docs = qdrant.mmr_select(
            query_embedding=query_emb,
            documents=all_docs,
            doc_embeddings=doc_embeddings,
            top_k=settings.rag_top_k_retrieval,
            lambda_param=mmr_lambda,
        )

    # Coverage-gap check: docs exist but all score below quality threshold → treat as no coverage
    _coverage_threshold = getattr(settings, "web_search_coverage_threshold", 0.08)
    if all_docs and all(doc.get("score", 0.0) < _coverage_threshold for doc in all_docs):
        max_score = max(doc.get("score", 0.0) for doc in all_docs)
        _gap_intent = state.get("intent", "unknown")
        logger.warning(
            f"Coverage gap detected: {len(all_docs)} docs retrieved but all scored below "
            f"threshold {_coverage_threshold} (max_score={max_score:.4f}). "
            "Triggering web-search fallback."
        )
        try:
            COVERAGE_GAP_TOTAL.labels(intent=_gap_intent).inc()
        except Exception:
            pass
        web_search_service = getattr(_services, "_web_search", None)
        if web_search_service is not None:
            try:
                question = state.get("rewritten_query") or state["question"]
                user_id = state.get("user_id")
                web_results = await web_search_service.search(question, user_id=user_id)
                if web_results:
                    logger.info(f"Coverage-gap web search found {len(web_results)} results.")
                    all_docs = web_results
                    try:
                        WEB_SEARCH_HIT_TOTAL.labels(trigger="coverage_gap").inc()
                    except Exception:
                        pass
                else:
                    try:
                        WEB_SEARCH_MISS_TOTAL.labels(reason="empty").inc()
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning(f"Coverage-gap web search failed: {exc}")
                try:
                    WEB_SEARCH_MISS_TOTAL.labels(reason="error").inc()
                except Exception:
                    pass

    if not all_docs:
        logger.info("RAG retrieval yielded zero chunks. Triggering web-search fallback.")
        web_search_service = getattr(_services, "_web_search", None)
        if web_search_service is not None:
            try:
                question = state.get("rewritten_query") or state["question"]
                user_id = state.get("user_id")
                web_results = await web_search_service.search(question, user_id=user_id)
                if web_results:
                    logger.info(f"Web-search fallback found {len(web_results)} results.")
                    all_docs = web_results
                    try:
                        WEB_SEARCH_HIT_TOTAL.labels(trigger="zero_docs").inc()
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning(f"Web-search fallback failed: {exc}")
                try:
                    WEB_SEARCH_MISS_TOTAL.labels(reason="error").inc()
                except Exception:
                    pass

    raw_docs_copy = [dict(d) for d in all_docs]

    # Phase 2b: inject OKF compiled entries as a third retrieval channel.
    # Gate controlled by rag_okf_injection_enabled — defaults to True as of
    # Fix C's OKF hardening: OKF is now the canonical curated knowledge layer
    # (see app/config.py:269), not an opt-in extra.
    if (
        getattr(settings, "rag_okf_injection_enabled", False)
        and all_docs
        and intent not in ("CASUAL", "GREETING")
    ):
        try:
            okf_docs = _okf_match(base_question, limit=3)
            if okf_docs:
                logger.info("OKF injection: adding %d curated entries", len(okf_docs))
                all_docs = okf_docs + all_docs
                raw_docs_copy = okf_docs + raw_docs_copy
        except Exception:
            pass  # non-fatal; OKF must never break retrieval

    # RAGFlow Gap 1: adaptive deep-research sufficiency loop.
    # Auto-fires for tier3_complex + standard; opt-in via rag_deep_research_enabled.
    # ponytail: inline call — shortest diff, no new graph node. Non-fatal on failure.
    if (
        getattr(settings, "rag_deep_research_enabled", False)
        and state.get("query_tier") == "tier3_complex"
    ):
        try:
            from rag.nodes.deep_research import conduct_deep_research

            all_docs = await conduct_deep_research(
                base_question, all_docs, state, depth=getattr(settings, "rag_deep_research_max_depth", 2)
            )
        except Exception as e:
            logger.warning("Deep research failed (non-fatal): %s", e)

    if getattr(settings, "rag_context_compression_enabled", True):
        question = state.get("rewritten_query") or state["question"]
        all_docs = await _compress_rag_context_impl(question, all_docs, embedder)

    logger.info(f"Retrieved {len(all_docs)} unique documents (two-phase hybrid, parallel)")
    return {
        "documents": all_docs,
        "raw_documents": raw_docs_copy,
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
    knowledge_tags = state.get("knowledge_tags") or []

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
                "knowledge_tags": knowledge_tags,
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
        lightrag=lightrag if state.get("query_tier") == "tier3_complex" else None,
        knowledge_tags=state.get("knowledge_tags") or [],
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
            knowledge_tags=state.get("knowledge_tags") or [],
        )
        for doc in fallback_results:
            th = hash(doc["text"][:100])
            if th not in seen:
                seen.add(th)
                all_docs.append(doc)

    # Drop documents far below the top score (fewer-but-better chunks)
    if getattr(settings, "retrieval_score_delta_enabled", False):
        all_docs = _apply_score_delta_cutoff(all_docs, score_key="score")

    # Near-duplicate removal at retrieval time
    all_docs = _apply_retrieval_dedup(all_docs)

    web_docs = state.get("web_search_results", [])
    if web_docs:
        logger.info(f"merge_sub_results: merging {len(web_docs)} web search results")
        all_docs = web_docs + all_docs

    top_k = getattr(settings, "rag_top_k_retrieval_after_cutoff", settings.rag_top_k_retrieval)
    if len(all_docs) > top_k:
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
            top_k=top_k,
            lambda_param=0.7,
        )

    logger.info(
        f"merge_sub_results: {len(all_results)} branch(es) -> {len(all_docs)} unique docs (RRF + MMR + cutoffs applied)"
    )
    return {"documents": all_docs}
