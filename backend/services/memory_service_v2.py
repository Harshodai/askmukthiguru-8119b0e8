"""Three-Tier Memory Service (v2).

Extends MemoryService with:
  Tier 1 — Ephemeral (Redis): short-term session context, 15-min TTL
  Tier 2 — Semantic (PG+Qdrant): long-term vector search (existing v1)
  Tier 3 — Global (Qdrant Cluster+Neo4j): cross-user knowledge graph memory

All tiers are independently operational — failures in one don't block others.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

from redis import asyncio as aioredis

from services.memory_service import MemoryService
from services.tenant_context import TenantContext

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
EPHEMERAL_TTL = 900  # 15 minutes
GLOBAL_MEMORY_COLLECTION = "global_memory"
_LRU_MAX_SIZE = 1000  # ponytail: in-memory LRU fallback cap, bump if eviction rate >5%


@dataclass
class MemoryTierResult:
    source: str
    memories: list[dict[str, Any]]
    latency_ms: float
    error: Optional[str] = None


class MemoryServiceV2(MemoryService):
    """Three-tier memory service with isolated fallback per tier."""

    def __init__(self, supabase_client=None, embedding_service=None, llm_service=None,
                 *, guru_slug: str = "default", use_global_memory: bool = False):
        super().__init__(supabase_client, embedding_service, llm_service)
        self.guru_slug = guru_slug
        self.use_global_memory = use_global_memory
        self._redis: Optional[aioredis.Redis] = None
        self._neo4j_driver = None
        # LRU fallback when Redis is down — bounded, thread-safe via asyncio
        self._lru_fallback: OrderedDict[str, str] = OrderedDict()
        self._redis_available: Optional[bool] = None  # None = unchecked

    def _get_memory_collection(
        self, guru_slug: Optional[str] = None, use_global_memory: Optional[bool] = None
    ) -> str:
        """Return the Qdrant collection for memory writes.

        Per-guru (default): "{guru_slug}_memory"
        Global (toggle)   : "global_memory"

        guru_slug/use_global_memory are accepted per-call because this service
        is a process-lifetime singleton (built once in ServiceContainer) shared
        across every assistant — the active guru varies per request, not per
        process, so it cannot live solely on constructor state.
        """
        is_global = self.use_global_memory if use_global_memory is None else use_global_memory
        if is_global:
            return GLOBAL_MEMORY_COLLECTION
        return f"{guru_slug or self.guru_slug}_memory"

    # ---- Tier 1: Ephemeral (Redis) ----

    async def _get_redis(self) -> Optional[aioredis.Redis]:
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
                await self._redis.ping()
                logger.info("Connected to Redis for ephemeral memory")
            except Exception as e:
                logger.warning(f"Redis unavailable for ephemeral memory: {e}")
                self._redis = None
        return self._redis

    async def set_ephemeral(self, user_id: str, key: str, value: Any, ttl: int = EPHEMERAL_TTL) -> bool:
        redis = await self._get_redis()
        tenant_id = TenantContext.get()
        cache_key = f"ephemeral:{tenant_id}:{user_id}:{key}"
        serialized = json.dumps(value)
        if redis:
            try:
                await redis.setex(cache_key, ttl, serialized)
                self._redis_available = True
                return True
            except Exception as e:
                logger.warning(f"Redis ephemeral set failed, falling back to LRU: {e}")
                self._redis_available = False
        # LRU fallback
        self._lru_set(cache_key, serialized)
        return True

    async def get_ephemeral(self, user_id: str, key: str) -> Optional[Any]:
        redis = await self._get_redis()
        tenant_id = TenantContext.get()
        cache_key = f"ephemeral:{tenant_id}:{user_id}:{key}"
        if redis and self._redis_available is not False:
            try:
                data = await redis.get(cache_key)
                if data:
                    self._redis_available = True
                    return json.loads(data)
                # Redis miss — check LRU in case it was written during outage
            except Exception as e:
                logger.warning(f"Redis ephemeral get failed, falling back to LRU: {e}")
                self._redis_available = False
        # LRU fallback
        data = self._lru_get(cache_key)
        return json.loads(data) if data else None

    async def get_ephemeral_session(self, user_id: str, session_id: str) -> dict[str, Any]:
        redis = await self._get_redis()
        if not redis:
            return {}
        tenant_id = TenantContext.get()
        try:
            keys = await redis.keys(f"ephemeral:{tenant_id}:{user_id}:session:{session_id}:*")
            result = {}
            for key in keys:
                short_key = key.split(":")[-1]
                data = await redis.get(key)
                if data:
                    result[short_key] = json.loads(data)
            return result
        except Exception as e:
            logger.warning(f"Ephemeral session get failed: {e}")
            return {}

    async def clear_ephemeral(self, user_id: str, session_id: Optional[str] = None) -> bool:
        redis = await self._get_redis()
        if not redis:
            return False
        tenant_id = TenantContext.get()
        try:
            pattern = f"ephemeral:{tenant_id}:{user_id}:{session_id + ':' if session_id else ''}*"
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)
            return True
        except Exception as e:
            logger.warning(f"Ephemeral clear failed: {e}")
            return False

    # ---- Tier 3: Global (Qdrant Cluster + Neo4j) ----

    def _get_qdrant_v2(self):
        """Get Qdrant client for global memory collection."""
        try:
            from qdrant_client import QdrantClient
            qdrant_url = os.environ.get("QDRANT_URL_V2") or os.environ.get("QDRANT_URL", "http://qdrant:6333")
            return QdrantClient(url=qdrant_url)
        except Exception:
            return None

    def ensure_global_memory_collection(self) -> bool:
        """Create the GLOBAL_MEMORY_COLLECTION in Qdrant if it doesn't exist yet.

        `set_global_memory`/`search_global` upsert/search against this collection
        via a raw QdrantClient but never created it — every write/search silently
        failed inside their broad `except Exception` handlers. Call once at
        startup (ServiceContainer._build_profiles) so global memory actually works.

        Uses an unnamed default vector (matches the raw `vector=embedding` upsert
        in `set_global_memory`), unlike the main collection's named dense+sparse
        vectors — the two schemas are intentionally different.
        """
        client = self._get_qdrant_v2()
        if client is None:
            logger.warning("Cannot ensure global_memory collection — Qdrant client unavailable")
            return False
        try:
            from qdrant_client.http.models import Distance, VectorParams
            from app.config import settings

            existing = {c.name for c in client.get_collections().collections}
            if GLOBAL_MEMORY_COLLECTION in existing:
                return True

            client.create_collection(
                collection_name=GLOBAL_MEMORY_COLLECTION,
                vectors_config=VectorParams(
                    size=settings.embedding_dimension, distance=Distance.COSINE
                ),
            )
            logger.info(f"Created Qdrant collection: {GLOBAL_MEMORY_COLLECTION}")
            return True
        except Exception as e:
            logger.warning(f"Failed to ensure global_memory collection: {e}")
            return False

    def _get_neo4j(self):
        """Get Neo4j driver for graph memory."""
        if self._neo4j_driver is None:
            try:
                from neo4j import GraphDatabase
                uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
                user = os.environ.get("NEO4J_USER", "neo4j")
                password = os.environ.get("NEO4J_PASSWORD", "mukthiguru_neo4j_pass")
                self._neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
            except Exception as e:
                logger.warning(f"Neo4j unavailable: {e}")
                self._neo4j_driver = None
        return self._neo4j_driver

    async def set_global_memory(
        self,
        user_id: str,
        content: str,
        embedding: list[float],
        metadata: Optional[dict] = None,
        *,
        guru_slug: Optional[str] = None,
        use_global_memory: Optional[bool] = None,
    ) -> bool:
        """Store in global Qdrant collection + Neo4j graph."""
        success = False

        try:
            client = await asyncio.to_thread(self._get_qdrant_v2)
            if client:
                from qdrant_client.http import models
                point_id = f"global:{user_id}:{hash(content) % 10**15}"
                await asyncio.to_thread(
                    client.upsert,
                    collection_name=self._get_memory_collection(guru_slug, use_global_memory),
                    points=[models.PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "user_id": user_id,
                            "content": content,
                            "metadata": metadata or {},
                            "created_at": time.time(),
                        },
                    )],
                )
                success = True
        except Exception as e:
            logger.warning(f"Global Qdrant write failed: {e}")

        try:
            driver = await asyncio.to_thread(self._get_neo4j)
            if driver:
                from services.tenant_context import TenantContext
                tenant_id = TenantContext.get()

                # ponytail: to_thread wraps sync neo4j driver; migrate to AsyncGraphDatabase past 100 concurrent users
                def _write():
                    with driver.session() as session:
                        session.run(
                            """
                            MERGE (u:User {id: $user_id})
                            SET u.tenant_id = $tenant_id
                            MERGE (m:GlobalMemory {id: $memory_id})
                            SET m.content = $content, m.created_at = timestamp(), m.tenant_id = $tenant_id
                            MERGE (u)-[:HAS_MEMORY]->(m)
                            """,
                            user_id=user_id,
                            memory_id=f"global:{user_id}:{hash(content) % 10**15}",
                            content=content,
                            tenant_id=tenant_id,
                        )

                await asyncio.to_thread(_write)
                success = True
        except Exception as e:
            logger.warning(f"Neo4j write failed: {e}")

        return success

    async def search_global(
        self,
        query_embedding: list[float],
        limit: int = 5,
        min_similarity: float = 0.7,
        user_id: Optional[str] = None,
        *,
        guru_slug: Optional[str] = None,
        use_global_memory: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        """Search global memory across all users (or filter by user_id)."""
        try:
            client = await asyncio.to_thread(self._get_qdrant_v2)
            if not client:
                return []

            from qdrant_client.http import models
            filter_cond = models.Filter(
                must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
            ) if user_id else None

            results = await asyncio.to_thread(
                client.search,
                collection_name=self._get_memory_collection(guru_slug, use_global_memory),
                query_vector=query_embedding,
                limit=limit,
                score_threshold=min_similarity,
                query_filter=filter_cond,
            )

            return [
                {
                    "content": r.payload.get("content", ""),
                    "user_id": r.payload.get("user_id", ""),
                    "metadata": r.payload.get("metadata", {}),
                    "score": r.score,
                }
                for r in results
            ]
        except Exception as e:
            logger.warning(f"Global search failed: {e}")
            return []

    async def get_global_graph(
        self,
        user_id: str,
        depth: int = 2,
    ) -> list[dict[str, Any]]:
        """Traverse Neo4j graph for related memories."""
        try:
            driver = await asyncio.to_thread(self._get_neo4j)
            if not driver:
                return []

            from services.tenant_context import TenantContext
            tenant_id = TenantContext.get()

            def _query():
                with driver.session() as session:
                    result = session.run(
                        """
                        MATCH (u:User {id: $user_id})-[:HAS_MEMORY]->(m:GlobalMemory)
                        WHERE m.tenant_id = $tenant_id
                        OPTIONAL MATCH (m)-[:RELATED_TO]->(related:GlobalMemory)
                        WHERE related.tenant_id = $tenant_id
                        RETURN m.content AS memory, collect(DISTINCT related.content) AS related_memories
                        LIMIT 20
                        """,
                        user_id=user_id,
                        tenant_id=tenant_id,
                    )
                    return result.data()

            records = await asyncio.to_thread(_query)
            return [
                {
                    "memory": r["memory"],
                    "related_memories": r["related_memories"],
                }
                for r in records
            ]
        except Exception as e:
            logger.warning(f"Neo4j graph query failed: {e}")
            return []

    # ---- Unified multi-tier query ----

    async def search_all_tiers(
        self,
        user_id: str,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 5,
        *,
        guru_slug: Optional[str] = None,
        use_global_memory: Optional[bool] = None,
    ) -> dict[str, list[MemoryTierResult]]:
        """Search all three tiers in parallel, returning independent results."""
        embedding = None
        if self._embedding_service:
            try:
                emb_dict = await asyncio.to_thread(self._embedding_service.encode_single_full, query)
                embedding = emb_dict.get("dense")
            except Exception:
                pass

        async def _tier1():
            start = time.monotonic()
            try:
                if session_id:
                    memories = await self.get_ephemeral_session(user_id, session_id)
                    result_list = [{"key": k, "value": v} for k, v in memories.items()]
                else:
                    result_list = []
                return MemoryTierResult(
                    source="ephemeral",
                    memories=result_list,
                    latency_ms=(time.monotonic() - start) * 1000,
                )
            except Exception as e:
                return MemoryTierResult(source="ephemeral", memories=[], latency_ms=0, error=str(e))

        async def _tier2():
            start = time.monotonic()
            try:
                memories = await self.search_semantic(user_id, query, limit=limit, min_similarity=0.6)
                return MemoryTierResult(
                    source="semantic",
                    memories=memories,
                    latency_ms=(time.monotonic() - start) * 1000,
                )
            except Exception as e:
                return MemoryTierResult(source="semantic", memories=[], latency_ms=0, error=str(e))

        async def _tier3():
            start = time.monotonic()
            try:
                results = []
                if embedding:
                    results = await self.search_global(
                        embedding,
                        limit=limit,
                        user_id=user_id,
                        guru_slug=guru_slug,
                        use_global_memory=use_global_memory,
                    )
                return MemoryTierResult(
                    source="global",
                    memories=results,
                    latency_ms=(time.monotonic() - start) * 1000,
                )
            except Exception as e:
                return MemoryTierResult(source="global", memories=[], latency_ms=0, error=str(e))

        t1, t2, t3 = await asyncio.gather(_tier1(), _tier2(), _tier3(), return_exceptions=False)

        return {
            "ephemeral": t1,
            "semantic": t2,
            "global": t3,
        }

    async def close(self):
        if self._redis:
            await self._redis.close()
        if self._neo4j_driver:
            await self._neo4j_driver.close()

    # ---- E4.3: Personalized subgraphs ----

    async def get_user_subgraph(self, user_id: str, concept: str, depth: int = 2) -> dict[str, Any]:
        """Return a personalized context subgraph for `user_id` around `concept`.

        E4.3 stub (Ponytail). Combines:
          - Tier-3 global graph memory for this user (`get_global_graph`)
          - Neo4j ontology neighbors of `concept` (if Neo4j is up)
        into a single dict for the prompt to consume as personalized context.

        Existing per-user Neo4j data: `set_global_memory` writes
        (:User {id})-[:HAS_MEMORY]->(:GlobalMemory {content}) with tenant_id;
        `get_global_graph` traverses HAS_MEMORY + RELATED_TO. That is user-
        specific Neo4j data already — this method wraps it with concept focus.

        Args:
            user_id: Supabase auth user id.
            concept: Canonical concept name (e.g. "Karma", "Beautiful State").
            depth: Traversal depth (1-2 typical; capped at 3).

        Returns:
            {
              "user_id": str,
              "concept": str,
              "memories": list[dict],     # from get_global_graph
              "ontology_neighbors": list[str],  # neighbor entity_ids
            }
            Never raises — degrades to empty lists on any failure.
        """
        result: dict[str, Any] = {
            "user_id": user_id,
            "concept": concept,
            "memories": [],
            "ontology_neighbors": [],
        }
        # 1. Per-user global graph memories
        try:
            result["memories"] = await self.get_global_graph(user_id, depth=depth)
        except Exception as e:
            logger.warning(f"get_user_subgraph: global graph failed: {e}")

        # 2. Ontology neighbors of the concept (best-effort, one Cypher)
        try:
            driver = await asyncio.to_thread(self._get_neo4j)
            if driver is not None:
                def _neighbors():
                    with driver.session() as session:
                        res = session.run(
                            "MATCH (n {entity_id: $concept})-[r]-(neighbor) "
                            "WHERE neighbor.entity_id IS NOT NULL "
                            "RETURN DISTINCT neighbor.entity_id AS neighbor LIMIT 15",
                            concept=concept,
                        )
                        return [rec.get("neighbor") for rec in res if rec.get("neighbor")]
                result["ontology_neighbors"] = await asyncio.to_thread(_neighbors)
        except Exception as e:
            logger.warning(f"get_user_subgraph: ontology neighbors failed: {e}")
        return result

    # ---- LRU fallback helpers ----

    def _lru_set(self, key: str, value: str) -> None:
        """Set value in in-memory LRU cache (bounded)."""
        self._lru_fallback[key] = value
        self._lru_fallback.move_to_end(key)
        # Evict oldest entries if over cap
        while len(self._lru_fallback) > _LRU_MAX_SIZE:
            self._lru_fallback.popitem(last=False)

    def _lru_get(self, key: str) -> Optional[str]:
        """Get value from in-memory LRU cache."""
        if key in self._lru_fallback:
            self._lru_fallback.move_to_end(key)
            return self._lru_fallback[key]
        return None