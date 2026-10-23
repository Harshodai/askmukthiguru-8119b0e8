"""Three-Tier Memory Service (v2).

Extends MemoryService with:
  Tier 1 — Ephemeral (Redis): short-term session context, 15-min TTL
  Tier 2 — Semantic (PG+Qdrant): long-term vector search (existing v1)
  Tier 3 — Global (Qdrant Cluster+Neo4j): cross-user knowledge graph memory

All tiers are independently operational — failures in one don't block others.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import logging
import os
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

from redis import asyncio as aioredis

from app.config import settings
from app.metrics import MEMORY_LRU_EVICTIONS
from services import kg_analytics
from services.memory_service import MemoryService, _derive_fact_key
from services.tenant_context import TenantContext

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
EPHEMERAL_TTL = 900  # 15 minutes
# ponytail: in-memory LRU fallback cap, bump if eviction rate >5%.
# Restored 2026-10-20: the constant was dropped in an uncommitted edit while
# _lru_set still referenced it (ruff F821), so every Redis-down write raised
# NameError instead of evicting.
_LRU_MAX_SIZE = 1000
GLOBAL_MEMORY_COLLECTION = "global_memory"
_CANONICAL_PRACTICES: dict[str, str] = {
    "Soul Sync": "Sri Preethaji",
    "Serene Mind": "Sri Preethaji",
    "Witnessing Awareness": "Sri Krishnaji",
    "Stillness Meditation": "Sri Preethaji",
    "Observation": "Sri Krishnaji",
    "Compassion": "Sri Preethaji",
}
_CANONICAL_TEACHERS: set[str] = {"Sri Preethaji", "Sri Krishnaji"}
_DEFAULT_CONCEPT_CATALOG: list[str] = [
    "Soul Sync",
    "Serene Mind",
    "Witnessing Awareness",
    "Beautiful State",
    "Suffering State",
    "Stillness",
    "Compassion",
    "Sri Krishnaji",
    "Sri Preethaji",
    "Observation",
    "Connection",
    "Oneness",
    "Meditation",
]


def _resolve_concept_meta(cid: str) -> tuple[str, Optional[str], Optional[str]]:
    """Returns (node_type, teacher_name, state_category) for an ontology concept."""
    if cid in _CANONICAL_PRACTICES:
        return "Practice", _CANONICAL_PRACTICES[cid], None
    if cid in _CANONICAL_TEACHERS:
        return "Teacher", cid, None
    cid_lower = cid.lower()
    for p_name, teacher in _CANONICAL_PRACTICES.items():
        if p_name.lower() == cid_lower:
            return "Practice", teacher, None
    for t_name in _CANONICAL_TEACHERS:
        if t_name.lower() == cid_lower:
            return "Teacher", t_name, None
    if "state" in cid_lower or cid_lower in (
        "calm",
        "peace",
        "stillness",
        "anxiety",
        "fear",
        "stress",
        # Suffering-state names that do not contain the word "state": without
        # these, "Shrinking Self"/"Destructive Self"/"Inert Self" resolved to
        # Concept and created concept:* duplicates next to the existing
        # state:* node for the same concept.
        "shrinking self",
        "destructive self",
        "inert self",
    ):
        is_suffering = any(
            w in cid_lower
            for w in [
                "suffering",
                "shrink",
                "destruct",
                "inert",
                "anxiet",
                "fear",
                "anger",
                "stress",
            ]
        )
        return "State", None, "Suffering State" if is_suffering else "Beautiful State"
    return "Concept", None, None


@dataclass
class MemoryTierResult:
    source: str
    memories: list[dict[str, Any]]
    latency_ms: float
    error: Optional[str] = None


class MemoryMutationIncompleteError(RuntimeError):
    """A primary memory mutation completed but a derived private projection is unconfirmed."""


class MemoryServiceV2(MemoryService):
    """Three-tier memory service with isolated fallback per tier."""

    def __init__(
        self,
        supabase_client=None,
        embedding_service=None,
        llm_service=None,
        *,
        guru_slug: str = "default",
        use_global_memory: bool = False,
        neo4j_driver=None,
        neo4j_driver_accessor=None,
    ):
        super().__init__(supabase_client, embedding_service, llm_service)
        self.guru_slug = guru_slug
        self.use_global_memory = use_global_memory
        self._redis: Optional[aioredis.Redis] = None
        self._neo4j_driver = neo4j_driver
        self._neo4j_driver_accessor = neo4j_driver_accessor
        self._owns_neo4j_driver = False
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
                f'Analyze this personal reflection: "{content}"'
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

                raw_content = _re.sub(
                    r"^```(?:json)?\n?(.*?)\n?```$", r"\1", raw_content, flags=_re.DOTALL
                ).strip()
            first_brace = raw_content.find("{")
            last_brace = raw_content.rfind("}")
            if first_brace != -1 and last_brace != -1:
                return _json.loads(raw_content[first_brace : last_brace + 1])
        except Exception as e:
            logger.warning("classify_memory_content failed (%s)", type(e).__name__)
        return {}

    async def add_atoms(
        self,
        user_id: str,
        session_id: str,
        atoms: list[Any],
    ) -> None:
        """Persist L1 atomic memories to Supabase and Neo4j."""
        from services.layered_memory.models import MemoryAtom

        for atom in atoms:
            if not isinstance(atom, MemoryAtom):
                continue
            classified = {
                "insight": atom.content[:40],
                "state_category": "Neutral",
                "related_concepts": atom.metadata.get("related_concepts", []),
                "atom_type": atom.type,
                "priority": atom.priority,
                "scene_name": atom.scene_name,
                "source_message_ids": atom.source_message_ids,
                "session_id": session_id,
            }
            await self.add_explicit(
                user_id,
                atom.content,
                is_core=False,
                source="l1_atom",
                run_compaction=False,
                metadata=classified,
            )

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
        # Read active rows for the deterministic fact key before inserting. This
        # is deliberately independent of embedding similarity so a reworded
        # contradiction still supersedes the prior Neo4j memory node.
        superseded_ids: list[str] = []
        fact_key = _derive_fact_key(content, metadata)
        if not is_core and fact_key and self._supabase:
            try:
                active_result = await asyncio.to_thread(
                    self._supabase.table("guru_memories")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("tenant_id", TenantContext.get())
                    .eq("fact_key", fact_key)
                    .is_("valid_to", "null")
                    .execute
                )
                superseded_ids = [
                    row["id"]
                    for row in (active_result.data or [])
                    if isinstance(row, dict) and isinstance(row.get("id"), str)
                ]
            except Exception as key_err:
                logger.warning("Neo4j fact-key lookup unavailable for %s: %s", fact_key, key_err)

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
                    "related_concepts": [],
                }
            else:
                if "insight" not in classified:
                    classified["insight"] = content[:30]
                if "state_category" not in classified:
                    classified["state_category"] = "Neutral"
                if "related_concepts" not in classified:
                    classified["related_concepts"] = []

        # Classification can supply the fact key when metadata was omitted.
        # Re-run the same deterministic lookup after classification so the graph
        # path also supersedes automatically extracted factual memories.
        fact_key = _derive_fact_key(content, classified)
        if not is_core and fact_key and not superseded_ids and self._supabase:
            try:
                active_result = await asyncio.to_thread(
                    self._supabase.table("guru_memories")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("fact_key", fact_key)
                    .is_("valid_to", "null")
                    .execute
                )
                superseded_ids = [
                    row["id"]
                    for row in (active_result.data or [])
                    if isinstance(row, dict) and isinstance(row.get("id"), str)
                ]
            except Exception as key_err:
                logger.warning(
                    "Neo4j classified fact-key lookup unavailable for %s: %s", fact_key, key_err
                )

        # Step 2: Save to Supabase (using updated base implementation)
        res = await super().add_explicit(
            user_id, content, is_core, source, run_compaction, classified
        )

        # Step 3: Write to Neo4j
        if not is_core and res and "id" in res:
            try:
                driver = await asyncio.to_thread(self._get_neo4j)
                if driver:
                    tenant_id = TenantContext.get()
                    mem_id = str(res["id"])
                    insight = classified.get("insight") or content[:30]
                    state_cat = classified.get("state_category") or "Neutral"
                    rel_concepts = classified.get("related_concepts") or []

                    # Keep the newly inserted memory node as the canonical
                    # current value; old nodes remain for audit/history only.
                    new_mem_id = mem_id

                    def _write_neo4j():
                        with driver.session() as session:
                            if superseded_ids:
                                for old_id in superseded_ids:
                                    session.run(
                                        """
                                        MATCH (m:GlobalMemory {id: $old_id, tenant_id: $tenant_id})
                                        SET m.is_superseded = true,
                                            m.decay_score = 0.05
                                        """,
                                        old_id=old_id,
                                        tenant_id=tenant_id,
                                    )

                                session.run(
                                    """
                                    MERGE (u:User {tenant_id: $tenant_id, id: $user_id})
                                    SET u.tenant_id = $tenant_id
                                    MERGE (m:GlobalMemory {id: $memory_id})
                                    SET m.user_id = $user_id,
                                        m.content = $content,
                                        m.insight = $insight,
                                        m.state_category = $state_category,
                                        m.created_at = timestamp(),
                                        m.tenant_id = $tenant_id
                                    MERGE (u)-[:HAS_MEMORY]->(m)
                                    WITH m
                                    UNWIND $old_ids AS old_id
                                    MATCH (old:GlobalMemory {id: old_id, tenant_id: $tenant_id})
                                    MERGE (old)-[:SUPERSEDED_BY]->(m)
                                    """,
                                    user_id=user_id,
                                    memory_id=new_mem_id,
                                    content=content,
                                    insight=insight,
                                    state_category=state_cat,
                                    tenant_id=tenant_id,
                                    old_ids=superseded_ids,
                                )
                                target_mem_id = new_mem_id
                            else:
                                # Standard insert flow
                                session.run(
                                    """
                                    MERGE (u:User {tenant_id: $tenant_id, id: $user_id})
                                    SET u.tenant_id = $tenant_id
                                    MERGE (m:GlobalMemory {id: $memory_id})
                                    SET m.user_id = $user_id,
                                        m.content = $content,
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
                                MATCH (m:GlobalMemory {id: $memory_id, tenant_id: $tenant_id})
                                MATCH (c) WHERE (c:Concept OR c:Teacher OR c:Practice) AND toLower(c.entity_id) = toLower($state_cat)
                                MERGE (m)-[:RELATES_TO]->(c)
                                """,
                                memory_id=target_mem_id,
                                state_cat=state_cat,
                                tenant_id=tenant_id,
                            )

                            # 4. Relate to concepts
                            for concept in rel_concepts:
                                session.run(
                                    """
                                    MATCH (m:GlobalMemory {id: $memory_id, tenant_id: $tenant_id})
                                    MATCH (c) WHERE (c:Concept OR c:Teacher OR c:Practice) AND toLower(c.entity_id) = toLower($concept)
                                    MERGE (m)-[:RELATES_TO]->(c)
                                    """,
                                    memory_id=target_mem_id,
                                    concept=concept,
                                    tenant_id=tenant_id,
                                )

                    await asyncio.to_thread(_write_neo4j)
            except Exception as e:
                logger.warning(f"Neo4j memory write failed (non-fatal): {e}")

        return res

    async def forget(self, user_id: str, memory_id: str) -> bool:
        """Forget an owned memory in Postgres and every reachable graph projection.

        A retry must still clean Neo4j after the Postgres row is already gone.
        Otherwise a non-fatal graph error could make supposedly forgotten
        content reappear because personal-KG reads prefer Neo4j over Postgres.
        """
        postgres_deleted = await super().forget(user_id, memory_id)
        tenant_id = (TenantContext.get() or "").strip()
        if not tenant_id:
            if postgres_deleted:
                raise MemoryMutationIncompleteError(
                    "Memory removed from Postgres but tenant scope is unavailable for graph cleanup"
                )
            return False

        try:
            driver = await asyncio.to_thread(self._get_neo4j)
            if driver is None:
                raise RuntimeError("Neo4j/Memgraph adapter unavailable")

            def _delete_owned_graph_memory() -> int:
                with driver.session() as session:
                    result = session.run(
                        """
                        OPTIONAL MATCH (u:User {id: $user_id, tenant_id: $tenant_id})
                                  -[:HAS_MEMORY]->(linked:GlobalMemory {id: $memory_id, tenant_id: $tenant_id})
                        OPTIONAL MATCH (owned:GlobalMemory {id: $memory_id, user_id: $user_id, tenant_id: $tenant_id})
                        WITH collect(DISTINCT linked) + collect(DISTINCT owned) AS candidates
                        WITH reduce(unique = [], memory IN candidates |
                            CASE WHEN memory IS NULL OR memory IN unique
                                 THEN unique ELSE unique + memory END
                        ) AS memories
                        FOREACH (memory IN memories | DETACH DELETE memory)
                        RETURN size(memories) AS deleted
                        """,
                        user_id=user_id,
                        memory_id=memory_id,
                        tenant_id=tenant_id,
                    )
                    row = result.single()
                    return int(row["deleted"]) if row else 0

            graph_deleted = await asyncio.to_thread(_delete_owned_graph_memory)
            # A false Postgres result is legitimate on retry when the graph node
            # survived a previous partial delete.
            return bool(postgres_deleted or graph_deleted)
        except Exception as exc:
            logger.error(
                "Memory forget is incomplete; graph cleanup unconfirmed (%s)",
                type(exc).__name__,
            )
            raise MemoryMutationIncompleteError(
                "Memory deletion could not be confirmed across all stores; retry the forget operation"
            ) from exc

    async def edit(self, user_id: str, memory_id: str, content: str) -> dict[str, Any]:
        """Edit the PostgreSQL memory and synchronize its tenant-scoped graph copy."""
        updated = await super().edit(user_id, memory_id, content)
        if not updated:
            return {}

        tenant_id = TenantContext.get()
        if not tenant_id:
            return updated
        driver = await asyncio.to_thread(self._get_neo4j)
        if driver is None:
            # The personal KG prefers Neo4j over Postgres. Without confirming
            # graph synchronization, the old statement could still be served.
            raise MemoryMutationIncompleteError(
                "Memory was updated in Postgres but graph synchronization is unavailable; retry the edit"
            )

        try:

            def _update_graph() -> bool:
                with driver.session() as session:
                    result = session.run(
                        """
                        MATCH (m:GlobalMemory {id: $memory_id, tenant_id: $tenant_id})
                        OPTIONAL MATCH (m)-[r:RELATES_TO]->()
                        WITH m, collect(r) AS stale_relations
                        FOREACH (rel IN stale_relations | DELETE rel)
                        SET m.user_id = $user_id,
                            m.content = $content,
                            m.insight = $insight,
                            m.state_category = 'Neutral',
                            m.updated_at = timestamp()
                        RETURN m.id AS id
                        """,
                        user_id=user_id,
                        memory_id=memory_id,
                        tenant_id=tenant_id,
                        content=content,
                        insight=content[:30],
                    )
                    return result.single() is not None

            await asyncio.to_thread(_update_graph)
        except Exception as update_error:
            # A stale projection is worse than a missing projection. If update
            # fails, try deleting only the same user's tenant-scoped graph node;
            # PostgreSQL remains the source of truth and can repopulate it later.
            logger.warning(
                "Graph memory update failed for tenant-scoped memory (%s); removing stale node",
                type(update_error).__name__,
            )
            try:

                def _delete_stale_graph_node() -> None:
                    with driver.session() as session:
                        session.run(
                            "MATCH (m:GlobalMemory {id: $memory_id, tenant_id: $tenant_id}) DETACH DELETE m",
                            memory_id=memory_id,
                            tenant_id=tenant_id,
                        )

                await asyncio.to_thread(_delete_stale_graph_node)
            except Exception as delete_error:
                logger.error(
                    "Could not update or remove the stale graph memory (%s)",
                    type(delete_error).__name__,
                )
                raise MemoryMutationIncompleteError(
                    "Memory was updated in Postgres but its stale graph copy could not be removed; retry the edit"
                ) from delete_error
        return updated

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

    async def set_ephemeral(
        self, user_id: str, key: str, value: Any, ttl: int = EPHEMERAL_TTL
    ) -> bool:
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

    async def clear_ephemeral(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        *,
        all_tenants: bool = False,
    ) -> bool:
        """Clear Redis and process-local ephemeral memory for this user.

        Account erasure must span every tenant namespace. If Redis is unavailable,
        clear the local LRU but return False so callers do not certify full erasure.
        """
        if not user_id:
            return False

        tenant_id = TenantContext.get()
        if not all_tenants and not tenant_id:
            return False

        session_prefix = f"session:{session_id}:" if session_id else ""

        def _matches_lru(key: str) -> bool:
            parts = key.split(":", 3)
            if len(parts) < 3 or parts[0] != "ephemeral" or parts[2] != user_id:
                return False
            if not all_tenants and parts[1] != tenant_id:
                return False
            suffix = parts[3] if len(parts) > 3 else ""
            return not session_id or suffix.startswith(session_prefix)

        # The process-local fallback can retain data written during a Redis
        # outage even after Redis recovers, so purge it independently.
        for cache_key in list(self._lru_fallback):
            if _matches_lru(cache_key):
                self._lru_fallback.pop(cache_key, None)

        redis = await self._get_redis()
        if not redis:
            return False

        pattern = (
            f"ephemeral:*:{user_id}:{session_prefix}*"
            if all_tenants
            else f"ephemeral:{tenant_id}:{user_id}:{session_prefix}*"
        )
        try:
            keys = [key async for key in redis.scan_iter(match=pattern, count=500)]
            for offset in range(0, len(keys), 500):
                await redis.delete(*keys[offset : offset + 500])
            return True
        except Exception as e:
            logger.warning("Ephemeral clear failed (%s)", type(e).__name__)
            return False

    # ---- Tier 3: Global (Qdrant Cluster + Neo4j) ----

    def _get_qdrant_v2(self):
        """Get Qdrant client for global memory collection."""
        try:
            from qdrant_client import QdrantClient

            qdrant_url = os.environ.get("QDRANT_URL_V2") or os.environ.get(
                "QDRANT_URL", "http://qdrant:6333"
            )
            qdrant_api_key = settings.qdrant_api_key or None
            return QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        except Exception as e:
            logger.debug("Failed to create Qdrant client: %s", e)
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
        """Get the shared Neo4j driver, or a bounded process-local fallback."""
        if self._neo4j_driver_accessor is not None:
            try:
                return self._neo4j_driver_accessor()
            except Exception as e:
                logger.warning("Shared Neo4j driver accessor failed: %s", e)
                return None
        if self._neo4j_driver is None:
            try:
                from neo4j import GraphDatabase

                self._neo4j_driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                    max_connection_pool_size=settings.neo4j_max_connection_pool_size,
                    connection_timeout=settings.neo4j_connection_timeout_s,
                    connection_acquisition_timeout=settings.neo4j_connection_acquisition_timeout_s,
                    max_transaction_retry_time=settings.neo4j_max_transaction_retry_time_s,
                    max_connection_lifetime=settings.neo4j_max_connection_lifetime_s,
                    keep_alive=settings.neo4j_keep_alive,
                )
                self._owns_neo4j_driver = True
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
        tenant_id = TenantContext.get() or "default"
        normalized_content = " ".join(content.split())
        memory_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"askmukthiguru:global-memory:{tenant_id}:{user_id}:{normalized_content}",
            )
        )
        success = False

        try:
            client = await asyncio.to_thread(self._get_qdrant_v2)
            if client:
                from qdrant_client.http import models

                point_id = memory_id
                await asyncio.to_thread(
                    client.upsert,
                    collection_name=self._get_memory_collection(guru_slug, use_global_memory),
                    points=[
                        models.PointStruct(
                            id=point_id,
                            vector=embedding,
                            payload={
                                "user_id": user_id,
                                "tenant_id": tenant_id,
                                "content": content,
                                "metadata": metadata or {},
                                "created_at": time.time(),
                            },
                        )
                    ],
                )
                success = True
        except Exception as e:
            logger.warning(f"Global Qdrant write failed: {e}")

        try:
            driver = await asyncio.to_thread(self._get_neo4j)
            if driver:
                # ponytail: to_thread wraps sync neo4j driver; migrate to AsyncGraphDatabase past 100 concurrent users
                def _write():
                    with driver.session() as session:
                        session.run(
                            """
                            MERGE (u:User {tenant_id: $tenant_id, id: $user_id})
                            SET u.tenant_id = $tenant_id
                            MERGE (m:GlobalMemory {id: $memory_id})
                            SET m.user_id = $user_id, m.content = $content,
                                m.created_at = timestamp(), m.tenant_id = $tenant_id
                            MERGE (u)-[:HAS_MEMORY]->(m)
                            """,
                            user_id=user_id,
                            memory_id=memory_id,
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
        """Search only the current tenant's memories for one explicit user."""
        try:
            if not user_id:
                logger.warning("Global memory search rejected without user scope")
                return []
            client = await asyncio.to_thread(self._get_qdrant_v2)
            if not client:
                return []

            from qdrant_client.http import models

            if not user_id:
                logger.warning("Global memory search rejected without user scope")
                return []
            tenant_id = TenantContext.get() or "default"
            filter_cond = models.Filter(
                must=[
                    models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
                    models.FieldCondition(
                        key="tenant_id", match=models.MatchValue(value=tenant_id)
                    ),
                ]
            )

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
                        MATCH (u:User {tenant_id: $tenant_id, id: $user_id})-[:HAS_MEMORY]->(m:GlobalMemory)
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
            logger.warning("Neo4j graph query failed (%s)", type(e).__name__)
            return []

    async def purge_all_user_data(self, user_id: str) -> dict[str, Any]:
        """Legacy partial purge for the original memory service's stores.

        This helper is NOT the account-erasure contract: it does not cover all
        SQL audit/projection tables, tenant-wide cache namespaces, canonical
        vectors, or the Second Brain vault. Account deletion must use
        DELETE /api/account/purge-memory / delete_all_memory_endpoint, which
        attempts each known store and refuses to report success on partial
        failure. Keep complete=False here so callers cannot mistake this
        subset operation for a verified full erasure.
        """
        result: dict[str, Any] = {
            "postgres_core_memory": 0,
            "postgres_episodic_memory": 0,
            "postgres_session_summaries": 0,
            "postgres_user_episodes": 0,
            "postgres_user_scene_blocks": 0,
            "postgres_memory_outbox": 0,
            "postgres_memory_consent_receipts": 0,
            "postgres_canonical_memories": 0,
            "qdrant_deleted": False,
            "neo4j_deleted": False,
            "redis_cleared": False,
            "errors": [],
            "complete": False,
            "scope": "legacy_subset",
        }
        if not user_id or self._is_anonymous(user_id):
            result["errors"].append("invalid_or_anonymous_user")
            return result

        if self._supabase:
            for table, key in (
                ("guru_core_memory", "postgres_core_memory"),
                ("guru_memories", "postgres_episodic_memory"),
                ("guru_session_summaries", "postgres_session_summaries"),
                ("user_episodes", "postgres_user_episodes"),
                ("user_scene_blocks", "postgres_user_scene_blocks"),
                ("memory_outbox", "postgres_memory_outbox"),
                ("memory_consent_receipts", "postgres_memory_consent_receipts"),
                ("canonical_memories", "postgres_canonical_memories"),
            ):
                try:
                    res = await asyncio.to_thread(
                        self._supabase.table(table).delete().eq("user_id", user_id).execute
                    )
                    result[key] = len(res.data) if res and getattr(res, "data", None) else 0
                except Exception as exc:
                    result["errors"].append(f"{table}: {type(exc).__name__}")
                    logger.error(
                        "Legacy memory purge table failed (table=%s, error=%s)",
                        table,
                        type(exc).__name__,
                    )

        try:
            client = await asyncio.to_thread(self._get_qdrant_v2)
            if client:
                from qdrant_client.http import models

                tenant_id = TenantContext.get() or "default"
                await asyncio.to_thread(
                    client.delete,
                    collection_name=GLOBAL_MEMORY_COLLECTION,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="user_id", match=models.MatchValue(value=user_id)
                                ),
                                models.FieldCondition(
                                    key="tenant_id", match=models.MatchValue(value=tenant_id)
                                ),
                            ]
                        )
                    ),
                )
                result["qdrant_deleted"] = True
        except Exception as exc:
            result["errors"].append(f"qdrant: {type(exc).__name__}")
            logger.error("Legacy Qdrant purge failed (%s)", type(exc).__name__)

        try:
            driver = await asyncio.to_thread(self._get_neo4j)
            if driver:
                tenant_id = TenantContext.get() or "default"

                def _purge():
                    with driver.session() as session:
                        session.run(
                            """
                            MATCH (u:User {tenant_id: $tenant_id, id: $user_id})
                            OPTIONAL MATCH (u)-[:HAS_MEMORY]->(m:GlobalMemory {tenant_id: $tenant_id})
                            DETACH DELETE u, m
                            """,
                            user_id=user_id,
                            tenant_id=tenant_id,
                        )

                await asyncio.to_thread(_purge)
                result["neo4j_deleted"] = True
        except Exception as exc:
            result["errors"].append(f"neo4j: {type(exc).__name__}")
            logger.error("Legacy graph purge failed (%s)", type(exc).__name__)

        try:
            result["redis_cleared"] = await self.clear_ephemeral(user_id)
        except Exception as exc:
            result["errors"].append(f"redis: {type(exc).__name__}")
            logger.error("Legacy ephemeral-memory purge failed (%s)", type(exc).__name__)

        # This helper does not cover all memory stores and cannot attest a
        # complete erase, even if its narrower operations all succeed.
        logger.info("Legacy memory purge finished with subset_only=true")
        return result

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
                emb_dict = await asyncio.to_thread(
                    self._embedding_service.encode_single_full, query
                )
                embedding = emb_dict.get("dense")
            except Exception as _e:
                logger.debug("[memory service] suppressed non-critical error: %s", _e)

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
                memories = await self.search_semantic(
                    user_id, query, limit=limit, min_similarity=0.6
                )
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
            self._redis = None
        # The container-owned driver is shared and must be closed by the
        # container, not by this service. Only close private fallback drivers.
        if self._neo4j_driver and self._owns_neo4j_driver:
            close_result = self._neo4j_driver.close()
            if inspect.isawaitable(close_result):
                await close_result
            self._neo4j_driver = None
            self._owns_neo4j_driver = False

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
    # Cache entries are tenant-aware and user-aware, with a full-query digest.
    # Every return path uses the same bounded, defensive-copy helper.
    _KG_CACHE: dict[tuple, tuple[dict, float]] = {}
    _KG_TTL = 60.0
    _KG_CACHE_MAX = 256

    @classmethod
    def invalidate_personal_knowledge_graph_cache(
        cls,
        user_id: str | None = None,
        *,
        tenant_id: str | None = None,
        all_tenants: bool = False,
    ) -> int:
        """Evict cached private graph projections after a memory mutation.

        Cache keys are (tenant, user, view, limit, query digest). Never clear
        public ontology entries for a user-memory mutation. If the caller does
        not know the tenant, invalidate that user's private projections across
        tenants rather than risking stale personal content being replayed.
        """
        removed = 0
        for key in list(cls._KG_CACHE):
            if len(key) < 3 or key[2] != "personal":
                continue
            cached_tenant, cached_user = key[0], key[1]
            if user_id is not None and cached_user != user_id:
                continue
            if not all_tenants and tenant_id and cached_tenant != tenant_id:
                continue
            cls._KG_CACHE.pop(key, None)
            removed += 1
        return removed

    async def build_personal_knowledge_graph(
        self, user_id: Optional[str], view: str = "personal", limit: int = 50, query: str = ""
    ) -> dict[str, Any]:
        """Build a tenant-scoped personal knowledge graph.

        Persisted graph relationships remain distinct from lexical concept
        mentions inferred from record text. Private reads and cache entries are
        scoped to the authenticated user and current tenant.
        """
        normalized_view = (view or "personal").strip().lower()
        if normalized_view not in {"personal", "ontology"}:
            raise ValueError(f"Unsupported knowledge graph view: {normalized_view}")
        normalized_query = re.sub(r"\s+", " ", (query or "").strip().lower())
        tenant_id = (TenantContext.get() or "").strip()

        # Never reinterpret a direct anonymous personal-graph request as a
        # public ontology request. The HTTP API enforces auth too, but the
        # service boundary must stand independently of its callers.
        if normalized_view == "personal" and not user_id:
            return {"nodes": [], "edges": [], "query": normalized_query}
        if normalized_view == "personal" and not tenant_id:
            raise ValueError("Tenant context is required for a personal knowledge graph")

        cache_tenant = tenant_id if normalized_view == "personal" else "public"
        query_digest = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()
        cache_key = (
            cache_tenant,
            user_id or "",
            normalized_view,
            int(limit),
            query_digest,
        )

        def _cache_result(graph: dict[str, Any]) -> dict[str, Any]:
            snapshot = copy.deepcopy(graph)
            self._KG_CACHE[cache_key] = (snapshot, time.time() + self._KG_TTL)
            if len(self._KG_CACHE) > self._KG_CACHE_MAX:
                oldest = min(self._KG_CACHE, key=lambda key: self._KG_CACHE[key][1])
                self._KG_CACHE.pop(oldest, None)
            return copy.deepcopy(snapshot)

        cached = self._KG_CACHE.get(cache_key)
        if cached and cached[1] > time.time():
            return copy.deepcopy(cached[0])
        if cached:
            self._KG_CACHE.pop(cache_key, None)

        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        # O(1) edge dedup — replaces the O(n²) `edge not in edges` scan that
        # made large graphs quadratic during construction.
        edges_seen: set[tuple[str, str, Optional[str]]] = set()

        def _add_node(
            uid: str,
            label: str,
            ntype: str,
            teacher: str | None = None,
            state_category: str | None = None,
            content: str | None = None,
        ) -> None:
            if uid not in nodes:
                nodes[uid] = {
                    "id": uid,
                    "label": label,
                    "type": ntype,
                    "teacher": teacher,
                    "state_category": state_category,
                    "content": content,
                }

        def _add_edge(src: str, dst: str, label: str | None = None) -> None:
            key = (src, dst, label)
            if key in edges_seen or src == dst:
                return
            edges_seen.add(key)
            edges.append({"source": src, "target": dst, "label": label})

        # 1. Public Ontology View
        if normalized_view == "ontology":
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
                            edges_data = [
                                r.data() for r in res2 if r.get("source") and r.get("target")
                            ]
                            return ontology, edges_data

                    ontology, edges_data = await asyncio.to_thread(_query_ontology)
                    for c in ontology:
                        eid = c["eid"]
                        labels = c.get("labels", ["Concept"])
                        ntype = next(
                            (lbl for lbl in labels if lbl in ("Concept", "Teacher", "Practice")),
                            "Concept",
                        )
                        _add_node(f"concept:{eid}", eid, ntype, eid if ntype == "Teacher" else None)
                    for edge in edges_data:
                        _add_edge(
                            f"concept:{edge['source']}",
                            f"concept:{edge['target']}",
                            edge["rel_type"],
                        )
            except Exception as e:
                logger.warning(f"build_personal_knowledge_graph ontology view failed: {e}")
            result = {"nodes": list(nodes.values()), "edges": edges}
            enriched = copy.deepcopy(result)

            def _do_enrich():
                return kg_analytics.enrich_graph(enriched, enabled=settings.kg_analytics_enabled)

            try:
                await asyncio.wait_for(asyncio.to_thread(_do_enrich), timeout=30.0)
                result = enriched
            except (TimeoutError, Exception):
                logger.debug("KG enrichment timeout/error (non-critical)", exc_info=True)
            return _cache_result(result)

        # 2. Personal View
        # Check memories count from both Neo4j and Supabase
        neo4j_mems = []
        supabase_mems = []
        try:
            driver = await asyncio.to_thread(self._get_neo4j)
            if driver is not None:

                def _query_memories():
                    with driver.session() as session:
                        res = session.run(
                            "MATCH (u:User {id: $uid, tenant_id: $tenant_id})"
                            "-[:HAS_MEMORY]->(m:GlobalMemory {tenant_id: $tenant_id}) "
                            "WHERE m.is_superseded IS NULL OR NOT m.is_superseded = true "
                            "RETURN m.id AS id, m.content AS content, m.insight AS insight, "
                            "m.state_category AS state_category, m.created_at AS created_at",
                            uid=user_id,
                            tenant_id=tenant_id,
                        )
                        return [r.data() for r in res]

                neo4j_mems = await asyncio.to_thread(_query_memories)
        except Exception as e:
            logger.warning("Failed to query Neo4j memories (%s)", type(e).__name__)

        try:
            mems_res = await self.list_memories(user_id, page=1, page_size=50)
            supabase_mems = mems_res.get("memories", [])
        except Exception as e:
            logger.warning("Failed to query Supabase memories (%s)", type(e).__name__)

        # Fetch user's study notebooks and their items
        notebook_items = []
        try:
            notebooks_res = await asyncio.to_thread(
                # study_notebooks has no tenant axis (id/user_id/title/created_at
                # only), so a tenant_id filter made PostgREST reject the whole
                # query and the personal map silently lost every notebook item.
                self._supabase.table("study_notebooks").select("id").eq("user_id", user_id).execute
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
            logger.warning("Failed to query study notebook items for KG (%s)", type(e).__name__)

        # If absolutely no memories and no notebook items, return empty graph to trigger empty state in UI
        if not neo4j_mems and not supabase_mems and not notebook_items:
            empty = {"nodes": [], "edges": []}
            return _cache_result(empty)

        # User is authenticated. Build the personalized Consciousness Map!
        _add_node(f"user:{user_id}", "You", "User")

        # Track memories we've processed
        processed_memory_ids = set()

        # Add Neo4j memories
        for m in neo4j_mems:
            mid = m["id"]
            content = m.get("content", "")
            insight = m.get("insight") or content[:30]
            state_cat = str(m.get("state_category") or "").strip() or None
            processed_memory_ids.add(mid)

            _add_node(f"memory:{mid}", insight, "Memory", state_category=state_cat, content=content)
            _add_edge(f"user:{user_id}", f"memory:{mid}", "HAS_MEMORY")

            if state_cat:
                _add_node(f"state:{state_cat}", state_cat, "State", state_category=state_cat)
                _add_edge(f"memory:{mid}", f"state:{state_cat}", "IN_STATE")

        # Add Supabase memories if not already processed
        for m in supabase_mems:
            mid = str(m.get("id", ""))
            if not mid or mid in processed_memory_ids:
                continue
            content = m.get("content", "")
            claim = m.get("claim") or content[:30]

            # Extract state category if possible
            state_cat = str(m.get("state_category") or "").strip() or None
            _add_node(
                f"memory:{mid}",
                claim,
                "Memory",
                state_category=state_cat,
                content=content,
            )
            _add_edge(f"user:{user_id}", f"memory:{mid}", "HAS_MEMORY")
            if state_cat:
                _add_node(f"state:{state_cat}", state_cat, "State", state_category=state_cat)
                _add_edge(f"memory:{mid}", f"state:{state_cat}", "IN_STATE")

        # Now, query relationships between the memories and ontology concepts from Neo4j
        referenced_concept_ids = set()
        if neo4j_mems:
            try:

                def _query_memory_ontology_rels():
                    with driver.session() as session:
                        res = session.run(
                            "MATCH (m:GlobalMemory {tenant_id: $tenant_id})-[r:RELATES_TO]->(c) "
                            "WHERE m.id IN $mids AND (c:Concept OR c:Teacher OR c:Practice) "
                            "RETURN m.id AS mid, c.entity_id AS cid, labels(c)[0] AS clabel",
                            tenant_id=tenant_id,
                            mids=list(processed_memory_ids),
                        )
                        return [r.data() for r in res]

                rels = await asyncio.to_thread(_query_memory_ontology_rels)
                for r in rels:
                    mid = r["mid"]
                    cid = r["cid"]
                    # An ontology row without entity_id cannot be resolved to a
                    # node id; skipping it preserves every other relationship
                    # instead of letting _resolve_concept_meta raise and abort
                    # the whole batch.
                    if not cid:
                        logger.debug(
                            "Skipping memory ontology relationship with null entity_id (memory %s)",
                            mid,
                        )
                        continue
                    # The resolved type decides the node id; the relationship's own
                    # label is preserved for existing Concept rows.
                    ntype, teacher_name, state_cat_meta = _resolve_concept_meta(cid)
                    clabel = r["clabel"] or "Concept"
                    node_type = clabel if ntype == "Concept" else ntype
                    target = f"state:{cid}" if ntype == "State" else f"concept:{cid}"
                    _add_node(
                        target, cid, node_type, teacher=teacher_name, state_category=state_cat_meta
                    )
                    _add_edge(f"memory:{mid}", target, "RELATES_TO")
                    referenced_concept_ids.add(cid)
            except Exception as e:
                logger.warning("Failed to query memory ontology rels (%s)", type(e).__name__)

        # Fallback matching is deliberately phrase/token based; broad substring
        # matches created misleading concept edges in the previous implementation.
        concept_catalog: list[str] = []
        if driver is not None:
            try:

                def _get_all_concepts():
                    with driver.session() as session:
                        res = session.run(
                            "MATCH (c) WHERE c:Concept OR c:Teacher OR c:Practice "
                            "RETURN DISTINCT c.entity_id AS eid LIMIT 500"
                        )
                        return [str(r["eid"]) for r in res if r.get("eid")]

                concept_catalog = await asyncio.to_thread(_get_all_concepts)
            except Exception as _e:
                logger.debug("[memory service] concept fallback unavailable: %s", _e)

        if not concept_catalog:
            concept_catalog = list(_DEFAULT_CONCEPT_CATALOG)
        else:
            for item in _DEFAULT_CONCEPT_CATALOG:
                if item not in concept_catalog:
                    concept_catalog.append(item)

        def _matches_concept(text: str, concept: str) -> bool:
            source_tokens = set(re.findall(r"[a-z0-9][a-z0-9'-]{2,}", text.lower()))
            concept_tokens = set(re.findall(r"[a-z0-9][a-z0-9'-]{2,}", concept.lower()))
            if not source_tokens or not concept_tokens:
                return False
            normalized_concept = " ".join(concept.lower().split())
            if " " in normalized_concept:
                return concept_tokens.issubset(source_tokens)
            return len(normalized_concept) >= 4 and normalized_concept in source_tokens

        existing_concept_edges = {
            (e["source"], e["target"])
            for e in edges
            if e.get("source", "").startswith("memory:")
            and (
                e.get("target", "").startswith("concept:")
                or e.get("target", "").startswith("state:")
            )
        }

        for m in supabase_mems:
            mid = str(m.get("id", ""))
            if not mid:
                continue
            content = f"{m.get('content') or ''} {m.get('claim') or ''}"
            for cid in concept_catalog:
                if not _matches_concept(content, cid):
                    continue
                ntype, teacher_name, state_cat_meta = _resolve_concept_meta(cid)
                target = f"state:{cid}" if ntype == "State" else f"concept:{cid}"
                if (f"memory:{mid}", target) in existing_concept_edges:
                    continue
                _add_node(target, cid, "Concept")
                # Token/phrase overlap proves a mention, not a persisted
                # semantic relationship. Keep this inferential edge distinct.
                _add_edge(f"memory:{mid}", target, "MENTIONS_CONCEPT")
                existing_concept_edges.add((f"memory:{mid}", target))

        # 3. Add Study Notebook Items as Student Inquiries
        for item in notebook_items:
            nid = str(item.get("id", ""))
            if not nid:
                continue
            query = (item.get("query") or "").strip()
            answer = (item.get("answer") or "").strip()
            label = query[:36] + ("..." if len(query) > 36 else "")

            _add_node(
                f"notebook:{nid}",
                label,
                "NotebookItem",
                content=f"Inquiry: {query}\n\nTeacher's Guidance: {answer}"
                if answer
                else f"Inquiry: {query}",
            )
            _add_edge(f"user:{user_id}", f"notebook:{nid}", "SAVED_NOTE")

            # Match concepts in the inquiry or answer
            full_text = query + " " + answer
            for cid in concept_catalog:
                if not _matches_concept(full_text, cid):
                    continue
                _add_node(f"concept:{cid}", cid, "Concept")
                _add_edge(f"notebook:{nid}", f"concept:{cid}", "MENTIONS_CONCEPT")

        # Query and add relationships between the matched ontology concepts
        personal_ontology_ids = {
            n["label"]: n["id"]
            for n in nodes.values()
            if str(n.get("id", "")).startswith(("concept:", "state:"))
        }
        if personal_ontology_ids and driver is not None:
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
                            cids=list(personal_ontology_ids),
                        )
                        return [r.data() for r in res]

                concept_rels = await asyncio.to_thread(_query_concept_rels)
                for r in concept_rels:
                    source = personal_ontology_ids.get(str(r["source"]))
                    target = personal_ontology_ids.get(str(r["target"]))
                    if source and target:
                        _add_edge(source, target, r["rel_type"])
            except Exception as e:
                logger.warning("Failed to query concept rels (%s)", type(e).__name__)

        # Use only persisted memory↔memory relationships. The old implementation
        # created ring/cycle edges purely to make the graph look connected.
        if driver is not None and processed_memory_ids:
            try:

                def _query_memory_memory_rels():
                    with driver.session() as session:
                        res = session.run(
                            "MATCH (m1:GlobalMemory {tenant_id: $tenant_id})"
                            "-[r:RELATED_TO]-"
                            "(m2:GlobalMemory {tenant_id: $tenant_id}) "
                            "WHERE m1.id IN $mids AND m2.id IN $mids "
                            "RETURN DISTINCT m1.id AS source, m2.id AS target, type(r) AS rel_type "
                            "LIMIT 200",
                            tenant_id=tenant_id,
                            mids=list(processed_memory_ids),
                        )
                        return [r.data() for r in res]

                for r in await asyncio.to_thread(_query_memory_memory_rels):
                    source = str(r.get("source") or "")
                    target = str(r.get("target") or "")
                    if source and target:
                        _add_edge(
                            f"memory:{source}",
                            f"memory:{target}",
                            r.get("rel_type") or "RELATED_TO",
                        )
            except Exception as e:
                logger.warning(
                    "Failed to query memory-to-memory relationships (%s)", type(e).__name__
                )

        # Rank a query-focused subgraph from the real graph. An empty query
        # returns the most connected recent view; a query returns matches plus
        # their one-hop real neighbors.
        user_node_id = f"user:{user_id}"
        degree: dict[str, int] = {nid: 0 for nid in nodes}
        adjacency: dict[str, set[str]] = {nid: set() for nid in nodes}
        for edge in edges:
            if edge["source"] in adjacency and edge["target"] in adjacency:
                degree[edge["source"]] += 1
                degree[edge["target"]] += 1
                adjacency[edge["source"]].add(edge["target"])
                adjacency[edge["target"]].add(edge["source"])

        def _node_text(node: dict) -> str:
            return " ".join(
                [
                    str(node.get("label") or ""),
                    str(node.get("content") or "")[:500],
                    str(node.get("state_category") or ""),
                    str(node.get("type") or ""),
                ]
            ).lower()

        def _score(node: dict) -> float:
            if not normalized_query:
                return 0.0
            q_tokens = set(re.findall(r"[a-z0-9][a-z0-9'-]{2,}", normalized_query))
            n_tokens = set(re.findall(r"[a-z0-9][a-z0-9'-]{2,}", _node_text(node)))
            overlap = len(q_tokens & n_tokens)
            score = overlap * 5.0
            if normalized_query in _node_text(node):
                score += 10.0
            if normalized_query == str(node.get("label") or "").lower().strip():
                score += 20.0
            return score + min(degree.get(node["id"], 0), 8) * 0.2

        if normalized_query:
            scored = sorted(
                (
                    (_score(node), nid)
                    for nid, node in nodes.items()
                    if nid != user_node_id and _score(node) > 0
                ),
                key=lambda item: (-item[0], item[1]),
            )
            if not scored:
                result = {"nodes": [], "edges": [], "query": normalized_query}
            else:
                seeds = [nid for _, nid in scored[: min(10, max(4, limit // 3))]]
                selected = {user_node_id, *seeds}
                for seed in seeds:
                    selected.update(adjacency.get(seed, set()))
                ranked = sorted(
                    (
                        (
                            _score(nodes[nid])
                            + (4.0 if nid in selected else 0.0)
                            + degree.get(nid, 0) * 0.1,
                            nid,
                        )
                        for nid in selected
                        if nid != user_node_id
                    ),
                    key=lambda item: (-item[0], item[1]),
                )
                selected = {user_node_id, *(nid for _, nid in ranked[: max(1, limit - 1)])}
                result = {
                    "nodes": [node for nid, node in nodes.items() if nid in selected],
                    "edges": [
                        edge
                        for edge in edges
                        if edge["source"] in selected and edge["target"] in selected
                    ],
                    "query": normalized_query,
                }
        else:
            # Default personal view is deliberately balanced around the seeker's
            # own records. Concepts support the memories; they do not replace them.
            memory_ids = [
                nid
                for nid, node in nodes.items()
                if nid != user_node_id and node["type"] == "Memory"
            ]
            notebook_ids = [
                nid
                for nid, node in nodes.items()
                if nid != user_node_id and node["type"] == "NotebookItem"
            ]
            concept_ids = [
                nid
                for nid, node in nodes.items()
                if nid != user_node_id
                and node["type"] in {"Concept", "State", "Practice", "Teacher"}
            ]

            def _created_key(nid: str) -> str:
                return str(nodes[nid].get("created_at") or "")

            memory_ids.sort(
                key=lambda nid: (_created_key(nid), min(degree.get(nid, 0), 10)),
                reverse=True,
            )
            notebook_ids.sort(key=lambda nid: _created_key(nid), reverse=True)
            concept_ids.sort(
                key=lambda nid: (-degree.get(nid, 0), str(nodes[nid].get("label") or ""))
            )

            selected: set[str] = {user_node_id}
            remaining = max(1, limit - 1)

            # Show recent personal records first.
            for nid in memory_ids[: min(18, remaining)]:
                selected.add(nid)
            remaining = max(0, limit - len(selected))

            for nid in notebook_ids[: min(5, remaining)]:
                selected.add(nid)
            remaining = max(0, limit - len(selected))

            # Prefer concepts that are actually connected to the selected records.
            connected_concepts = [
                nid
                for nid in concept_ids
                if any(nid in adjacency.get(item_id, set()) for item_id in selected)
            ]
            for nid in connected_concepts[:remaining]:
                selected.add(nid)

            result = {
                "nodes": [node for nid, node in nodes.items() if nid in selected],
                "edges": [
                    edge
                    for edge in edges
                    if edge["source"] in selected and edge["target"] in selected
                ],
                "query": "",
            }

        enriched = copy.deepcopy(result)

        def _do_enrich():
            return kg_analytics.enrich_graph(enriched, enabled=settings.kg_analytics_enabled)

        try:
            await asyncio.wait_for(asyncio.to_thread(_do_enrich), timeout=30.0)
            result = enriched
        except (TimeoutError, Exception):
            logger.debug("KG enrichment timeout/error (non-critical)", exc_info=True)
        return _cache_result(result)

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
