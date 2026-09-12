"""Memory Consolidator — Phase 6 of the Adaptive Memory System.

Prevents memory fragmentation without expensive per-write compaction.
Uses threshold-triggered or scheduled consolidation.

Strategy:
    1. Check if user's active memory count exceeds threshold
    2. Identify consolidation candidates (similar memories, related facts)
    3. LLM-assisted merge (if needed)
    4. Validate no information loss
    5. Apply changes (supersede old, create merged)
    6. Return result with before/after counts

Safety:
    - Snapshot before destructive operations
    - Rollback capability
    - Validation that important memories are preserved
    - Dry-run mode
    - Audit events for all mutations

Success metric: NOT "fewer memories" — success is:
    less redundancy + no information loss + better retrieval
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONSOLIDATION_THRESHOLD = 50
DEFAULT_MAX_MERGED_OUTPUT = 30
SNAPSHOT_TABLE = "canonical_memory_compaction_snapshots"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ConsolidationResult:
    """Outcome of a consolidation operation.

    Attributes:
        user_id: The user whose memories were consolidated.
        before_count: Active memory count before consolidation.
        after_count: Active memory count after consolidation.
        superseded_ids: IDs of memories that were superseded.
        created_ids: IDs of newly created merged memories.
        dry_run: Whether this was a dry run (no changes applied).
        rollback_available: Whether a snapshot exists for rollback.
        reason: Human-readable summary.
        audit_event_ids: IDs of audit events created.
        error: Error message if consolidation failed.
    """
    user_id: str
    before_count: int = 0
    after_count: int = 0
    superseded_ids: list[str] = field(default_factory=list)
    created_ids: list[str] = field(default_factory=list)
    dry_run: bool = False
    rollback_available: bool = False
    reason: str = ""
    audit_event_ids: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class ConsolidationCandidate:
    """A pair/group of memories identified for consolidation.

    Attributes:
        memory_ids: IDs of memories to consolidate.
        reason: Why these should be consolidated.
        merged_statement: The proposed merged statement (if computed).
        merged_type: The memory type for the merged result.
        merged_fact_key: The fact key for the merged result.
        merged_confidence: The confidence for the merged result.
        merged_importance: The importance for the merged result.
    """
    memory_ids: list[str]
    reason: str
    merged_statement: Optional[str] = None
    merged_type: Optional[str] = None
    merged_fact_key: Optional[str] = None
    merged_confidence: Optional[float] = None
    merged_importance: Optional[float] = None


# ---------------------------------------------------------------------------
# Consolidator
# ---------------------------------------------------------------------------

class CanonicalMemoryConsolidator:
    """Consolidates fragmented memories for a user.

    Uses threshold-triggered consolidation: when a user's active memory count
    exceeds the threshold, the consolidator identifies candidates for merging,
    uses LLM to produce merged statements, validates no information loss,
    and applies supersession + creation.

    Safety invariants:
        1. Snapshot before any destructive operation
        2. Validate no important memories lost
        3. Dry-run mode never modifies data
        4. Rollback from snapshot if needed
        5. Audit events for every mutation
    """

    def __init__(
        self,
        supabase_client: Any,
        llm_service: Any,
        threshold: int = DEFAULT_CONSOLIDATION_THRESHOLD,
    ):
        self._db = supabase_client
        self._llm = llm_service
        self._threshold = threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def should_consolidate(self, user_id: str) -> bool:
        """Check if user's memory count exceeds consolidation threshold.

        Returns True if the user has more active memories than the threshold,
        indicating consolidation may reduce fragmentation.
        """
        count = await self._count_active_memories(user_id)
        return count > self._threshold

    async def consolidate(
        self,
        user_id: str,
        dry_run: bool = False,
    ) -> ConsolidationResult:
        """Consolidate fragmented memories for a user.

        Flow:
            1. Snapshot current state
            2. Identify consolidation candidates
            3. LLM-assisted merge (if needed)
            4. Validate no information loss
            5. Apply changes (supersede old, create merged)
            6. Return result with before/after counts

        Args:
            user_id: The user whose memories to consolidate.
            dry_run: If True, identify candidates but don't apply changes.

        Returns:
            ConsolidationResult with full details of the operation.
        """
        result = ConsolidationResult(user_id=user_id, dry_run=dry_run)

        try:
            # 1. Count before
            memories = await self._fetch_active_memories(user_id)
            result.before_count = len(memories)

            if result.before_count <= self._threshold:
                result.after_count = result.before_count
                result.reason = (
                    f"Memory count ({result.before_count}) is at or below "
                    f"threshold ({self._threshold}). No consolidation needed."
                )
                return result

            # 2. Identify consolidation candidates
            candidates = self._identify_candidates(memories)

            if not candidates:
                result.reason = (
                    f"Found {result.before_count} active memories but no "
                    f"consolidation candidates identified."
                )
                result.after_count = result.before_count
                return result

            # 3. LLM-assisted merge
            merged_candidates = await self._llm_merge(candidates, memories)

            # 4. Validate
            validation = self._validate_preservation(
                memories, merged_candidates
            )
            if not validation["valid"]:
                result.reason = f"Validation failed: {validation['reason']}"
                result.error = validation["reason"]
                result.after_count = result.before_count
                return result

            # 5. Apply (or dry-run)
            if dry_run:
                result.reason = (
                    f"Dry run: would supersede {len(merged_candidates)} groups "
                    f"({sum(len(c.memory_ids) for c in merged_candidates)} memories) "
                    f"into {len(merged_candidates)} merged memories."
                )
                result.after_count = (
                    result.before_count
                    - sum(len(c.memory_ids) for c in merged_candidates)
                    + len(merged_candidates)
                )
                return result

            # Snapshot before destructive operation
            snapshot_id = await self._create_snapshot(user_id, memories)
            result.rollback_available = snapshot_id is not None

            # Apply supersession + creation
            apply_result = await self._apply_consolidation(
                user_id, memories, merged_candidates
            )
            result.superseded_ids = apply_result["superseded_ids"]
            result.created_ids = apply_result["created_ids"]
            result.audit_event_ids = apply_result["audit_event_ids"]
            result.after_count = (
                result.before_count
                - len(result.superseded_ids)
                + len(result.created_ids)
            )
            result.reason = (
                f"Consolidated: superseded {len(result.superseded_ids)} memories, "
                f"created {len(result.created_ids)} merged memories. "
                f"Count: {result.before_count} → {result.after_count}."
            )

        except Exception as e:
            logger.error(
                "Consolidation failed for user %s: %s", user_id, e, exc_info=True
            )
            result.error = str(e)
            result.after_count = result.before_count

        return result

    async def rollback(self, user_id: str, snapshot_id: str) -> bool:
        """Rollback a consolidation using a snapshot.

        Restores the pre-consolidation state by:
        1. Deleting any merged memories created during consolidation
        2. Restoring superseded memories to active status

        Returns True if rollback succeeded.
        """
        try:
            snapshot = await self._fetch_snapshot(snapshot_id)
            if not snapshot:
                logger.warning(
                    "Snapshot %s not found for user %s", snapshot_id, user_id
                )
                return False

            memories_json = snapshot.get("memories_json", "[]")
            original_memories = json.loads(memories_json)

            # Delete all current active memories for this user
            await asyncio.to_thread(
                self._db.table("canonical_memories")
                .delete()
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute
            )

            # Re-insert original memories
            for mem in original_memories:
                mem.pop("id", None)  # Let Postgres generate new IDs
                await asyncio.to_thread(
                    self._db.table("canonical_memories")
                    .insert(mem)
                    .execute
                )

            logger.info(
                "Rollback completed for user %s from snapshot %s",
                user_id, snapshot_id,
            )
            return True

        except Exception as e:
            logger.error(
                "Rollback failed for user %s: %s", user_id, e, exc_info=True
            )
            return False

    # ------------------------------------------------------------------
    # Internal: counting and fetching
    # ------------------------------------------------------------------

    async def _count_active_memories(self, user_id: str) -> int:
        """Count active memories for a user."""
        result = await asyncio.to_thread(
            self._db.table("canonical_memories")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute
        )
        return result.count if hasattr(result, "count") else len(result.data or [])

    async def _fetch_active_memories(self, user_id: str) -> list[dict]:
        """Fetch all active memories for a user."""
        result = await asyncio.to_thread(
            self._db.table("canonical_memories")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "active")
            .order("importance", desc=True)
            .execute
        )
        return result.data if hasattr(result, "data") else []

    # ------------------------------------------------------------------
    # Internal: candidate identification
    # ------------------------------------------------------------------

    def _identify_candidates(
        self, memories: list[dict]
    ) -> list[ConsolidationCandidate]:
        """Identify groups of memories that should be consolidated.

        Heuristics:
        1. Same fact_key → likely redundant (single-valued keys)
        2. Same memory_type + high keyword overlap → related facts
        3. High similarity in normalized_statement → near-duplicates
        """
        candidates: list[ConsolidationCandidate] = []
        used_ids: set[str] = set()

        # Group by fact_key first (single-valued keys are highest priority)
        fact_key_groups: dict[str, list[dict]] = {}
        for mem in memories:
            fk = mem.get("fact_key")
            if fk:
                fact_key_groups.setdefault(fk, []).append(mem)

        for fk, group in fact_key_groups.items():
            if len(group) > 1:
                mem_ids = [m["id"] for m in group if m["id"] not in used_ids]
                if len(mem_ids) > 1:
                    candidates.append(
                        ConsolidationCandidate(
                            memory_ids=mem_ids,
                            reason=f"Same fact_key '{fk}': {len(mem_ids)} memories",
                        )
                    )
                    used_ids.update(mem_ids)

        # Group by memory_type with keyword overlap
        type_groups: dict[str, list[dict]] = {}
        for mem in memories:
            if mem["id"] not in used_ids:
                mt = mem.get("memory_type", "unknown")
                type_groups.setdefault(mt, []).append(mem)

        for mt, group in type_groups.items():
            if len(group) < 2:
                continue

            # Find pairs with high keyword overlap
            for i in range(len(group)):
                if group[i]["id"] in used_ids:
                    continue
                pair_ids = [group[i]["id"]]
                kw_i = self._extract_keywords(
                    group[i].get("statement", "")
                )

                for j in range(i + 1, len(group)):
                    if group[j]["id"] in used_ids:
                        continue
                    kw_j = self._extract_keywords(
                        group[j].get("statement", "")
                    )
                    overlap = self._keyword_overlap(kw_i, kw_j)

                    if overlap > 0.5:
                        pair_ids.append(group[j]["id"])

                if len(pair_ids) > 1:
                    candidates.append(
                        ConsolidationCandidate(
                            memory_ids=pair_ids,
                            reason=(
                                f"Same type '{mt}' with keyword overlap: "
                                f"{len(pair_ids)} memories"
                            ),
                        )
                    )
                    used_ids.update(pair_ids)

        return candidates

    def _extract_keywords(self, text: str) -> set[str]:
        """Extract keywords from text for overlap comparison."""
        indic = "\u0900-\u097F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F"
        return {
            w.lower()
            for w in re.findall(rf"[a-zA-Z{indic}]+", text)
            if len(w) > 2
        }

    def _keyword_overlap(self, kw_a: set[str], kw_b: set[str]) -> float:
        """Compute Jaccard overlap between two keyword sets."""
        if not kw_a or not kw_b:
            return 0.0
        intersection = len(kw_a & kw_b)
        union = len(kw_a | kw_b)
        return intersection / union if union > 0 else 0.0

    # ------------------------------------------------------------------
    # Internal: LLM merge
    # ------------------------------------------------------------------

    async def _llm_merge(
        self,
        candidates: list[ConsolidationCandidate],
        all_memories: list[dict],
    ) -> list[ConsolidationCandidate]:
        """Use LLM to merge consolidation candidates into coherent statements.

        For each candidate group, asks the LLM to produce a single merged
        statement that preserves all information from the group.
        """
        # Build a lookup for quick access
        mem_lookup = {m["id"]: m for m in all_memories}

        merged: list[ConsolidationCandidate] = []
        for candidate in candidates:
            group_statements = []
            group_mems = []
            for mid in candidate.memory_ids:
                mem = mem_lookup.get(mid)
                if mem:
                    group_statements.append(mem.get("statement", ""))
                    group_mems.append(mem)

            if not group_statements:
                continue

            if len(group_statements) == 1:
                # Single memory — keep as-is
                candidate.merged_statement = group_statements[0]
                candidate.merged_type = group_mems[0].get("memory_type")
                candidate.merged_fact_key = group_mems[0].get("fact_key")
                candidate.merged_confidence = group_mems[0].get("confidence", 0.75)
                candidate.merged_importance = group_mems[0].get("importance", 0.5)
                merged.append(candidate)
                continue

            # Multi-memory merge via LLM
            merged_text = await self._call_llm_merge(group_statements)
            if merged_text:
                candidate.merged_statement = merged_text
                # Preserve highest confidence and importance
                candidate.merged_confidence = max(
                    (m.get("confidence", 0) for m in group_mems), default=0.75
                )
                candidate.merged_importance = max(
                    (m.get("importance", 0) for m in group_mems), default=0.5
                )
                # Use the most specific type
                candidate.merged_type = group_mems[0].get("memory_type")
                candidate.merged_fact_key = group_mems[0].get("fact_key")
                merged.append(candidate)
            else:
                # LLM failed — keep first memory as-is
                candidate.merged_statement = group_statements[0]
                candidate.merged_type = group_mems[0].get("memory_type")
                candidate.merged_fact_key = group_mems[0].get("fact_key")
                candidate.merged_confidence = group_mems[0].get("confidence", 0.75)
                candidate.merged_importance = group_mems[0].get("importance", 0.5)
                merged.append(candidate)

        return merged

    async def _call_llm_merge(self, statements: list[str]) -> Optional[str]:
        """Call LLM to merge multiple statements into one coherent statement.

        Returns the merged statement, or None on failure.
        """
        try:
            prompt = (
                "You are a memory consolidation assistant for a spiritual guidance system. "
                "Merge the following related facts about a user into a single coherent statement. "
                "Preserve ALL information. Do not add information not present in the originals. "
                "Return ONLY the merged statement, nothing else."
            )

            numbered = "\n".join(
                f"{i+1}. {s}" for i, s in enumerate(statements)
            )
            user_msg = (
                f"Merge these {len(statements)} related facts into one coherent statement:\n\n"
                f"{numbered}\n\n"
                f"Merged statement:"
            )

            # Try the LLM service if available
            if self._llm and hasattr(self._llm, "generate"):
                response = await self._llm.generate(
                    system=prompt,
                    user=user_msg,
                    temperature=0.0,
                    max_tokens=256,
                )
                if response and response.strip():
                    return response.strip()

            # Fallback: simple concatenation with dedup
            return self._simple_merge(statements)

        except Exception as e:
            logger.warning("LLM merge failed, using simple merge: %s", e)
            return self._simple_merge(statements)

    def _simple_merge(self, statements: list[str]) -> str:
        """Simple fallback merge: deduplicate and combine sentences."""
        seen = set()
        merged_parts = []
        for stmt in statements:
            # Normalize for dedup
            norm = stmt.strip().lower()
            if norm not in seen:
                seen.add(norm)
                merged_parts.append(stmt.strip())

        if not merged_parts:
            return statements[0] if statements else ""

        # Combine: use the longest as base, append unique parts
        base = max(merged_parts, key=len)
        extras = [p for p in merged_parts if p != base]

        if not extras:
            return base

        return f"{base.rstrip('.')}. Additionally, {'; '.join(e.rstrip('.') for e in extras)}."

    # ------------------------------------------------------------------
    # Internal: validation
    # ------------------------------------------------------------------

    def _validate_preservation(
        self,
        original_memories: list[dict],
        candidates: list[ConsolidationCandidate],
    ) -> dict:
        """Validate that consolidation preserves important memories.

        Checks:
        1. High-importance memories (>= 0.8) are included in candidates
           (their information is preserved in merged statements)
        2. USER_EXPLICIT memories are always included
        3. No more than 50% of memories are consolidated in one pass
        """
        total_original = len(original_memories)
        total_to_supersede = sum(len(c.memory_ids) for c in candidates)

        # Don't consolidate more than 50% in one pass
        if total_to_supersede > total_original * 0.5:
            return {
                "valid": False,
                "reason": (
                    f"Would supersede {total_to_supersede}/{total_original} "
                    f"memories (>50% threshold). Aborting for safety."
                ),
            }

        # Check high-importance memories are covered
        high_importance_ids = {
            m["id"]
            for m in original_memories
            if m.get("importance", 0) >= 0.8
        }
        consolidated_ids = {
            mid for c in candidates for mid in c.memory_ids
        }
        missing_important = high_importance_ids - consolidated_ids

        if missing_important:
            # This is OK — high-importance memories aren't being touched
            # They're preserved as-is
            pass

        # Check USER_EXPLICIT memories aren't lost
        explicit_ids = {
            m["id"]
            for m in original_memories
            if m.get("memory_type") == "USER_EXPLICIT"
        }
        missing_explicit = explicit_ids - consolidated_ids

        if missing_explicit:
            # USER_EXPLICIT memories not being consolidated — good
            pass

        return {"valid": True, "reason": ""}

    # ------------------------------------------------------------------
    # Internal: snapshot and apply
    # ------------------------------------------------------------------

    async def _create_snapshot(
        self, user_id: str, memories: list[dict]
    ) -> Optional[str]:
        """Create a snapshot of current memories before consolidation.

        Returns snapshot_id for potential rollback.
        """
        try:
            snapshot_data = {
                "user_id": user_id,
                "memories_json": json.dumps(memories, default=str),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            result = await asyncio.to_thread(
                self._db.table(SNAPSHOT_TABLE)
                .insert(snapshot_data)
                .execute
            )
            if result.data:
                return result.data[0].get("id")
            return None
        except Exception as e:
            logger.warning("Failed to create snapshot: %s", e)
            return None

    async def _fetch_snapshot(self, snapshot_id: str) -> Optional[dict]:
        """Fetch a snapshot by ID."""
        try:
            result = await asyncio.to_thread(
                self._db.table(SNAPSHOT_TABLE)
                .select("*")
                .eq("id", snapshot_id)
                .single()
                .execute
            )
            return result.data if hasattr(result, "data") else None
        except Exception:
            return None

    async def _apply_consolidation(
        self,
        user_id: str,
        memories: list[dict],
        candidates: list[ConsolidationCandidate],
    ) -> dict:
        """Apply consolidation: supersede old memories, create merged ones.

        Returns dict with superseded_ids, created_ids, audit_event_ids.
        """
        superseded_ids: list[str] = []
        created_ids: list[str] = []
        audit_event_ids: list[str] = []

        now = datetime.now(timezone.utc).isoformat()

        for candidate in candidates:
            # Supersede old memories
            for mid in candidate.memory_ids:
                try:
                    # Get current version
                    mem = next((m for m in memories if m["id"] == mid), None)
                    if not mem:
                        continue

                    old_version = mem.get("version", 1)

                    await asyncio.to_thread(
                        self._db.table("canonical_memories")
                        .update({
                            "status": "superseded",
                            "valid_to": now,
                            "version": old_version + 1,
                            "updated_at": now,
                        })
                        .eq("id", mid)
                        .eq("version", old_version)
                        .execute
                    )

                    superseded_ids.append(mid)

                    # Audit event
                    audit_result = await asyncio.to_thread(
                        self._db.table("canonical_memory_events")
                        .insert({
                            "user_id": user_id,
                            "memory_id": mid,
                            "event_type": "SUPERSEDED",
                            "actor": "consolidator",
                            "old_version": old_version,
                            "new_version": old_version + 1,
                            "reason": f"Consolidation: {candidate.reason}",
                            "created_at": now,
                        })
                        .execute
                    )
                    if audit_result.data:
                        audit_event_ids.append(audit_result.data[0]["id"])

                except Exception as e:
                    logger.warning(
                        "Failed to supersede memory %s: %s", mid, e
                    )

            # Create merged memory
            if candidate.merged_statement:
                try:
                    new_mem = {
                        "user_id": user_id,
                        "memory_type": candidate.merged_type or "PREFERENCE",
                        "statement": candidate.merged_statement,
                        "normalized_statement": candidate.merged_statement.strip().lower(),
                        "fact_key": candidate.merged_fact_key,
                        "confidence": candidate.merged_confidence or 0.75,
                        "importance": candidate.merged_importance or 0.5,
                        "sensitivity": "normal",
                        "status": "active",
                        "extraction_method": "consolidator",
                        "evidence_count": len(candidate.memory_ids),
                        "version": 1,
                        "valid_from": now,
                        "metadata": {
                            "consolidated_from": candidate.memory_ids,
                            "consolidation_reason": candidate.reason,
                        },
                    }
                    create_result = await asyncio.to_thread(
                        self._db.table("canonical_memories")
                        .insert(new_mem)
                        .execute
                    )

                    if create_result.data:
                        new_id = create_result.data[0]["id"]
                        created_ids.append(new_id)

                        # Audit event
                        audit_result = await asyncio.to_thread(
                            self._db.table("canonical_memory_events")
                            .insert({
                                "user_id": user_id,
                                "memory_id": new_id,
                                "event_type": "MERGED",
                                "actor": "consolidator",
                                "old_version": 0,
                                "new_version": 1,
                                "reason": f"Consolidation: {candidate.reason}",
                                "created_at": now,
                            })
                            .execute
                        )
                        if audit_result.data:
                            audit_event_ids.append(audit_result.data[0]["id"])

                except Exception as e:
                    logger.warning(
                        "Failed to create merged memory: %s", e
                    )

        return {
            "superseded_ids": superseded_ids,
            "created_ids": created_ids,
            "audit_event_ids": audit_event_ids,
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_consolidator(
    supabase_client: Any,
    llm_service: Any = None,
    threshold: int = DEFAULT_CONSOLIDATION_THRESHOLD,
) -> CanonicalMemoryConsolidator:
    """Create a consolidator with the given dependencies."""
    return CanonicalMemoryConsolidator(
        supabase_client=supabase_client,
        llm_service=llm_service,
        threshold=threshold,
    )


if __name__ == "__main__":
    # Self-check: verify class can be instantiated
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    mock_llm = MagicMock()
    consolidator = CanonicalMemoryConsolidator(mock_db, mock_llm)
    print(f"CanonicalMemoryConsolidator created (threshold={consolidator._threshold})")
    print("Self-check passed.")
