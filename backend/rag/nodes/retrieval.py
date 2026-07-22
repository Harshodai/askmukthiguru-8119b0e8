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
from services.embedding_service import EmbeddingService, _apply_query_expansion
from services.lightrag_service import LightRAGService
from services.qdrant_service import QdrantService

import re

from app.tracing import trace_rag_node
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
        # Loud on purpose: rag_okf_injection_enabled defaults to True, so an absent
        # index silently strips the canonical knowledge layer from every answer.
        logger.warning(
            "OKF compiled index missing at %s — OKF injection will contribute no documents. "
            "In Docker this means memory/ was not copied into the image.",
            _OKF_COMPILED_PATH,
        )
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


def _okf_match(query: str, limit: int = 3, teacher: str | None = None) -> list[dict]:
    """Semantic match via cosine similarity on title embeddings; keyword fallback.

    When *teacher* is provided (``sri-preethaji`` | ``sri-krishnaji``), only entries
    whose frontmatter ``teacher`` field matches — or is ``"both"`` — are returned.
    """
    entries = _load_okf_entries()
    if not entries:
        return []

    # Teacher filter — narrow to entries matching the requested guru
    if teacher:
        entries = [
            e for e in entries
            if e.get("teacher") in (teacher, "both")
        ]
        if not entries:
            return []

    # Try semantic matching first
    try:
        embedder = _services._embedder
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
                        "teacher": e.get("teacher", "both"),
                    },
                })
            return docs
    except Exception:
        pass

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
                "teacher": e.get("teacher", "both"),
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
        from app.dependencies import get_container

        def _run():
            driver = get_container().neo4j_driver
            if driver is None:
                raise RuntimeError("Neo4j driver unavailable")
            subgraph_context = []
            candidates = set()
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
                        if record.get('target'):
                            candidates.add(record['target'])
            return subgraph_context, list(candidates)

        res, candidates = await asyncio.to_thread(_run)
        if res:
            candidate_str = f"\n[Next-Step Traversal Candidates]: {', '.join(sorted(candidates))}" if candidates else ""
            return "\n[Targeted Subgraph Context]:\n" + "\n".join(res) + candidate_str
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
        from app.dependencies import get_container
        tenant_id = TenantContext.get()
        def _run():
            driver = get_container().neo4j_driver
            if driver is None:
                raise RuntimeError("Neo4j driver unavailable")
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


def _dedup_newest_by_source(docs: list[dict]) -> list[dict]:
    """Pre-rerank dedup: same source_id + title → keep highest source_version."""
    if not docs:
        return docs
    best: dict[tuple[str, str], dict] = {}
    for doc in docs:
        source_id = doc.get("source_id") or doc.get("video_id") or doc.get("source_url", "")
        title = doc.get("title", "")
        key = (source_id, title)
        current_version = doc.get("source_version", 1)
        existing = best.get(key)
        if existing is None or current_version > existing.get("source_version", 1):
            best[key] = doc
    if len(best) == len(docs):
        return docs
    logger.info(f"Dedup-newest: {len(docs)} -> {len(best)} docs")
    return list(best.values())


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


def _bm25_sparse_search(
    query: str,
    embedder: EmbeddingService,
    qdrant: QdrantService,
    limit: int = 10,
) -> list[dict]:
    """Native BM25 sparse-vector search via Qdrant's sparse named vector.

    Encodes the query with bge-m3 lexical weights and queries the ``sparse``
    vector in Qdrant, returning Qdrant's own relevance scores instead of a
    local word-overlap approximation.
    """
    query_embedding = embedder.encode_single_full(query)
    sparse_vector = query_embedding.get("sparse")
    if not sparse_vector:
        return []

    hits = qdrant.search(
        query_vector=query_embedding["dense"],
        limit=limit,
        sparse_vector=sparse_vector,
        raptor_level=0,
    )

    for hit in hits:
        hit["source"] = "bm25_sparse"
    return hits


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


@trace_rag_node("navigate_and_hyde")
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


@trace_rag_node("decompose_query")
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


def _compute_query_for_embedding(
    query: str,
    chat_history: list,
    hyde_text: Optional[str],
) -> str:
    """Compute the text that gets encoded for a sub-query.

    Mirrors the augmentation + hyde + rule-based expansion logic in
    `retrieve_for_single_query` so the retrieve node can batch-encode
    all primary queries in one `encode_batch` call (collapses 6
    `_inference_lock` acquisitions into 1).
    """
    augmented_query = query
    if chat_history:
        last_user_msgs = [m["content"] for m in chat_history[-4:] if m.get("role") == "user"]
        if last_user_msgs:
            augmented_query = f"{last_user_msgs[-1]} {query}"

    query_for_embedding = hyde_text or augmented_query
    return _apply_query_expansion(query_for_embedding)


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
    query_embedding: Optional[dict] = None,
) -> list[dict]:
    """Retrieve documents for a single sub-query, decoupled from state.

    If `query_embedding` is supplied ({"dense": ..., "sparse": ...}),
    skip the encode step and use it directly — this lets the retrieve
    node batch-encode all primary sub-queries in one `encode_batch`
    call. When None, fall back to `encode_single_full` (backward compat).
    """
    augmented_query = query
    if chat_history:
        last_user_msgs = [m["content"] for m in chat_history[-4:] if m.get("role") == "user"]
        if last_user_msgs:
            augmented_query = f"{last_user_msgs[-1]} {query}"

    query_for_embedding = hyde_text or augmented_query
    if query_embedding is None:
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
    if (
        getattr(settings, "knowledge_graph_query_enabled", False)
        and lightrag
        and intent in ["RELATIONAL", "FACTUAL", "QUERY"]
    ):
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


@trace_rag_node("retrieve_documents")
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
    # E4.2: KG-RAG ontology traversal — broaden query with Neo4j neighbors
    # of mentioned concepts (e.g. "karma" -> also retrieve "Dharma", "prarabdha").
    # Ponytail: one helper, fire-and-forget, non-fatal. Runs alongside synonym
    # expansion so docs tagged with sub-concepts are also surfaced.
    try:
        from rag.kg_expansion import expand_query_with_ontology, augment_query
        from app.dependencies import get_container
        _neo4j = getattr(get_container(), "neo4j_driver", None)
        if _neo4j is not None:
            neighbors = await expand_query_with_ontology(base_question, _neo4j)
            if neighbors:
                base_question = augment_query(base_question, neighbors)
                logger.info(f"KG ontology expansion: +{len(neighbors)} neighbor(s)")
    except Exception as _kg_err:
        logger.debug(f"KG ontology expansion skipped: {_kg_err}")
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
    # Feature-flagged: set rag_skip_retrieval_expansions=true to skip the
    # LLM expansion call (saves 1 LLM call on standard/deep paths).
    #
    # --- LEGACY (preserved per "do not delete, just comment") ---
    # expansion_queries: list[str] = await _llm_retrieval_expansions(state)
    # if expansion_queries:
    #     logger.info(...)
    # sub_queries = list(dict.fromkeys([*sub_queries, *expansion_queries]))
    # ------------------------------------------------------------
    if not getattr(settings, "rag_skip_retrieval_expansions", False):
        expansion_task = asyncio.create_task(_llm_retrieval_expansions(state))
    else:
        expansion_task = None

    chat_history = state.get("chat_history", [])
    selected_clusters = state.get("selected_clusters", [])
    hyde_text = state.get("hyde_text")
    intent = state.get("intent", "FACTUAL")
    knowledge_tags = state.get("knowledge_tags") or []
    embedder = _services._embedder
    qdrant = _services._qdrant
    lightrag = _services._lightrag

    primary_queries = list(dict.fromkeys(sub_queries))[:6]
    # Batch-encode ALL primary queries in ONE encode_batch call.
    # Collapses 6 `_inference_lock` acquisitions into 1 (66.7s -> ~3.5s
    # for the encode step). Order is preserved: precomputed[i] matches
    # primary_queries[i]. Expansion queries keep using encode_single_full
    # individually (capped at remaining_budget, usually 0-3) to preserve
    # the parallel-fire pattern with the LLM expansion call.
    precomputed_embeddings: list[Optional[dict]] = [None] * len(primary_queries)
    if primary_queries:
        primary_query_texts = [
            _compute_query_for_embedding(q, chat_history, hyde_text)
            for q in primary_queries
        ]
        try:
            batched = await asyncio.to_thread(embedder.encode_batch, primary_query_texts)
            precomputed_embeddings = [
                {"dense": batched["dense"][i], "sparse": batched["sparse"][i]}
                for i in range(len(primary_queries))
            ]
        except Exception as enc_err:
            logger.warning(
                f"Batched encode failed (non-fatal, falling back to per-query): {enc_err}"
            )
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
                    query_embedding=precomputed_embeddings[i],
                ),
                timeout=get_node_timeout("default_main", getattr(settings, "node_timeout_main", 60)),
            )
            for i, q in enumerate(primary_queries)
        ],
        return_exceptions=True,
    )

    # --- BM25 sparse-vector search fan-out (parallel with vector retrieval) ---
    bm25_results: list[dict] = []
    if getattr(settings, "bm25_retrieval_enabled", True):
        try:
            bm25_query = sub_queries[0] if sub_queries else state.get("question", "")
            bm25_results = _bm25_sparse_search(
                bm25_query,
                embedder,
                qdrant,
                limit=getattr(settings, "bm25_result_limit", 10),
            )
            logger.info(f"BM25 sparse search returned {len(bm25_results)} results")
        except Exception as bm25_err:
            logger.warning(f"BM25 sparse search failed (non-fatal): {bm25_err}")

    # Now consume the (likely already-completed) expansion task.
    # Cap total retrievals at 6 to bound LLM/Qdrant load.
    expansion_queries = []
    if expansion_task is not None:
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

    # GraphRAG Fusion — multi-hop vector + KG retrieval fused via RRF.
    # Runs BEFORE score cutoff, dedup, MMR, compression, and budget processing
    # so fused results participate in all downstream quality safeguards.
    if (
        _services._graphrag_fusion is not None
        and getattr(settings, "graphrag_fusion_enabled", False)
    ):
        try:
            from services.graphrag_fusion import ContextItem
            fused = await _services._graphrag_fusion.retrieve(base_question)
            if fused.items:
                fused_docs = [
                    {"text": i.text, "score": i.score, "channel": i.channel, "provenance": i.provenance}
                    for i in fused.items
                ]
                all_docs = fused_docs + all_docs
        except Exception as e:
            logger.warning("GraphRAG fusion failed (non-fatal): %s", type(e).__name__)

    # Drop documents far below the top score (fewer-but-better chunks)
    if getattr(settings, "retrieval_score_delta_enabled", False):
        all_docs = _apply_score_delta_cutoff(all_docs, score_key="score")

    # Pre-rerank dedup: same source_id+title → keep highest source_version
    all_docs = _dedup_newest_by_source(all_docs)

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
        and intent not in ("CASUAL", "GREETING")
    ):
        try:
            # Teacher routing: detect guru mention in query for OKF filtering
            _ql = base_question.lower()
            _teacher = None
            if "sri preethaji" in _ql or "preethaji" in _ql:
                _teacher = "sri-preethaji"
            elif "sri krishnaji" in _ql or "krishnaji" in _ql:
                _teacher = "sri-krishnaji"
            okf_docs = _okf_match(base_question, limit=3, teacher=_teacher)
            if okf_docs:
                logger.info("OKF injection: adding %d curated entries", len(okf_docs))
                all_docs = okf_docs + all_docs
                raw_docs_copy = okf_docs + raw_docs_copy
        except Exception:
            pass  # non-fatal; OKF must never break retrieval

    # RAGFlow Gap 1: adaptive deep-research sufficiency loop.
    # Auto-fires for tier3_complex + standard; opt-in via rag_deep_research_enabled.
    # ponytail: inline call — shortest diff, no new graph node. Non-fatal on failure.
    deep_research_done = False
    if (
        getattr(settings, "rag_deep_research_enabled", False)
        and state.get("query_tier") == "tier3_complex"
    ):
        try:
            from rag.nodes.deep_research import conduct_deep_research

            all_docs = await conduct_deep_research(
                base_question, all_docs, state, depth=getattr(settings, "rag_deep_research_max_depth", 2)
            )
            deep_research_done = True
        except Exception as e:
            logger.warning("Deep research failed (non-fatal): %s", e)

    # Task 2: low-confidence escalation for standard/tier3/tier4.
    # If CRAG marked retrieval as low confidence, run deep research and fall back
    # to web search if the context is still thin. Non-fatal on every failure.
    if (
        state.get("low_confidence_retrieval")
        and state.get("query_tier") in ("standard", "tier3_complex", "tier4_deep")
        and not deep_research_done
    ):
        try:
            from rag.nodes.deep_research import conduct_deep_research

            all_docs = await conduct_deep_research(
                base_question, all_docs, state,
                depth=getattr(settings, "rag_deep_research_max_depth", 2)
            )
            deep_research_done = True
        except Exception as e:
            logger.warning("Low-confidence deep research failed (non-fatal): %s", e)

        if len(all_docs) < 3:
            web_search_service = getattr(_services, "_web_search", None)
            if web_search_service is not None:
                try:
                    question = state.get("rewritten_query") or state["question"]
                    user_id = state.get("user_id")
                    web_results = await web_search_service.search(question, user_id=user_id)
                    if web_results:
                        all_docs = web_results + all_docs
                        try:
                            WEB_SEARCH_HIT_TOTAL.labels(trigger="low_confidence").inc()
                        except Exception:
                            pass
                except Exception as exc:
                    logger.warning("Low-confidence web search failed: %s", exc)

    if getattr(settings, "rag_context_compression_enabled", False):
        question = state.get("rewritten_query") or state["question"]
        # Tier-aware compression budget: deep/complex queries keep more diversity
        # because they rely on LITM/BM25/deep-research breadth. Fast/simple tiers
        # benefit from a tighter focus. Preserve at least the top 3 and up to a
        # score-threshold fraction of the retrieved set.
        if query_tier in ("deep", "tier3_complex"):
            max_compress_k = max(5, len(all_docs) // 2)
        elif query_tier in ("fast", "tier2_simple"):
            max_compress_k = 3
        else:
            max_compress_k = getattr(settings, "rag_context_compression_top_k", 5)

        if all_docs:
            top_score = max(doc.get("score", 0.0) for doc in all_docs) or 1.0
            score_floor = top_score * getattr(settings, "rag_context_compression_score_ratio", 0.75)
            eligible = [doc for doc in all_docs if doc.get("score", 0.0) >= score_floor]
            allowlisted = eligible[:max_compress_k]
            compressed = await _compress_rag_context_impl(question, allowlisted, embedder)
            compressed_ids = {id(d) for d in compressed}
            all_docs = compressed + [d for d in all_docs if id(d) not in compressed_ids]

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



