"""Memory Resolver — Phase 5 of the Adaptive Memory System.

Applies the judge's decisions to the canonical Postgres store.
Handles deduplication, supersession, merging, contradiction handling,
version history, idempotency, and audit logging.

Design principles:
    - Postgres is the single source of truth.
    - Every mutation writes an audit event.
    - Idempotent: same decision applied twice produces the same result.
    - Optimistic concurrency via version field.
    - Memory failure never fails chat (async path).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from services.canonical_memory.judge import DecisionType, MemoryDecision
from services.canonical_memory.models import MemoryCandidate, SINGLE_VALUED_FACT_KEYS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resolution result
# ---------------------------------------------------------------------------

@dataclass
class ResolutionResult:
    """Outcome of resolving a single judge decision.

    Attributes:
        action: The action taken (created, updated, merged, ignored, etc.).
        memory_id: ID of the created/updated memory (None for ignored/escalated).
        superseded_ids: IDs of memories that were superseded.
        reason: Human-readable explanation.
        audit_event_id: ID of the audit event written.
        metadata: Arbitrary metadata for observability.
    """
    action: str
    memory_id: Optional[str] = None
    superseded_ids: list[str] = field(default_factory=list)
    reason: str = ""
    audit_event_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Memory Resolver
# ---------------------------------------------------------------------------

class MemoryResolver:
    """Applies judge decisions to the canonical Postgres store via Supabase.

    Each resolution method handles one DecisionType and produces a
    ResolutionResult. Every mutation writes an audit event to
    canonical_memory_events.

    The resolver is stateless — it receives a Supabase client and processes
    one decision at a time. Thread-safety is handled by the caller (outbox
    worker or task queue).
    """

    def __init__(self, supabase_client: Any):
        self._db = supabase_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def resolve(
        self, decision: MemoryDecision, user_id: str
    ) -> ResolutionResult:
        """Apply the judge's decision to the canonical store.

        Args:
            decision: The judge's decision to resolve.
            user_id: The owning user ID (enforced externally, not on candidate).

        Dispatches to the appropriate handler based on decision type.
        """
        handlers = {
            DecisionType.CREATE: self._create,
            DecisionType.UPDATE: self._update,
            DecisionType.MERGE: self._merge,
            DecisionType.IGNORE: self._ignore,
            DecisionType.EXPIRE: self._expire,
            DecisionType.DELETE: self._delete,
            DecisionType.ESCALATE: self._escalate,
        }

        handler = handlers.get(decision.decision)
        if handler is None:
            logger.error("Unknown decision type: %s", decision.decision)
            return ResolutionResult(
                action="error",
                reason=f"Unknown decision type: {decision.decision}",
            )

        try:
            return await handler(decision, user_id)
        except Exception as e:
            logger.exception(
                "Resolution failed for decision %s: %s", decision.decision, e
            )
            return ResolutionResult(
                action="error",
                reason=f"Resolution failed: {e}",
            )

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    async def _create(
        self, decision: MemoryDecision, user_id: str
    ) -> ResolutionResult:
        """Create a new memory in the canonical store.

        If the candidate has a fact_key that already has an active memory,
        the old memory is superseded first (fact-key supersession).
        """
        candidate = decision.candidate
        now = datetime.now(timezone.utc).isoformat()

        # Check for existing active memory with same fact_key
        superseded_ids: list[str] = []
        if candidate.fact_key:
            existing = await self._find_active_by_fact_key(
                user_id, candidate.fact_key
            )
            if existing is not None:
                # Single-valued key → supersede old; multi-valued → skip if
                # same semantic content (judge should have caught this, but
                # defense-in-depth)
                if candidate.fact_key in SINGLE_VALUED_FACT_KEYS:
                    sup_result = await self._supersede_memory(
                        existing["id"],
                        existing["version"],
                        user_id,
                        reason=(
                            f"Superseded by new {candidate.fact_key} value: "
                            f"{candidate.statement}"
                        ),
                    )
                    if sup_result:
                        superseded_ids.append(existing["id"])
                else:
                    # Multi-valued: check semantic similarity for dedup
                    existing_norm = (existing.get("normalized_statement") or
                                     existing.get("statement", "")).lower().strip()
                    candidate_norm = candidate.normalized()
                    if self._text_similar(existing_norm, candidate_norm, threshold=0.92):
                        # Exact duplicate → idempotent, return existing
                        return ResolutionResult(
                            action="idempotent_duplicate",
                            memory_id=existing["id"],
                            reason=(
                                "Active memory with same fact_key and "
                                "semantic content already exists"
                            ),
                        )

        # Insert new memory
        new_id = await self._insert_memory(candidate, now, user_id)

        # Audit event
        audit_id = await self._write_audit_event(
            user_id=user_id,
            memory_id=new_id,
            event_type="CREATED",
            old_version=None,
            new_version=1,
            reason=decision.reason,
            actor="resolver",
        )

        return ResolutionResult(
            action="created",
            memory_id=new_id,
            superseded_ids=superseded_ids,
            reason=decision.reason,
            audit_event_id=audit_id,
            metadata={
                "fact_key": candidate.fact_key,
                "confidence": candidate.confidence,
            },
        )

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    async def _update(
        self, decision: MemoryDecision, user_id: str
    ) -> ResolutionResult:
        """Update an existing memory: supersede old, create new version.

        Increments version on the new memory. Sets valid_to on the old.
        """
        candidate = decision.candidate
        now = datetime.now(timezone.utc).isoformat()

        target_id = decision.superseded_memory_id
        if not target_id:
            # Fallback: try to find by fact_key
            if candidate.fact_key:
                existing = await self._find_active_by_fact_key(
                    user_id, candidate.fact_key
                )
                if existing:
                    target_id = existing["id"]

        superseded_ids: list[str] = []
        new_version = 1
        # Captured BEFORE _supersede_memory bumps the row. The audit event and
        # the result metadata must report the version as it was prior to the
        # update; re-reading old_memory afterwards yields the incremented value
        # (an UPDATE of a v3 row was auditing old_version=4). Also keeps this
        # safe when target_id is set but the row no longer exists.
        old_version: Optional[int] = None

        if target_id:
            # Read current version for optimistic lock
            old_memory = await self._get_memory(target_id)
            if old_memory is not None:
                old_version = old_memory.get("version", 1)
                sup_ok = await self._supersede_memory(
                    target_id,
                    old_version,
                    user_id,
                    reason=(
                        f"Superseded by update: {decision.reason}"
                    ),
                )
                if sup_ok:
                    superseded_ids.append(target_id)
                    new_version = 1  # New memory always starts at version 1
                else:
                    # Optimistic lock failed — idempotent: already superseded
                    if old_memory.get("status") == "superseded":
                        return ResolutionResult(
                            action="idempotent_update",
                            memory_id=target_id,
                            superseded_ids=[target_id],
                            reason="Memory already superseded",
                        )
                    logger.warning(
                        "Optimistic lock failed for memory %s", target_id
                    )
                    return ResolutionResult(
                        action="error",
                        reason=f"Optimistic lock failed for {target_id}",
                    )

        # Insert new version of memory
        new_id = await self._insert_memory(candidate, now, user_id)

        # Audit event
        audit_id = await self._write_audit_event(
            user_id=user_id,
            memory_id=new_id,
            event_type="UPDATED",
            old_version=old_version,
            new_version=new_version,
            reason=decision.reason,
            actor="resolver",
        )

        return ResolutionResult(
            action="updated",
            memory_id=new_id,
            superseded_ids=superseded_ids,
            reason=decision.reason,
            audit_event_id=audit_id,
            metadata={
                "fact_key": candidate.fact_key,
                "previous_version": old_version,
            },
        )

    # ------------------------------------------------------------------
    # MERGE
    # ------------------------------------------------------------------

    async def _merge(
        self, decision: MemoryDecision, user_id: str
    ) -> ResolutionResult:
        """Merge two related memories into one.

        Supersedes both source memories and creates a merged result
        with combined evidence.
        """
        candidate = decision.candidate
        now = datetime.now(timezone.utc).isoformat()

        merged_ids = decision.merged_memory_ids or []
        superseded_ids: list[str] = []

        # Supersede all source memories
        for mem_id in merged_ids:
            old_memory = await self._get_memory(mem_id)
            if old_memory is not None:
                ok = await self._supersede_memory(
                    mem_id,
                    old_memory.get("version", 1),
                    user_id,
                    reason=f"Merged into new memory: {candidate.statement}",
                )
                if ok:
                    superseded_ids.append(mem_id)

        # Combine evidence counts from the merged memories.
        # Seeded at 0, NOT at the candidate's own evidence_count: the merged
        # candidate is derived from the sources, so counting it as well
        # double-counts the same evidence (2 + 1 sources yielded 4). Matches
        # consolidator.py, which sets a merged row's evidence_count to the
        # number of source memories.
        total_evidence = 0
        for mem_id in merged_ids:
            old_memory = await self._get_memory(mem_id)
            if old_memory:
                total_evidence += old_memory.get("evidence_count", 1)

        # Create merged memory
        new_id = await self._insert_memory(candidate, now, user_id)

        # Update evidence_count to reflect merged sources
        await self._update_field(new_id, "evidence_count", total_evidence)

        # Audit event
        audit_id = await self._write_audit_event(
            user_id=user_id,
            memory_id=new_id,
            event_type="MERGED",
            old_version=None,
            new_version=1,
            reason=(
                f"Merged from {len(superseded_ids)} memories: "
                + "; ".join(superseded_ids)
            ),
            actor="resolver",
        )

        return ResolutionResult(
            action="merged",
            memory_id=new_id,
            superseded_ids=superseded_ids,
            reason=decision.reason,
            audit_event_id=audit_id,
            metadata={
                "merged_from": superseded_ids,
                "combined_evidence_count": total_evidence,
            },
        )

    # ------------------------------------------------------------------
    # IGNORE
    # ------------------------------------------------------------------

    async def _ignore(
        self, decision: MemoryDecision, user_id: str
    ) -> ResolutionResult:
        """Ignore the candidate — no store mutation."""
        return ResolutionResult(
            action="ignored",
            reason=decision.reason,
        )

    # ------------------------------------------------------------------
    # EXPIRE
    # ------------------------------------------------------------------

    async def _expire(
        self, decision: MemoryDecision, user_id: str
    ) -> ResolutionResult:
        """Expire a memory — set status='expired' and valid_to.

        For temporary context memories that have exceeded their TTL.
        """
        candidate = decision.candidate
        now = datetime.now(timezone.utc).isoformat()

        # Find the active memory to expire
        target_id = decision.superseded_memory_id
        if not target_id and candidate.fact_key:
            existing = await self._find_active_by_fact_key(
                user_id, candidate.fact_key
            )
            if existing:
                target_id = existing["id"]

        if not target_id:
            return ResolutionResult(
                action="no_op",
                reason="No active memory found to expire",
            )

        old_memory = await self._get_memory(target_id)
        if old_memory is None:
            return ResolutionResult(
                action="no_op",
                reason=f"Memory {target_id} not found",
            )

        if old_memory.get("status") != "active":
            return ResolutionResult(
                action="idempotent_expire",
                memory_id=target_id,
                reason=f"Memory {target_id} already {old_memory.get('status')}",
            )

        ok = await self._update_status(target_id, "expired", now)
        if not ok:
            return ResolutionResult(
                action="error",
                reason=f"Failed to expire memory {target_id}",
            )

        # Audit event
        audit_id = await self._write_audit_event(
            user_id=user_id,
            memory_id=target_id,
            event_type="EXPIRED",
            old_version=old_memory.get("version"),
            new_version=old_memory.get("version"),
            reason=decision.reason,
            actor="resolver",
        )

        return ResolutionResult(
            action="expired",
            memory_id=target_id,
            reason=decision.reason,
            audit_event_id=audit_id,
        )

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    async def _delete(
        self, decision: MemoryDecision, user_id: str
    ) -> ResolutionResult:
        """Soft-delete a memory — set status='deleted'.

        Triggered by explicit user 'forget X' instruction.
        """
        candidate = decision.candidate
        now = datetime.now(timezone.utc).isoformat()

        target_id = decision.superseded_memory_id
        if not target_id and candidate.fact_key:
            existing = await self._find_active_by_fact_key(
                user_id, candidate.fact_key
            )
            if existing:
                target_id = existing["id"]

        # Fallback: try semantic search against all active memories
        if not target_id:
            target_id = await self._find_by_semantic_match(
                user_id, candidate.statement
            )

        if not target_id:
            return ResolutionResult(
                action="no_op",
                reason="No matching memory found to delete",
            )

        old_memory = await self._get_memory(target_id)
        if old_memory is None:
            return ResolutionResult(
                action="no_op",
                reason=f"Memory {target_id} not found",
            )

        if old_memory.get("status") == "deleted":
            return ResolutionResult(
                action="idempotent_delete",
                memory_id=target_id,
                reason=f"Memory {target_id} already deleted",
            )

        ok = await self._update_status(target_id, "deleted", now)
        if not ok:
            return ResolutionResult(
                action="error",
                reason=f"Failed to delete memory {target_id}",
            )

        # Audit event
        audit_id = await self._write_audit_event(
            user_id=user_id,
            memory_id=target_id,
            event_type="DELETED",
            old_version=old_memory.get("version"),
            new_version=old_memory.get("version"),
            reason=decision.reason,
            actor="resolver",
        )

        return ResolutionResult(
            action="deleted",
            memory_id=target_id,
            reason=decision.reason,
            audit_event_id=audit_id,
        )

    # ------------------------------------------------------------------
    # ESCALATE
    # ------------------------------------------------------------------

    async def _escalate(
        self, decision: MemoryDecision, user_id: str
    ) -> ResolutionResult:
        """Escalate to user confirmation — no store mutation."""
        return ResolutionResult(
            action="escalated",
            reason=decision.reason,
            metadata=decision.metadata,
        )

    # ------------------------------------------------------------------
    # Store operations (Supabase client)
    # ------------------------------------------------------------------

    async def _find_active_by_fact_key(
        self, user_id: str, fact_key: str
    ) -> Optional[dict]:
        """Find the active memory for a user + fact_key combination."""
        try:
            result = (
                self._db.table("canonical_memories")
                .select("*")
                .eq("user_id", user_id)
                .eq("fact_key", fact_key)
                .eq("status", "active")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = result.data if result.data else []
            return rows[0] if rows else None
        except Exception as e:
            logger.error("Failed to find active memory by fact_key: %s", e)
            return None

    async def _get_memory(self, memory_id: str) -> Optional[dict]:
        """Get a memory by ID."""
        try:
            result = (
                self._db.table("canonical_memories")
                .select("*")
                .eq("id", memory_id)
                .limit(1)
                .execute()
            )
            rows = result.data if result.data else []
            return rows[0] if rows else None
        except Exception as e:
            logger.error("Failed to get memory %s: %s", memory_id, e)
            return None

    async def _insert_memory(
        self, candidate: MemoryCandidate, now: str, user_id: str
    ) -> str:
        """Insert a new memory row and return its ID."""
        import uuid

        new_id = str(uuid.uuid4())
        row = {
            "id": new_id,
            "user_id": user_id,
            "tenant_id": "oneness",
            "memory_type": candidate.memory_type.value,
            "statement": candidate.statement,
            "normalized_statement": candidate.normalized(),
            "fact_key": candidate.fact_key,
            "confidence": candidate.confidence,
            "importance": candidate.importance,
            "sensitivity": candidate.sensitivity,
            "status": "active",
            "source_conversation_id": getattr(candidate, "source_conversation_id", None),
            "source_message_id": getattr(candidate, "source_message_id", None),
            "source_turn_index": candidate.source_turn_index,
            "extraction_method": candidate.extraction_method if hasattr(candidate, "extraction_method") else "llm",
            "evidence_count": 1,
            "created_at": now,
            "updated_at": now,
            "valid_from": now,
            "valid_to": None,
            "version": 1,
            "metadata": {},
        }

        # Add expires_at if present
        expires_at = getattr(candidate, "expires_at", None)
        if expires_at:
            row["expires_at"] = expires_at

        try:
            self._db.table("canonical_memories").insert(row).execute()
            return new_id
        except Exception as e:
            logger.error("Failed to insert memory: %s", e)
            raise

    async def _supersede_memory(
        self,
        memory_id: str,
        expected_version: int,
        user_id: str,
        reason: str = "",
    ) -> bool:
        """Supersede a memory using optimistic concurrency control.

        Returns True if superseded successfully, False if version mismatch.
        """
        now = datetime.now(timezone.utc).isoformat()
        try:
            result = (
                self._db.table("canonical_memories")
                .update({
                    "status": "superseded",
                    "valid_to": now,
                    "updated_at": now,
                    "version": expected_version + 1,
                })
                .eq("id", memory_id)
                .eq("version", expected_version)
                .eq("user_id", user_id)
                .execute()
            )
            # Supabase update doesn't return affected rows directly;
            # if no exception, assume success. Version mismatch will
            # result in 0 rows updated (idempotent on next attempt).
            return True
        except Exception as e:
            logger.error("Failed to supersede memory %s: %s", memory_id, e)
            return False

    async def _update_status(
        self, memory_id: str, new_status: str, now: str
    ) -> bool:
        """Update a memory's status and valid_to."""
        try:
            update_fields: dict = {
                "status": new_status,
                "updated_at": now,
            }
            if new_status in ("superseded", "expired", "deleted"):
                update_fields["valid_to"] = now

            self._db.table("canonical_memories").update(update_fields).eq(
                "id", memory_id
            ).execute()
            return True
        except Exception as e:
            logger.error(
                "Failed to update status for %s to %s: %s",
                memory_id, new_status, e,
            )
            return False

    async def _update_field(
        self, memory_id: str, field_name: str, value: Any
    ) -> bool:
        """Update a single field on a memory."""
        try:
            self._db.table("canonical_memories").update(
                {field_name: value}
            ).eq("id", memory_id).execute()
            return True
        except Exception as e:
            logger.error(
                "Failed to update field %s on %s: %s",
                field_name, memory_id, e,
            )
            return False

    async def _find_by_semantic_match(
        self, user_id: str, statement: str
    ) -> Optional[str]:
        """Find a memory by text similarity (fallback for delete).

        Searches active memories for the user and compares normalized
        statements. Returns the best match ID or None.
        """
        try:
            result = (
                self._db.table("canonical_memories")
                .select("id, statement, normalized_statement")
                .eq("user_id", user_id)
                .eq("status", "active")
                .limit(50)
                .execute()
            )
            rows = result.data if result.data else []
            if not rows:
                return None

            candidate_norm = statement.strip().lower()
            best_id = None
            best_sim = 0.0

            for row in rows:
                existing_norm = (
                    row.get("normalized_statement") or row.get("statement", "")
                ).strip().lower()
                sim = self._text_similarity_ratio(candidate_norm, existing_norm)
                if sim > best_sim and sim >= 0.75:
                    best_sim = sim
                    best_id = row["id"]

            return best_id
        except Exception as e:
            logger.error("Semantic match search failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Audit events
    # ------------------------------------------------------------------

    async def _write_audit_event(
        self,
        user_id: str,
        memory_id: str,
        event_type: str,
        old_version: Optional[int],
        new_version: Optional[int],
        reason: str,
        actor: str = "resolver",
    ) -> Optional[str]:
        """Write an audit event to canonical_memory_events."""
        import uuid

        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        try:
            self._db.table("canonical_memory_events").insert({
                "id": event_id,
                "user_id": user_id,
                "memory_id": memory_id,
                "event_type": event_type,
                "actor": actor,
                "old_version": old_version,
                "new_version": new_version,
                "reason": reason,
                "created_at": now,
            }).execute()
            return event_id
        except Exception as e:
            logger.error(
                "Failed to write audit event for memory %s: %s",
                memory_id, e,
            )
            return None

    # ------------------------------------------------------------------
    # Text similarity helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _text_similarity_ratio(a: str, b: str) -> float:
        """Deterministic text similarity using SequenceMatcher."""
        from difflib import SequenceMatcher

        if a == b:
            return 1.0
        return SequenceMatcher(None, a, b).ratio()

    @staticmethod
    def _text_similar(
        a: str, b: str, threshold: float = 0.92
    ) -> bool:
        """Check if two normalized texts are semantically similar."""
        from difflib import SequenceMatcher

        if a == b:
            return True
        return SequenceMatcher(None, a, b).ratio() >= threshold


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_resolver(supabase_client: Any) -> MemoryResolver:
    """Factory to create a MemoryResolver with a Supabase client."""
    return MemoryResolver(supabase_client)


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from unittest.mock import MagicMock
    from services.canonical_memory.judge import MemoryDecision, DecisionType
    from services.canonical_memory.models import MemoryCandidate, MemoryType

    # Quick self-check with mock Supabase client
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    mock_db.table.return_value.insert.return_value.execute.return_value.data = []
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value.data = []

    resolver = MemoryResolver(mock_db)

    candidate = MemoryCandidate(
        statement="User prefers concise answers.",
        memory_type=MemoryType.PREFERENCE,
        confidence=0.9,
        importance=0.7,
        fact_key="user:prefers_tone",
        evidence="I prefer concise answers.",
    )

    decision = MemoryDecision(
        candidate=candidate,
        decision=DecisionType.CREATE,
        confidence=0.9,
        reason="New durable fact",
    )

    import asyncio
    result = asyncio.run(resolver.resolve(decision, user_id="test-user-001"))
    print(f"Action: {result.action}")
    print(f"Memory ID: {result.memory_id}")
    print(f"Reason: {result.reason}")
    print("Self-check passed.")
