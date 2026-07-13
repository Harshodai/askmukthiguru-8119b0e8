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

from app.config import settings
from app.metrics import MEMORY_LRU_EVICTIONS
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

    async def classify_memory_content(self, content: str) -> dict[str, Any]:
        """Classify user reflection/memory to extract insight, state category, and related concepts."""
        try:
            import json as _json
            from openai import AsyncOpenAI

            # Build client based on active LLM provider
            if settings.is_sarvam_cloud:
                client = AsyncOpenAI(
                    base_url=settings.sarvam_base_url,
                    api_key="api-key-not-used-by-bearer",
                    default_headers={"api-subscription-key": settings.sarvam_api_key},
                )
                model_name = settings.sarvam_cloud_classify_model or "sarvam-30b"
            elif settings.llm_provider.lower() == "openrouter":
                client = AsyncOpenAI(
                    base_url=settings.openrouter_base_url,
                    api_key=settings.openrouter_api_key,
                )
                model_name = settings.model_for_classification
            elif settings.llm_provider.lower() == "nim":
                client = AsyncOpenAI(
                    base_url=settings.nim_base_url,
                    api_key=settings.nim_api_key,
                )
                model_name = settings.nim_classify_model
            elif settings.llm_provider.lower() == "ollama":
                client = AsyncOpenAI(
                    base_url=settings.ollama_base_url,
                    api_key="ollama",
                )
                model_name = settings.model_for_classification
            else:
                return {}

            system_msg = (
                "You are an expert spiritual counselor trained in Ekam teachings. "
                "Analyze the user's reflection or memory and classify it. "
                "Return ONLY a valid JSON object."
            )
            user_msg = (
                f"Classify and extract from a personal reflection:\n"
                f"1. insight: A concise 3-6 word summary (e.g. 'Work Stress Anxiety', 'Daily Chanting Practice', 'Gratitude for Family'). Do NOT use 'User asked X'. Write as a short noun phrase in first person representing their state.\n"
                f"2. state_category: Categorize into one of these exact states: 'Beautiful State', 'Suffering State', 'Shrinking Self', 'Destructive Self', 'Inert Self', or 'Neutral'.\n"
                f"3. related_concepts: List of concept names this relates to (e.g. 'Meditation', 'Karma', 'Soul Sync', 'Consciousness', 'Ekam', 'Dharma', 'Oneness', 'Surrender', 'Awareness', 'Connection').\n\n"
                f"Return ONLY this JSON:\n"
                f'{{"insight": "...", "state_category": "...", "related_concepts": []}}\n\n'
                f"Analyze this personal reflection: \"{content}\""
            )

            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.0,
                    max_tokens=256,
                ),
                timeout=15.0,
            )
            raw_content = (response.choices[0].message.content or "").strip()
            if raw_content.startswith("```"):
                import re as _re
                raw_content = _re.sub(r"^```(?:json)?\n?(.*?)\n?```$", r"\1", raw_content, flags=_re.DOTALL).strip()
            first_brace = raw_content.find("{")
            last_brace = raw_content.rfind("}")
            if first_brace != -1 and last_brace != -1:
                return _json.loads(raw_content[first_brace : last_brace + 1])
        except Exception as e:
            logger.warning(f"classify_memory_content failed: {e}")
        return {}

    async def add_explicit(
        self,
        user_id: str,
        content: str,
        is_core: bool = False,
        source: str = "explicit",
        run_compaction: bool = True,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Manually add a memory, and write it to both Supabase and Neo4j."""
        # Pre-check for duplicate/merge target in Supabase (to handle superseding in Neo4j)
        merge_target_id: str | None = None
        if not is_core:
            try:
                emb_dict = await asyncio.to_thread(
                    self._embedding_service.encode_single_full, content
                )
                embedding = emb_dict.get("dense")
                if embedding and not self._search_disabled:
                    dup_result = await asyncio.to_thread(
                        self._supabase.rpc(
                            "match_user_memories_by_user",
                            {
                                "p_user_id": user_id,
                                "p_query_embedding": embedding,
                                "p_k": 1,
                                "p_min_sim": 0.88,
                            },
                        ).execute
                    )
                    if dup_result and dup_result.data:
                        first_match = dup_result.data[0]
                        if isinstance(first_match, dict) and isinstance(first_match.get("id"), str):
                            merge_target_id = first_match.get("id")
            except Exception as dup_err:
                logger.debug(f"Pre-merge duplicate check skipped: {dup_err}")

        # Step 1: Classify if metadata not provided
        classified = metadata
        if not is_core:
            if not classified:
                classified = await self.classify_memory_content(content)
            
            # Ensure classification results exist
            if not classified:
                classified = {
                    "insight": content[:30],
                    "state_category": "Neutral",
                    "related_concepts": []
                }
            else:
                if "insight" not in classified:
                    classified["insight"] = content[:30]
                if "state_category" not in classified:
                    classified["state_category"] = "Neutral"
                if "related_concepts" not in classified:
                    classified["related_concepts"] = []

        # Step 2: Save to Supabase (using updated base implementation)
        res = await super().add_explicit(user_id, content, is_core, source, run_compaction, classified)

        # Step 3: Write to Neo4j
        if not is_core and res and "id" in res:
            try:
                driver = await asyncio.to_thread(self._get_neo4j)
                if driver:
                    import uuid
                    from services.tenant_context import TenantContext
                    tenant_id = TenantContext.get()
                    mem_id = str(res["id"])
                    insight = classified.get("insight") or content[:30]
                    state_cat = classified.get("state_category") or "Neutral"
                    rel_concepts = classified.get("related_concepts") or []

                    # If merging, generate a new UUID for the Neo4j node so we preserve the old node
                    new_mem_id = merge_target_id if merge_target_id else mem_id

                    def _write_neo4j():
                        with driver.session() as session:
                            if merge_target_id:
                                # 1. Mark old memory node as superseded
                                session.run(
                                    """
                                    MATCH (m:GlobalMemory {id: $old_id})
                                    SET m.is_superseded = true,
                                        m.decay_score = 0.05
                                    """,
                                    old_id=merge_target_id
                                )
                                # 2. Create the new memory node, and link to User + old memory node
                                session.run(
                                    """
                                    MERGE (u:User {id: $user_id})
                                    SET u.tenant_id = $tenant_id
                                    MERGE (m:GlobalMemory {id: $memory_id})
                                    SET m.content = $content,
                                        m.insight = $insight,
                                        m.state_category = $state_category,
                                        m.created_at = timestamp(),
                                        m.tenant_id = $tenant_id
                                    MERGE (u)-[:HAS_MEMORY]->(m)
                                    WITH m
                                    MATCH (old:GlobalMemory {id: $old_id})
                                    MERGE (old)-[:SUPERSEDED_BY]->(m)
                                    """,
                                    user_id=user_id,
                                    memory_id=new_mem_id,
                                    content=content,
                                    insight=insight,
                                    state_category=state_cat,
                                    tenant_id=tenant_id,
                                    old_id=merge_target_id
                                )
                                target_mem_id = new_mem_id
                            else:
                                # Standard insert flow
                                session.run(
                                    """
                                    MERGE (u:User {id: $user_id})
                                    SET u.tenant_id = $tenant_id
                                    MERGE (m:GlobalMemory {id: $memory_id})
                                    SET m.content = $content,
                                        m.insight = $insight,
                                        m.state_category = $state_category,
                                        m.created_at = timestamp(),
                                        m.tenant_id = $tenant_id
                                    MERGE (u)-[:HAS_MEMORY]->(m)
                                    """,
                                    user_id=user_id,
                                    memory_id=mem_id,
                                    content=content,
                                    insight=insight,
                                    state_category=state_cat,
                                    tenant_id=tenant_id,
                                )
                                target_mem_id = mem_id

                            # 3. Relate to state category if it's a known ontology node
                            session.run(
                                """
                                MATCH (m:GlobalMemory {id: $memory_id})
                                MATCH (c) WHERE (c:Concept OR c:Teacher OR c:Practice) AND toLower(c.entity_id) = toLower($state_cat)
                                MERGE (m)-[:RELATES_TO]->(c)
                                """,
                                memory_id=target_mem_id,
                                state_cat=state_cat
                            )

                            # 4. Relate to concepts
                            for concept in rel_concepts:
                                session.run(
                                    """
                                    MATCH (m:GlobalMemory {id: $memory_id})
                                    MATCH (c) WHERE (c:Concept OR c:Teacher OR c:Practice) AND toLower(c.entity_id) = toLower($concept)
                                    MERGE (m)-[:RELATES_TO]->(c)
                                    """,
                                    memory_id=target_mem_id,
                                    concept=concept,
                                )

                    await asyncio.to_thread(_write_neo4j)
            except Exception as e:
                logger.warning(f"Neo4j memory write failed (non-fatal): {e}")

        return res

    async def forget(self, user_id: str, memory_id: str) -> bool:
        """Forget memory: delete from Supabase PG and Neo4j graph."""
        res = await super().forget(user_id, memory_id)
        if res:
            try:
                driver = await asyncio.to_thread(self._get_neo4j)
                if driver:
                    def _delete():
                        with driver.session() as session:
                            session.run(
                                "MATCH (m:GlobalMemory {id: $memory_id}) DETACH DELETE m",
                                memory_id=memory_id
                            )
                    await asyncio.to_thread(_delete)
            except Exception as e:
                logger.warning(f"Neo4j forget failed (non-fatal): {e}")
        return res

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
                password = os.environ.get("NEO4J_PASSWORD", "")
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

    # ---- Personal Knowledge Graph ----
    # Cache: {(user_id, view): (result, expires_at)} — 60s TTL, keeps Neo4j
    # off the request path on repeat profile visits (Supermemory-style hot graph).
    _KG_CACHE: dict[tuple, tuple[dict, float]] = {}
    _KG_TTL = 60.0

    async def build_personal_knowledge_graph(self, user_id: Optional[str], view: str = "personal") -> dict[str, list[dict]]:
        """Build a {nodes, edges} knowledge graph for the user.

        - view=="ontology" or no user_id → public teaching ontology (limit 200).
        - view=="personal" with user_id → consciousness map: user + memories +
          concept edges + memory↔memory SHARED_STATE edges (Supermemory-style
          peer links so isolated memories still connect through shared meaning).
        Results are cached for 60s per (user_id, view).
        """
        cache_key = (user_id or "anon", view)
        cached = self._KG_CACHE.get(cache_key)
        if cached and cached[1] > time.time():
            return cached[0]

        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        # O(1) edge dedup — replaces the O(n²) `edge not in edges` scan that
        # made large graphs quadratic during construction.
        edges_seen: set[tuple[str, str, Optional[str]]] = set()

        def _add_node(uid: str, label: str, ntype: str, teacher: str | None = None,
                      state_category: str | None = None, content: str | None = None) -> None:
            if uid not in nodes:
                nodes[uid] = {
                    "id": uid,
                    "label": label,
                    "type": ntype,
                    "teacher": teacher,
                    "state_category": state_category,
                    "content": content
                }

        def _add_edge(src: str, dst: str, label: str | None = None) -> None:
            key = (src, dst, label)
            if key in edges_seen or src == dst:
                return
            edges_seen.add(key)
            edges.append({"source": src, "target": dst, "label": label})

        # 1. Public Ontology View
        if view == "ontology" or not user_id:
            try:
                driver = await asyncio.to_thread(self._get_neo4j)
                if driver is not None:
                    def _query_ontology():
                        with driver.session() as session:
                            res1 = session.run(
                                "MATCH (c) WHERE c:Concept OR c:Teacher OR c:Practice "
                                "RETURN c.entity_id AS eid, labels(c) AS labels "
                                "LIMIT 50"
                            )
                            ontology = [r.data() for r in res1 if r.get("eid")]

                            res2 = session.run(
                                "MATCH (c1)-[r]->(c2) "
                                "WHERE (c1:Concept OR c1:Teacher OR c1:Practice) "
                                "  AND (c2:Concept OR c2:Teacher OR c2:Practice) "
                                "  AND type(r) IN ['EXPOUNDS', 'PRACTICE_FOR', 'CONTRASTS_WITH', 'SYNONYMOUS_WITH'] "
                                "RETURN c1.entity_id AS source, c2.entity_id AS target, type(r) AS rel_type"
                            )
                            edges_data = [r.data() for r in res2 if r.get("source") and r.get("target")]
                            return ontology, edges_data
                    
                    ontology, edges_data = await asyncio.to_thread(_query_ontology)
                    for c in ontology:
                        eid = c["eid"]
                        labels = c.get("labels", ["Concept"])
                        ntype = next((lbl for lbl in labels if lbl in ("Concept", "Teacher", "Practice")), "Concept")
                        _add_node(f"concept:{eid}", eid, ntype, eid if ntype == "Teacher" else None)
                    for edge in edges_data:
                        _add_edge(f"concept:{edge['source']}", f"concept:{edge['target']}", edge['rel_type'])
            except Exception as e:
                logger.warning(f"build_personal_knowledge_graph ontology view failed: {e}")
            result = {"nodes": list(nodes.values()), "edges": edges}
            self._KG_CACHE[cache_key] = (result, time.time() + self._KG_TTL)
            return result

        # 2. Personal View
        # Check memories count from both Neo4j and Supabase
        neo4j_mems = []
        supabase_mems = []
        concept_nodes: dict[str, list[str]] = {}

        def _associate_concept(concept_name: str, item_id: str) -> None:
            c_key = concept_name.lower().strip()
            if c_key:
                concept_nodes.setdefault(c_key, []).append(item_id)

        try:
            driver = await asyncio.to_thread(self._get_neo4j)
            if driver is not None:
                def _query_memories():
                    with driver.session() as session:
                        res = session.run(
                            "MATCH (u:User {id: $uid})-[:HAS_MEMORY]->(m:GlobalMemory) "
                            "WHERE m.is_superseded IS NULL OR NOT m.is_superseded = true "
                            "RETURN m.id AS id, m.content AS content, m.insight AS insight, m.state_category AS state_category, m.created_at AS created_at",
                            uid=user_id
                        )
                        return [r.data() for r in res]
                neo4j_mems = await asyncio.to_thread(_query_memories)
        except Exception as e:
            logger.warning(f"Failed to query Neo4j memories: {e}")

        try:
            mems_res = await self.list_memories(user_id, page=1, page_size=50)
            supabase_mems = mems_res.get("memories", [])
        except Exception as e:
            logger.warning(f"Failed to query Supabase memories: {e}")

        # Fetch user's study notebooks and their items
        notebook_items = []
        try:
            notebooks_res = await asyncio.to_thread(
                self._supabase.table("study_notebooks")
                .select("id")
                .eq("user_id", user_id)
                .execute
            )
            notebook_ids = [nb.get("id") for nb in (notebooks_res.data or []) if nb.get("id")]
            if notebook_ids:
                items_res = await asyncio.to_thread(
                    self._supabase.table("study_notebook_items")
                    .select("id, query, answer, created_at")
                    .in_("notebook_id", notebook_ids)
                    .limit(50)
                    .execute
                )
                notebook_items = items_res.data or []
        except Exception as e:
            logger.warning(f"Failed to query study notebook items for KG: {e}")

        # If absolutely no memories and no notebook items, return empty graph to trigger empty state in UI
        if not neo4j_mems and not supabase_mems and not notebook_items:
            empty = {"nodes": [], "edges": []}
            self._KG_CACHE[cache_key] = (empty, time.time() + self._KG_TTL)
            return empty

        # User is authenticated. Build the personalized Consciousness Map!
        _add_node(f"user:{user_id}", "You", "User")

        # Set up state categories as base concepts so they exist in our graph
        state_categories = ["Beautiful State", "Suffering State", "Shrinking Self", "Destructive Self", "Inert Self"]
        for sc in state_categories:
            _add_node(f"concept:{sc}", sc, "Concept")

        concept_ids_in_graph = set(state_categories)

        # Track memories we've processed
        processed_memory_ids = set()

        # Add Neo4j memories
        for m in neo4j_mems:
            mid = m["id"]
            content = m.get("content", "")
            insight = m.get("insight") or content[:30]
            state_cat = m.get("state_category") or "Neutral"
            processed_memory_ids.add(mid)

            _add_node(f"memory:{mid}", insight, "Memory", state_category=state_cat, content=content)
            _add_edge(f"user:{user_id}", f"memory:{mid}", "HAS_MEMORY")

            if state_cat in state_categories:
                _add_edge(f"memory:{mid}", f"concept:{state_cat}", "IN_STATE")
                _associate_concept(state_cat, f"memory:{mid}")

        # Add Supabase memories if not already processed
        for m in supabase_mems:
            mid = str(m.get("id", ""))
            if not mid or mid in processed_memory_ids:
                continue
            content = m.get("content", "")
            claim = m.get("claim") or content[:30]
            
            # Extract state category if possible
            state_cat = "Neutral"
            _add_node(f"memory:{mid}", claim, "Memory", state_category=state_cat, content=content)
            _add_edge(f"user:{user_id}", f"memory:{mid}", "HAS_MEMORY")

        # Now, query relationships between the memories and ontology concepts from Neo4j
        referenced_concept_ids = set()
        if neo4j_mems:
            try:
                def _query_memory_ontology_rels():
                    with driver.session() as session:
                        res = session.run(
                            "MATCH (m:GlobalMemory)-[r:RELATES_TO]->(c) "
                            "WHERE m.id IN $mids AND (c:Concept OR c:Teacher OR c:Practice) "
                            "RETURN m.id AS mid, c.entity_id AS cid, labels(c)[0] AS clabel",
                            mids=list(processed_memory_ids)
                        )
                        return [r.data() for r in res]
                rels = await asyncio.to_thread(_query_memory_ontology_rels)
                for r in rels:
                    mid = r["mid"]
                    cid = r["cid"]
                    clabel = r["clabel"] or "Concept"
                    _add_node(f"concept:{cid}", cid, clabel, cid if clabel == "Teacher" else None)
                    _add_edge(f"memory:{mid}", f"concept:{cid}", "RELATES_TO")
                    _associate_concept(cid, f"memory:{mid}")
                    concept_ids_in_graph.add(cid)
                    referenced_concept_ids.add(cid)
            except Exception as e:
                logger.warning(f"Failed to query memory ontology rels: {e}")

        # For any memories that were not in Neo4j, do keyword matching fallback
        concept_keywords = {sc.lower(): sc for sc in state_categories}
        try:
            def _get_all_concepts():
                with driver.session() as session:
                    res = session.run("MATCH (c) WHERE c:Concept OR c:Teacher OR c:Practice RETURN c.entity_id AS eid")
                    return [r["eid"] for r in res]
            all_concepts = await asyncio.to_thread(_get_all_concepts)
            for cid in all_concepts:
                concept_keywords[cid.lower()] = cid
        except Exception:
            pass

        for m in supabase_mems:
            mid = str(m.get("id", ""))
            if mid in processed_memory_ids:
                continue
            content = m.get("content", "").lower()
            for kw, cid in concept_keywords.items():
                if kw in content:
                    _add_node(f"concept:{cid}", cid, "Concept")
                    _add_edge(f"memory:{mid}", f"concept:{cid}", "RELATES_TO")
                    _associate_concept(cid, f"memory:{mid}")
                    concept_ids_in_graph.add(cid)

        # 3. Add Study Notebook Items
        for item in notebook_items:
            nid = str(item.get("id", ""))
            if not nid:
                continue
            query = item.get("query", "")
            answer = item.get("answer", "")
            label = query[:30] + ("..." if len(query) > 30 else "")
            
            _add_node(f"notebook:{nid}", label, "NotebookItem", content=f"Q: {query}\nA: {answer}")
            _add_edge(f"user:{user_id}", f"notebook:{nid}", "SAVED_NOTE")
            
            # Find related concepts using content keyword matching
            full_text = (query + " " + answer).lower()
            for kw, cid in concept_keywords.items():
                if kw in full_text:
                    _add_node(f"concept:{cid}", cid, "Concept")
                    _add_edge(f"notebook:{nid}", f"concept:{cid}", "REFERENCES")
                    _associate_concept(cid, f"notebook:{nid}")
                    concept_ids_in_graph.add(cid)

        # Query and add relationships between the matched ontology concepts
        if concept_ids_in_graph:
            try:
                def _query_concept_rels():
                    with driver.session() as session:
                        res = session.run(
                            "MATCH (c1)-[r]->(c2) "
                            "WHERE (c1:Concept OR c1:Teacher OR c1:Practice) "
                            "  AND (c2:Concept OR c2:Teacher OR c2:Practice) "
                            "  AND c1.entity_id IN $cids AND c2.entity_id IN $cids "
                            "  AND type(r) IN ['EXPOUNDS', 'PRACTICE_FOR', 'CONTRASTS_WITH', 'SYNONYMOUS_WITH'] "
                            "RETURN c1.entity_id AS source, c2.entity_id AS target, type(r) AS rel_type",
                            cids=list(concept_ids_in_graph)
                        )
                        return [r.data() for r in res]
                concept_rels = await asyncio.to_thread(_query_concept_rels)
                for r in concept_rels:
                    _add_edge(f"concept:{r['source']}", f"concept:{r['target']}", r['rel_type'])
            except Exception as e:
                logger.warning(f"Failed to query concept rels: {e}")

        # Memory↔Memory peer edges: group memories by state_category so isolated
        # reflections still connect through shared meaning. Supermemory-style
        # "similar memory" hint — one dashed edge per pair, capped to avoid
        # visual noise on large graphs.
        try:
            by_state: dict[str, list[str]] = {}
            for n in nodes.values():
                if n["type"] == "Memory" and n.get("state_category") and n["state_category"] != "Neutral":
                    by_state.setdefault(n["state_category"], []).append(n["id"])
            _peer_cap = 40  # ponytail: bump if UI clarity holds at higher densities
            _added = 0
            for state, mids in by_state.items():
                if len(mids) < 2:
                    continue
                # Chain memories in a ring so each has ≤2 peer edges — dense
                # enough to show clusters, sparse enough to stay legible.
                for i, src in enumerate(mids):
                    dst = mids[(i + 1) % len(mids)]
                    _add_edge(src, dst, "SHARED_STATE")
                    _added += 1
                    if _added >= _peer_cap:
                        break
                if _added >= _peer_cap:
                    break
        except Exception as e:
            logger.warning(f"Failed to add peer memory edges: {e}")

        # Add Concept Sharing peer edges (Recall principle)
        try:
            _concept_peer_cap = 40
            _concept_peers_added = 0
            for c_key, items in concept_nodes.items():
                unique_items = list(dict.fromkeys(items))
                if len(unique_items) < 2:
                    continue
                # Chain items in a ring/cycle to avoid visual clutter
                for i, src in enumerate(unique_items):
                    dst = unique_items[(i + 1) % len(unique_items)]
                    _add_edge(src, dst, "SHARED_CONCEPT")
                    _concept_peers_added += 1
                    if _concept_peers_added >= _concept_peer_cap:
                        break
                if _concept_peers_added >= _concept_peer_cap:
                    break
        except Exception as e:
            logger.warning(f"Failed to add concept peer edges: {e}")

        result = {"nodes": list(nodes.values()), "edges": edges}
        self._KG_CACHE[cache_key] = (result, time.time() + self._KG_TTL)
        # Evict old cache entries (bounded).
        if len(self._KG_CACHE) > 256:
            oldest = min(self._KG_CACHE, key=lambda k: self._KG_CACHE[k][1])
            self._KG_CACHE.pop(oldest, None)
        return result

    # ---- LRU fallback helpers ----
    def _lru_set(self, key: str, value: str) -> None:
        """Set value in in-memory LRU cache (bounded)."""
        self._lru_fallback[key] = value
        self._lru_fallback.move_to_end(key)
        # Evict oldest entries if over cap
        while len(self._lru_fallback) > _LRU_MAX_SIZE:
            self._lru_fallback.popitem(last=False)
            MEMORY_LRU_EVICTIONS.inc()

    def _lru_get(self, key: str) -> Optional[str]:
        """Get value from in-memory LRU cache."""
        if key in self._lru_fallback:
            self._lru_fallback.move_to_end(key)
            return self._lru_fallback[key]
        return None