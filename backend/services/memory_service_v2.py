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
from dataclasses import dataclass
from typing import Any, Optional

from redis import asyncio as aioredis

from services.memory_service import MemoryService

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
EPHEMERAL_TTL = 900  # 15 minutes
GLOBAL_MEMORY_COLLECTION = "global_memory"


@dataclass
class MemoryTierResult:
    source: str
    memories: list[dict[str, Any]]
    latency_ms: float
    error: Optional[str] = None


class MemoryServiceV2(MemoryService):
    """Three-tier memory service with isolated fallback per tier."""

    def __init__(self, supabase_client=None, embedding_service=None, llm_service=None):
        super().__init__(supabase_client, embedding_service, llm_service)
        self._redis: Optional[aioredis.Redis] = None
        self._neo4j_driver = None

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
        if not redis:
            return False
        try:
            await redis.setex(f"ephemeral:{user_id}:{key}", ttl, json.dumps(value))
            return True
        except Exception as e:
            logger.warning(f"Ephemeral set failed: {e}")
            return False

    async def get_ephemeral(self, user_id: str, key: str) -> Optional[Any]:
        redis = await self._get_redis()
        if not redis:
            return None
        try:
            data = await redis.get(f"ephemeral:{user_id}:{key}")
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning(f"Ephemeral get failed: {e}")
            return None

    async def get_ephemeral_session(self, user_id: str, session_id: str) -> dict[str, Any]:
        redis = await self._get_redis()
        if not redis:
            return {}
        try:
            keys = await redis.keys(f"ephemeral:{user_id}:session:{session_id}:*")
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
        try:
            pattern = f"ephemeral:{user_id}:{session_id + ':' if session_id else ''}*"
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
                    collection_name=GLOBAL_MEMORY_COLLECTION,
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
                async with driver.session() as session:
                    await session.run(
                        """
                        MERGE (u:User {id: $user_id})
                        MERGE (m:GlobalMemory {id: $memory_id})
                        SET m.content = $content, m.created_at = timestamp()
                        MERGE (u)-[:HAS_MEMORY]->(m)
                        """,
                        user_id=user_id,
                        memory_id=f"global:{user_id}:{hash(content) % 10**15}",
                        content=content,
                    )
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
                collection_name=GLOBAL_MEMORY_COLLECTION,
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

            async with driver.session() as session:
                result = await session.run(
                    """
                    MATCH (u:User {id: $user_id})-[:HAS_MEMORY]->(m:GlobalMemory)
                    OPTIONAL MATCH (m)-[:RELATED_TO]->(related:GlobalMemory)
                    RETURN m.content AS memory, collect(DISTINCT related.content) AS related_memories
                    LIMIT 20
                    """,
                    user_id=user_id,
                )
                records = await result.data()
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
                    results = await self.search_global(embedding, limit=limit, user_id=user_id)
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