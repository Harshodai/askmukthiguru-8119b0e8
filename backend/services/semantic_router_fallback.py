"""
Unit 21 — Semantic Router Fallback (Neo4j Full-Text Search)

When the vector search (Qdrant) returns no results or insufficient results,
this module provides a fallback using Neo4j full-text search to prevent
silent 500 errors and empty responses.

Fallback chain:
  1. Qdrant hybrid search (primary — always tried first)
  2. Neo4j full-text search (this module — used when Qdrant returns < min_results)
  3. LightRAG GraphRAG query (deep graph-based retrieval for complex questions)

Design:
  - ``SemanticRouterFallback``: orchestrates the fallback chain
  - ``neo4j_fulltext_search()``: runs a Cypher full-text query against the Neo4j index
  - Results are normalized to the same dict schema as QdrantService.search()
  - Graceful: if Neo4j is unreachable, falls back gracefully with an empty list

Neo4j full-text index expected:
  - Index name: ``chunk_text`` on ``(:Chunk {text})``
  - Created by LightRAG during initialization

Usage::

    from services.semantic_router_fallback import SemanticRouterFallback

    fallback = SemanticRouterFallback(lightrag_service)
    results = await fallback.search_with_fallback(
        query="What is non-doing in consciousness?",
        qdrant_results=existing_qdrant_results,
        min_results=3,
    )
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Minimum result count before triggering fallback
DEFAULT_MIN_RESULTS = 2
# Max results to return from Neo4j fallback
NEO4J_FALLBACK_LIMIT = 10


async def neo4j_fulltext_search(
    query: str,
    limit: int = NEO4J_FALLBACK_LIMIT,
    neo4j_uri: Optional[str] = None,
    neo4j_user: Optional[str] = None,
    neo4j_password: Optional[str] = None,
) -> list[dict]:
    """Execute a Neo4j full-text search on the ``chunk_text`` index.

    Returns normalized dicts matching QdrantService.search() schema.
    Returns an empty list if Neo4j is unreachable or the index doesn't exist.
    """
    try:
        from app.config import settings as _settings
        uri = neo4j_uri or _settings.neo4j_uri
        user = neo4j_user or _settings.neo4j_user
        pwd = neo4j_password or _settings.neo4j_password
    except Exception as exc:
        logger.debug(f"SemanticRouterFallback: config unavailable: {exc}")
        return []

    if not uri:
        logger.debug("SemanticRouterFallback: NEO4J_URI not configured; skipping")
        return []

    cypher = """
    CALL db.index.fulltext.queryNodes('chunk_text', $query, {limit: $limit})
    YIELD node, score
    RETURN
        node.text AS text,
        node.source_url AS source_url,
        node.title AS title,
        node.chunk_index AS chunk_index,
        node.raptor_level AS raptor_level,
        score
    ORDER BY score DESC
    LIMIT $limit
    """

    def _run_query():
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(uri, auth=(user, pwd))
        try:
            with driver.session() as session:
                result = session.run(cypher, query=query, limit=limit)
                records = []
                for record in result:
                    records.append({
                        "text": record.get("text", ""),
                        "source_url": record.get("source_url", ""),
                        "title": record.get("title", ""),
                        "content_type": "neo4j_fts",
                        "chunk_index": record.get("chunk_index", 0),
                        "raptor_level": record.get("raptor_level", 0),
                        "score": record.get("score", 0.0),
                        "parent_id": None,
                        "parent_text": None,
                        "is_child": False,
                        "speaker": "Unknown",
                        "topic": "Spiritual",
                    })
                return records
        finally:
            driver.close()

    try:
        results = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _run_query),
            timeout=10.0,
        )
        logger.info(
            f"SemanticRouterFallback: Neo4j full-text search returned "
            f"{len(results)} results for query: {query[:60]!r}"
        )
        return results
    except asyncio.TimeoutError:
        logger.warning("SemanticRouterFallback: Neo4j query timed out (10s)")
        return []
    except Exception as exc:
        logger.warning(f"SemanticRouterFallback: Neo4j search failed: {type(exc).__name__}: {exc}")
        return []


class SemanticRouterFallback:
    """Orchestrates the 3-tier retrieval fallback chain.

    Tier 1: Qdrant hybrid search (caller's responsibility — results passed in)
    Tier 2: Neo4j full-text search (this class)
    Tier 3: LightRAG GraphRAG context extraction (for complex/spiritual queries)
    """

    def __init__(self, lightrag_service=None) -> None:
        self._lightrag = lightrag_service

    async def search_with_fallback(
        self,
        query: str,
        qdrant_results: list[dict],
        min_results: int = DEFAULT_MIN_RESULTS,
        use_lightrag: bool = True,
    ) -> list[dict]:
        """Return enriched results using the fallback chain if needed.

        Args:
            query: The user's query text.
            qdrant_results: Results already retrieved from Qdrant (may be empty).
            min_results: If Qdrant returns fewer, trigger the fallback.
            use_lightrag: Whether to try LightRAG as a 3rd-tier fallback.

        Returns:
            Combined deduped results from all successful retrieval tiers.
        """
        if len(qdrant_results) >= min_results:
            return qdrant_results  # Primary sufficient — no fallback needed

        logger.info(
            f"SemanticRouterFallback: Qdrant returned {len(qdrant_results)} results "
            f"(min={min_results}). Triggering Neo4j fallback."
        )

        # Tier 2: Neo4j full-text search
        neo4j_results = await neo4j_fulltext_search(query)
        combined = list(qdrant_results)

        # Dedup by text content
        seen_texts = {r["text"][:100] for r in combined}
        for r in neo4j_results:
            key = r["text"][:100]
            if key not in seen_texts:
                combined.append(r)
                seen_texts.add(key)

        if len(combined) >= min_results:
            logger.info(
                f"SemanticRouterFallback: Neo4j fallback added "
                f"{len(neo4j_results)} results → total {len(combined)}"
            )
            return combined

        # Tier 3: LightRAG GraphRAG
        if use_lightrag and self._lightrag:
            try:
                lightrag_context = await asyncio.wait_for(
                    self._lightrag.aquery(query, mode="hybrid", only_need_context=True),
                    timeout=15.0,
                )
                if lightrag_context and isinstance(lightrag_context, str):
                    combined.append({
                        "text": lightrag_context[:2000],
                        "source_url": "lightrag://graph",
                        "title": "Knowledge Graph Context",
                        "content_type": "lightrag_graph",
                        "chunk_index": 0,
                        "raptor_level": 2,
                        "score": 0.5,
                        "parent_id": None,
                        "parent_text": None,
                        "is_child": False,
                        "speaker": "Graph",
                        "topic": "Spiritual",
                    })
                    logger.info("SemanticRouterFallback: LightRAG added graph context")
            except asyncio.TimeoutError:
                logger.warning("SemanticRouterFallback: LightRAG query timed out (15s)")
            except Exception as exc:
                logger.warning(
                    f"SemanticRouterFallback: LightRAG fallback failed: "
                    f"{type(exc).__name__}: {exc}"
                )

        return combined
