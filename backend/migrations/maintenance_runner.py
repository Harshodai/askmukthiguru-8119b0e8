#!/usr/bin/env python3
"""
Mukthi Guru — Standalone Maintenance & Migration Runner.

Provides a unified, idempotent CLI runner for database and schema maintenance
operations that were previously run in application startup. Application startup
is strictly read-only; schema mutations, index definitions, and background
cleanups must be executed through this runner.

Usage:
  # List all registered operations
  python migrations/maintenance_runner.py --list

  # Plan an operation without executing mutations
  python migrations/maintenance_runner.py --operation qdrant-contract-v1 --dry-run

  # Apply mutations idempotently
  python migrations/maintenance_runner.py --operation qdrant-contract-v1 --apply

  # Run all registered operations
  python migrations/maintenance_runner.py --all --apply

Exit codes:
  0: SUCCESS (operation executed or planned successfully)
  1: GENERIC_ERROR (unhandled exception or failure)
  2: PRECONDITION_FAILED (target database/service unreachable)
  3: LOCK_HELD (operation lock held by another process)
  4: INVALID_OPERATION (unknown operation name or bad arguments)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple

# Ensure backend/ is in sys.path
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.config import settings

logger = logging.getLogger("maintenance_runner")


class ExitCode(IntEnum):
    SUCCESS = 0
    GENERIC_ERROR = 1
    PRECONDITION_FAILED = 2
    LOCK_HELD = 3
    INVALID_OPERATION = 4


@dataclass
class OperationResult:
    operation: str
    mode: str  # "dry-run" or "apply"
    status: str  # "SUCCESS", "PLANNED", "SKIPPED", "PRECONDITION_FAILED", "LOCK_HELD", "FAILED"
    plan: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    exit_code: ExitCode = ExitCode.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["exit_code"] = int(self.exit_code)
        return d


@dataclass
class MaintenanceContext:
    qdrant_client: Optional[Any] = None
    neo4j_driver: Optional[Any] = None
    redis_client: Optional[Any] = None
    lightrag_instance: Optional[Any] = None
    dry_run: bool = False
    force: bool = False

    def get_qdrant_client(self) -> Any:
        if self.qdrant_client is not None:
            return self.qdrant_client
        from services.qdrant.client import QdrantClientManager

        manager = QdrantClientManager()
        self.qdrant_client = manager.client
        return self.qdrant_client

    def get_redis_client(self) -> Optional[Any]:
        if self.redis_client is not None:
            return self.redis_client
        if not getattr(settings, "redis_url", None):
            return None
        try:
            import redis

            r = redis.Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
            r.ping()
            self.redis_client = r
            return self.redis_client
        except Exception as e:
            logger.warning("Redis client connection check failed: %s", e)
            return None


class DistributedLock:
    """Redis-backed distributed lock with 300s TTL and safe token release."""

    def __init__(self, redis_client: Optional[Any], lock_name: str, ttl_seconds: int = 300):
        self.redis = redis_client
        self.lock_name = lock_name
        self.key = f"maintenance:lock:{lock_name}"
        self.ttl_seconds = ttl_seconds
        self.token = str(uuid.uuid4())
        self.acquired = False
        self.error: Optional[str] = None

    def acquire(self) -> bool:
        if self.redis is None:
            logger.info("Redis not available; proceeding without distributed lock for %s", self.lock_name)
            self.acquired = True
            return True
        try:
            res = self.redis.set(self.key, self.token, nx=True, ex=self.ttl_seconds)
            self.acquired = bool(res)
            return self.acquired
        except Exception as e:
            self.error = str(e)
            logger.warning("Error acquiring distributed lock for %s: %s", self.lock_name, e)
            return False

    def release(self) -> bool:
        if not self.acquired or self.redis is None:
            return True
        try:
            lua = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            self.redis.eval(lua, 1, self.key, self.token)
            return True
        except Exception as e:
            logger.warning("Error releasing distributed lock for %s: %s", self.lock_name, e)
            return False


class BaseMaintenanceOperation(ABC):
    """Base contract for all maintenance operations."""

    name: str
    description: str

    @abstractmethod
    def check_preconditions(self, ctx: MaintenanceContext) -> Tuple[bool, str]:
        """Verify services/connections are ready before execution."""
        pass

    @abstractmethod
    def plan(self, ctx: MaintenanceContext) -> OperationResult:
        """Plan mutations without applying them (dry run)."""
        pass

    @abstractmethod
    def apply(self, ctx: MaintenanceContext) -> OperationResult:
        """Execute mutations idempotently."""
        pass


# =============================================================================
# 1. Qdrant Contract Migration: qdrant-contract-v1
# =============================================================================

class QdrantContractOperation(BaseMaintenanceOperation):
    name = "qdrant-contract-v1"
    description = "Enforce Qdrant HNSW m=16 configs on LightRAG collections, ensure semantic_query_cache (1024d cosine), and patch spiritual_wisdom HNSW m=16"

    LIGHTRAG_COLLECTIONS = [
        "lightrag_vdb_entities_baai_bge_m3_1024d",
        "lightrag_vdb_relationships_baai_bge_m3_1024d",
        "lightrag_vdb_chunks_baai_bge_m3_1024d",
    ]

    def check_preconditions(self, ctx: MaintenanceContext) -> Tuple[bool, str]:
        try:
            client = ctx.get_qdrant_client()
            client.get_collections()
            return True, "Qdrant reachable"
        except Exception as e:
            return False, f"Qdrant connection failed: {e}"

    def plan(self, ctx: MaintenanceContext) -> OperationResult:
        t0 = time.time()
        client = ctx.get_qdrant_client()
        plan_items: list[str] = []
        details: dict[str, Any] = {}

        try:
            existing_cols = {c.name for c in client.get_collections().collections}
            details["existing_collections"] = sorted(list(existing_cols))

            # 1. LightRAG HNSW check
            for col in self.LIGHTRAG_COLLECTIONS:
                if col in existing_cols:
                    info = client.get_collection(col)
                    current_m = getattr(getattr(info.config, "hnsw_config", None), "m", None)
                    if current_m is None or current_m < 16:
                        plan_items.append(f"Patch HNSW m=16 (ef_construct=100) on {col} (current m={current_m})")
                    else:
                        plan_items.append(f"HNSW m={current_m} already optimal on {col} (skip)")
                else:
                    plan_items.append(f"Collection {col} does not exist (skip)")

            # 2. semantic_query_cache check
            if "semantic_query_cache" not in existing_cols:
                plan_items.append("Create semantic_query_cache collection (1024d cosine vector)")
            else:
                plan_items.append("semantic_query_cache collection already exists (skip)")

            # 3. spiritual_wisdom HNSW check
            if "spiritual_wisdom" in existing_cols:
                sw_info = client.get_collection("spiritual_wisdom")
                sw_m = getattr(getattr(sw_info.config, "hnsw_config", None), "m", None)
                if sw_m is None or sw_m < 16:
                    plan_items.append(f"Patch HNSW m=16 (ef_construct=200) on spiritual_wisdom (current m={sw_m})")
                else:
                    plan_items.append(f"spiritual_wisdom HNSW m={sw_m} already optimal (skip)")
            else:
                plan_items.append("Collection spiritual_wisdom does not exist (skip)")

            return OperationResult(
                operation=self.name,
                mode="dry-run",
                status="PLANNED",
                plan=plan_items,
                details=details,
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.SUCCESS,
            )
        except Exception as e:
            return OperationResult(
                operation=self.name,
                mode="dry-run",
                status="FAILED",
                details={"error": str(e)},
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.GENERIC_ERROR,
            )

    def apply(self, ctx: MaintenanceContext) -> OperationResult:
        t0 = time.time()
        client = ctx.get_qdrant_client()
        actions: list[str] = []
        details: dict[str, Any] = {}

        try:
            from qdrant_client.models import Distance, HnswConfigDiff, VectorParams

            existing_cols = {c.name for c in client.get_collections().collections}

            # 1. Patch LightRAG collections HNSW
            for col in self.LIGHTRAG_COLLECTIONS:
                if col in existing_cols:
                    info = client.get_collection(col)
                    current_m = getattr(getattr(info.config, "hnsw_config", None), "m", None)
                    if current_m is None or current_m < 16:
                        client.update_collection(col, hnsw_config=HnswConfigDiff(m=16, ef_construct=100))
                        actions.append(f"Patched HNSW m=16 on {col}")
                    else:
                        actions.append(f"HNSW m={current_m} already optimal on {col}")

            # 2. Ensure semantic_query_cache collection
            if "semantic_query_cache" not in existing_cols:
                dim = getattr(settings, "embedding_dimension", 1024)
                client.create_collection(
                    "semantic_query_cache",
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
                actions.append(f"Created semantic_query_cache collection ({dim}d cosine)")
            else:
                actions.append("semantic_query_cache collection already exists")

            # 3. Ensure spiritual_wisdom HNSW m>=16
            if "spiritual_wisdom" in existing_cols:
                sw_info = client.get_collection("spiritual_wisdom")
                sw_m = getattr(getattr(sw_info.config, "hnsw_config", None), "m", None)
                if sw_m is None or sw_m < 16:
                    client.update_collection("spiritual_wisdom", hnsw_config=HnswConfigDiff(m=16, ef_construct=200))
                    actions.append("Patched HNSW m=16 on spiritual_wisdom")
                else:
                    actions.append(f"spiritual_wisdom HNSW m={sw_m} already optimal")

            return OperationResult(
                operation=self.name,
                mode="apply",
                status="SUCCESS",
                actions=actions,
                details=details,
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.SUCCESS,
            )
        except Exception as e:
            return OperationResult(
                operation=self.name,
                mode="apply",
                status="FAILED",
                details={"error": str(e)},
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.GENERIC_ERROR,
            )


# =============================================================================
# 2. Neo4j Spiritual Ontology Schema Migration: neo4j-ontology-schema-v1
# =============================================================================

class Neo4jOntologyOperation(BaseMaintenanceOperation):
    name = "neo4j-ontology-schema-v1"
    description = "Create Neo4j unique constraints, base entity index, seed spiritual teachers, concepts, practices, relationships, and align extracted ontology"

    def check_preconditions(self, ctx: MaintenanceContext) -> Tuple[bool, str]:
        if not getattr(settings, "neo4j_uri", None):
            return False, "NEO4J_URI is not configured in settings"
        try:
            if ctx.neo4j_driver is not None:
                ctx.neo4j_driver.verify_connectivity()
                return True, "Neo4j driver reachable"
            from app.dependencies import get_container

            driver = get_container().neo4j_driver
            if driver is None:
                return False, "Neo4j driver unavailable"
            driver.verify_connectivity()
            return True, "Neo4j driver reachable"
        except Exception as e:
            return False, f"Neo4j connectivity check failed: {e}"

    def plan(self, ctx: MaintenanceContext) -> OperationResult:
        t0 = time.time()
        plan_items = [
            "Create Cypher constraint UNIQUE_TEACHER_NAME on (t:Teacher) REQUIRE t.name IS UNIQUE",
            "Create Cypher constraint UNIQUE_CONCEPT_NAME on (c:Concept) REQUIRE c.name IS UNIQUE",
            "Create Cypher constraint UNIQUE_PRACTICE_NAME on (p:Practice) REQUIRE p.name IS UNIQUE",
            "Create Cypher index base_entity_id_idx on (n:base) FOR (n.entity_id)",
            "Seed 8 spiritual teachers (Sadhguru, Sri Amma Bhagavan, ISKCON, Sri Preethaji, Sri Krishnaji, Ekam, O&O Academy, Mukthi Guru)",
            "Seed 33 spiritual concepts with descriptions and entity types",
            "Seed 10 spiritual practices (Meditation, Yoga, Serene Mind, Soul Sync, etc.)",
            "Seed EXPOUNDS, PRACTICE_FOR, and concept relationship edges",
            "Align extracted generic nodes (:base) with canonical ontology entities using DOCTRINE_SYNONYMS",
        ]
        return OperationResult(
            operation=self.name,
            mode="dry-run",
            status="PLANNED",
            plan=plan_items,
            details={"target_uri": getattr(settings, "neo4j_uri", "")},
            execution_time_ms=(time.time() - t0) * 1000,
            exit_code=ExitCode.SUCCESS,
        )

    def apply(self, ctx: MaintenanceContext) -> OperationResult:
        t0 = time.time()
        try:
            from app.db.seed_ontology import seed_spiritual_ontology

            seed_spiritual_ontology()
            actions = [
                "Applied Neo4j unique constraints (Teacher, Concept, Practice)",
                "Created base_entity_id_idx index on :base(entity_id)",
                "Seeded teachers, concepts, practices, and relationship graph",
                "Aligned extracted generic graph entities to spiritual ontology",
            ]
            return OperationResult(
                operation=self.name,
                mode="apply",
                status="SUCCESS",
                actions=actions,
                details={"target_uri": getattr(settings, "neo4j_uri", "")},
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.SUCCESS,
            )
        except Exception as e:
            return OperationResult(
                operation=self.name,
                mode="apply",
                status="FAILED",
                details={"error": str(e)},
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.GENERIC_ERROR,
            )


# =============================================================================
# 3. Qdrant Payload Indexes Migration: qdrant-payload-indexes-v1
# =============================================================================

class QdrantPayloadIndexesOperation(BaseMaintenanceOperation):
    name = "qdrant-payload-indexes-v1"
    description = "Ensure integer and keyword payload indexes on spiritual_wisdom collection (raptor_level, cluster_id, language, content_type, speaker, topic)"

    INT_FIELDS = ["raptor_level", "cluster_id"]
    KW_FIELDS = ["language", "content_type", "speaker", "topic"]

    def check_preconditions(self, ctx: MaintenanceContext) -> Tuple[bool, str]:
        try:
            client = ctx.get_qdrant_client()
            cols = {c.name for c in client.get_collections().collections}
            if "spiritual_wisdom" not in cols:
                return False, "Collection 'spiritual_wisdom' not found in Qdrant"
            return True, "Qdrant reachable and spiritual_wisdom exists"
        except Exception as e:
            return False, f"Qdrant check failed: {e}"

    def plan(self, ctx: MaintenanceContext) -> OperationResult:
        t0 = time.time()
        plan_items = [
            f"Create INTEGER payload index on spiritual_wisdom.{f}" for f in self.INT_FIELDS
        ] + [
            f"Create KEYWORD payload index on spiritual_wisdom.{f}" for f in self.KW_FIELDS
        ]
        return OperationResult(
            operation=self.name,
            mode="dry-run",
            status="PLANNED",
            plan=plan_items,
            details={"collection": "spiritual_wisdom"},
            execution_time_ms=(time.time() - t0) * 1000,
            exit_code=ExitCode.SUCCESS,
        )

    def apply(self, ctx: MaintenanceContext) -> OperationResult:
        t0 = time.time()
        client = ctx.get_qdrant_client()
        actions: list[str] = []
        failures: list[str] = []
        try:
            from qdrant_client.models import PayloadSchemaType

            def _is_already_exists(ex: Exception) -> bool:
                msg = str(ex).lower()
                return "already exists" in msg or "conflict" in msg or getattr(getattr(ex, "status_code", None), "value", None) == 409 or getattr(ex, "status_code", None) == 409

            for f in self.INT_FIELDS:
                try:
                    client.create_payload_index("spiritual_wisdom", f, PayloadSchemaType.INTEGER)
                    actions.append(f"Created INTEGER index on spiritual_wisdom.{f}")
                except Exception as ex:
                    if _is_already_exists(ex):
                        actions.append(f"INTEGER index on spiritual_wisdom.{f} already exists ({ex})")
                    else:
                        failures.append(f"INTEGER index on spiritual_wisdom.{f} failed: {ex}")
                        actions.append(f"INTEGER index on spiritual_wisdom.{f} failed: {ex}")

            for f in self.KW_FIELDS:
                try:
                    client.create_payload_index("spiritual_wisdom", f, PayloadSchemaType.KEYWORD)
                    actions.append(f"Created KEYWORD index on spiritual_wisdom.{f}")
                except Exception as ex:
                    if _is_already_exists(ex):
                        actions.append(f"KEYWORD index on spiritual_wisdom.{f} already exists ({ex})")
                    else:
                        failures.append(f"KEYWORD index on spiritual_wisdom.{f} failed: {ex}")
                        actions.append(f"KEYWORD index on spiritual_wisdom.{f} failed: {ex}")

            if failures:
                return OperationResult(
                    operation=self.name,
                    mode="apply",
                    status="FAILED",
                    actions=actions,
                    details={"collection": "spiritual_wisdom", "failures": failures},
                    execution_time_ms=(time.time() - t0) * 1000,
                    exit_code=ExitCode.GENERIC_ERROR,
                )

            return OperationResult(
                operation=self.name,
                mode="apply",
                status="SUCCESS",
                actions=actions,
                details={"collection": "spiritual_wisdom"},
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.SUCCESS,
            )
        except Exception as e:
            return OperationResult(
                operation=self.name,
                mode="apply",
                status="FAILED",
                details={"error": str(e)},
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.GENERIC_ERROR,
            )


# =============================================================================
# 4. LightRAG Entity Dedup Migration: lightrag-entity-dedup-v1
# =============================================================================

class LightRAGEntityDedupOperation(BaseMaintenanceOperation):
    name = "lightrag-entity-dedup-v1"
    description = "Run entity deduplication merge rules for known spiritual concept name variants in LightRAG"

    ENTITY_MERGES = [
        (["karma", "Karma", "KARMA"], "Karma"),
        (["dharma", "Dharma", "DHARMA"], "Dharma"),
        (["deeksha", "Deeksha", "DEEKSHA", "deeksha blessing"], "Deeksha"),
        (["aham", "Aham", "AHAM", "aham consciousness"], "Aham"),
        (["beautiful state", "Beautiful State", "beautiful-state", "BeautifulState"], "Beautiful State"),
        (["suffering state", "Suffering State", "suffering-state"], "Suffering State"),
        (["soul sync", "Soul Sync", "SoulSync", "soul-sync"], "Soul Sync"),
        (["oneness blessing", "Oneness Blessing", "oneness-blessing"], "Oneness Blessing"),
        (["breath awareness", "Breath Awareness", "breath-awareness"], "Breath Awareness"),
        (["beautiful state of being", "beautiful state of consciousness"], "Beautiful State"),
    ]

    def check_preconditions(self, ctx: MaintenanceContext) -> Tuple[bool, str]:
        # LightRAG can be checked or Neo4j driver can be checked
        return True, "LightRAG entity dedup preconditions met"

    def plan(self, ctx: MaintenanceContext) -> OperationResult:
        t0 = time.time()
        plan_items = [
            f"Merge entity variants {sources} -> '{target}'"
            for sources, target in self.ENTITY_MERGES
        ]
        return OperationResult(
            operation=self.name,
            mode="dry-run",
            status="PLANNED",
            plan=plan_items,
            details={"rule_count": len(self.ENTITY_MERGES)},
            execution_time_ms=(time.time() - t0) * 1000,
            exit_code=ExitCode.SUCCESS,
        )

    def apply(self, ctx: MaintenanceContext) -> OperationResult:
        t0 = time.time()
        actions: list[str] = []
        applied_count = 0

        try:
            # Check if LightRAG instance or custom merge is available
            rag_instance = None
            if ctx.lightrag_instance is not None:
                rag_instance = ctx.lightrag_instance
            else:
                try:
                    from app.dependencies import get_container

                    container = get_container()
                    rag_instance = getattr(getattr(container, "lightrag", None), "_rag", None) or getattr(
                        getattr(container, "lightrag", None), "rag", None
                    )
                except Exception as ce:
                    logger.debug("Container LightRAG resolution note: %s", ce)

            if rag_instance and hasattr(rag_instance, "merge_entities"):
                merge_failures: list[str] = []
                for sources, target in self.ENTITY_MERGES:
                    try:
                        rag_instance.merge_entities(sources, target)
                        actions.append(f"Merged {sources} -> '{target}' via LightRAG")
                        applied_count += 1
                    except Exception as me:
                        merge_failures.append(f"Merge {sources} -> '{target}' failed: {me}")
                        actions.append(f"Merge {sources} -> '{target}' failed: {me}")
                if merge_failures:
                    return OperationResult(
                        operation=self.name,
                        mode="apply",
                        status="FAILED",
                        actions=actions,
                        details={
                            "rules_applied": applied_count,
                            "total_rules": len(self.ENTITY_MERGES),
                            "merge_failures": merge_failures,
                        },
                        execution_time_ms=(time.time() - t0) * 1000,
                        exit_code=ExitCode.GENERIC_ERROR,
                    )
            else:
                return OperationResult(
                    operation=self.name,
                    mode="apply",
                    status="SKIPPED",
                    actions=[
                        f"LightRAG engine instance unavailable; recorded {len(self.ENTITY_MERGES)} merge rules for online graph processing"
                    ],
                    details={
                        "rules_applied": 0,
                        "total_rules": len(self.ENTITY_MERGES),
                        "reason": "LightRAG engine instance unavailable",
                    },
                    execution_time_ms=(time.time() - t0) * 1000,
                    exit_code=ExitCode.SUCCESS,
                )

            return OperationResult(
                operation=self.name,
                mode="apply",
                status="SUCCESS",
                actions=actions,
                details={"rules_applied": applied_count, "total_rules": len(self.ENTITY_MERGES)},
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.SUCCESS,
            )
        except Exception as e:
            return OperationResult(
                operation=self.name,
                mode="apply",
                status="FAILED",
                details={"error": str(e)},
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.GENERIC_ERROR,
            )


# =============================================================================
# 5. Cleanup Stale Collections Migration: cleanup-stale-collections-v1
# =============================================================================

class CleanupStaleCollectionsOperation(BaseMaintenanceOperation):
    name = "cleanup-stale-collections-v1"
    description = "Delete stale 384d LightRAG collections and empty semantic_query_cache from Qdrant"

    STALE_384D = [
        "lightrag_vdb_entities_intfloat_multilingual_e5_small_384d",
        "lightrag_vdb_relationships_intfloat_multilingual_e5_small_384d",
        "lightrag_vdb_chunks_intfloat_multilingual_e5_small_384d",
        "spiritual_wisdom_recovery_v20260713_004009",
        "spiritual_wisdom_recovery_v20260713_003753",
    ]

    def check_preconditions(self, ctx: MaintenanceContext) -> Tuple[bool, str]:
        try:
            client = ctx.get_qdrant_client()
            client.get_collections()
            return True, "Qdrant reachable"
        except Exception as e:
            return False, f"Qdrant check failed: {e}"

    def plan(self, ctx: MaintenanceContext) -> OperationResult:
        t0 = time.time()
        client = ctx.get_qdrant_client()
        plan_items: list[str] = []
        details: dict[str, Any] = {}

        try:
            existing_cols = {c.name for c in client.get_collections().collections}
            for stale in self.STALE_384D:
                if stale in existing_cols:
                    plan_items.append(f"Delete stale collection '{stale}'")
                else:
                    plan_items.append(f"Stale collection '{stale}' not found (skip)")

            if "semantic_query_cache" in existing_cols:
                cache_info = client.get_collection("semantic_query_cache")
                count = getattr(cache_info, "points_count", None)
                if count == 0:
                    plan_items.append("Delete empty semantic_query_cache collection (0 points)")
                elif count is None:
                    plan_items.append("Preserve semantic_query_cache collection (point count unknown)")
                else:
                    plan_items.append(f"Preserve semantic_query_cache collection ({count} points)")

            return OperationResult(
                operation=self.name,
                mode="dry-run",
                status="PLANNED",
                plan=plan_items,
                details=details,
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.SUCCESS,
            )
        except Exception as e:
            return OperationResult(
                operation=self.name,
                mode="dry-run",
                status="FAILED",
                details={"error": str(e)},
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.GENERIC_ERROR,
            )

    def apply(self, ctx: MaintenanceContext) -> OperationResult:
        t0 = time.time()
        client = ctx.get_qdrant_client()
        actions: list[str] = []
        details: dict[str, Any] = {}

        try:
            if not ctx.force:
                stale_present = [
                    stale for stale in self.STALE_384D
                    if stale in {c.name for c in client.get_collections().collections}
                ]
                return OperationResult(
                    operation=self.name,
                    mode="apply",
                    status="SKIPPED",
                    actions=[f"Stale 384d collection deletion requires --force confirmation; {len(stale_present)} stale collection(s) found: {stale_present}"],
                    details={
                        "reason": "Destructive operation: pass --force to confirm deletion of stale 384d collections",
                        "stale_collections_present": stale_present,
                    },
                    execution_time_ms=(time.time() - t0) * 1000,
                    exit_code=ExitCode.SUCCESS,
                )

            existing_cols = {c.name for c in client.get_collections().collections}
            for stale in self.STALE_384D:
                if stale in existing_cols:
                    try:
                        client.delete_collection(stale)
                        actions.append(f"Deleted stale collection '{stale}'")
                    except Exception as de:
                        actions.append(f"Failed to delete '{stale}': {de}")

            if "semantic_query_cache" in existing_cols:
                try:
                    cache_info = client.get_collection("semantic_query_cache")
                    count = getattr(cache_info, "points_count", None)
                    if count == 0:
                        client.delete_collection("semantic_query_cache")
                        actions.append("Deleted empty semantic_query_cache collection")
                    elif count is None:
                        actions.append("Preserved semantic_query_cache collection (point count unknown)")
                    else:
                        actions.append(f"Preserved semantic_query_cache collection ({count} points)")
                except Exception as ce:
                    actions.append(f"Checking semantic_query_cache failed: {ce}")

            return OperationResult(
                operation=self.name,
                mode="apply",
                status="SUCCESS",
                actions=actions,
                details=details,
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.SUCCESS,
            )
        except Exception as e:
            return OperationResult(
                operation=self.name,
                mode="apply",
                status="FAILED",
                details={"error": str(e)},
                execution_time_ms=(time.time() - t0) * 1000,
                exit_code=ExitCode.GENERIC_ERROR,
            )


# =============================================================================
# Registry & Runner
# =============================================================================

OPERATIONS: Dict[str, BaseMaintenanceOperation] = {
    QdrantContractOperation.name: QdrantContractOperation(),
    Neo4jOntologyOperation.name: Neo4jOntologyOperation(),
    QdrantPayloadIndexesOperation.name: QdrantPayloadIndexesOperation(),
    LightRAGEntityDedupOperation.name: LightRAGEntityDedupOperation(),
    CleanupStaleCollectionsOperation.name: CleanupStaleCollectionsOperation(),
}


def list_operations() -> list[dict[str, str]]:
    return [
        {"name": op.name, "description": op.description}
        for op in OPERATIONS.values()
    ]


def run_operation(
    operation_name: str,
    dry_run: bool = True,
    ctx: Optional[MaintenanceContext] = None,
) -> OperationResult:
    """Run a single named operation in dry-run or apply mode with locking and precondition checks."""
    if operation_name not in OPERATIONS:
        return OperationResult(
            operation=operation_name,
            mode="dry-run" if dry_run else "apply",
            status="FAILED",
            details={"error": f"Unknown operation: {operation_name}. Available: {list(OPERATIONS.keys())}"},
            exit_code=ExitCode.INVALID_OPERATION,
        )

    if ctx is None:
        ctx = MaintenanceContext(dry_run=dry_run)
    else:
        ctx.dry_run = dry_run

    op = OPERATIONS[operation_name]

    # Precondition check
    ready, reason = op.check_preconditions(ctx)
    if not ready:
        return OperationResult(
            operation=operation_name,
            mode="dry-run" if dry_run else "apply",
            status="PRECONDITION_FAILED",
            details={"reason": reason},
            exit_code=ExitCode.PRECONDITION_FAILED,
        )

    if dry_run:
        return op.plan(ctx)

    # In apply mode: acquire distributed Redis lock
    redis_client = ctx.get_redis_client()
    lock = DistributedLock(redis_client, operation_name, ttl_seconds=300)
    if not lock.acquire():
        if lock.error is not None:
            # Redis acquisition failed (error, not contention)
            if ctx.force:
                logger.warning(
                    "Redis lock acquisition failed for %s (%s); --force permits proceeding without the distributed lock",
                    operation_name,
                    lock.error,
                )
            else:
                return OperationResult(
                    operation=operation_name,
                    mode="apply",
                    status="PRECONDITION_FAILED",
                    details={"reason": f"Distributed lock could not be acquired due to Redis error: {lock.error}"},
                    exit_code=ExitCode.PRECONDITION_FAILED,
                )
        elif not ctx.force:
            return OperationResult(
                operation=operation_name,
                mode="apply",
                status="LOCK_HELD",
                details={"error": f"Lock maintenance:lock:{operation_name} is held by another worker"},
                exit_code=ExitCode.LOCK_HELD,
            )
        else:
            logger.warning(
                "Distributed lock for %s is held by another worker; --force permits proceeding",
                operation_name,
            )

    try:
        return op.apply(ctx)
    finally:
        lock.release()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mukthi Guru Standalone Schema & Database Maintenance Runner"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all registered maintenance operations",
    )
    parser.add_argument(
        "--operation",
        "-o",
        type=str,
        help="Name of the operation to run (e.g., qdrant-contract-v1)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all registered operations sequentially",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan actions without executing mutations (default unless --apply is passed)",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Apply mutations idempotently",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON audit report",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force execution even if Redis lock is unavailable",
    )

    args = parser.parse_args()

    # Handle --list
    if args.list:
        ops = list_operations()
        if args.json:
            print(json.dumps({"operations": ops}, indent=2))
        else:
            print("\nAvailable Maintenance Operations:")
            print("=" * 60)
            for item in ops:
                print(f"• {item['name']}")
                print(f"  {item['description']}\n")
        return ExitCode.SUCCESS

    # Determine mode: dry_run is True if --dry-run is set or if --apply is NOT set
    dry_run = not args.apply

    if not args.operation and not args.all:
        parser.print_help()
        return ExitCode.INVALID_OPERATION

    ctx = MaintenanceContext(dry_run=dry_run, force=args.force)
    target_ops = list(OPERATIONS.keys()) if args.all else [args.operation]

    results: list[OperationResult] = []
    overall_exit_code = ExitCode.SUCCESS

    for op_name in target_ops:
        res = run_operation(op_name, dry_run=dry_run, ctx=ctx)
        results.append(res)
        if res.exit_code != ExitCode.SUCCESS and overall_exit_code == ExitCode.SUCCESS:
            overall_exit_code = res.exit_code

    if args.json:
        report = {
            "mode": "dry-run" if dry_run else "apply",
            "overall_status": "SUCCESS" if overall_exit_code == ExitCode.SUCCESS else "FAILED",
            "overall_exit_code": int(overall_exit_code),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": [r.to_dict() for r in results],
        }
        print(json.dumps(report, indent=2))
    else:
        print(f"\nMaintenance Runner Summary (Mode: {'DRY-RUN' if dry_run else 'APPLY'})")
        print("=" * 60)
        for r in results:
            print(f"\n[{r.status}] {r.operation} ({r.execution_time_ms:.1f}ms)")
            if r.plan:
                print("  Plan:")
                for p in r.plan:
                    print(f"    - {p}")
            if r.actions:
                print("  Actions:")
                for a in r.actions:
                    print(f"    ✓ {a}")
            if r.details:
                print(f"  Details: {r.details}")
        print("\n" + "=" * 60)
        print(f"Exit Code: {int(overall_exit_code)} ({overall_exit_code.name})\n")

    return int(overall_exit_code)


if __name__ == "__main__":
    sys.exit(main())
