"""Tests for Memory Resolver — Phase 5 of Adaptive Memory System.

Unit tests using mocked Supabase client to verify resolution logic
without requiring a live database. Covers: CREATE, UPDATE, MERGE,
IGNORE, EXPIRE, DELETE, ESCALATE, idempotency, audit events,
fact-key supersession, and optimistic concurrency.

Run: cd backend && .venv/bin/pytest tests/test_canonical_memory_resolution.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from services.canonical_memory.judge import DecisionType, MemoryDecision
from services.canonical_memory.models import MemoryCandidate, MemoryType
from services.canonical_memory.resolver import MemoryResolver, ResolutionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_candidate(**overrides: Any) -> MemoryCandidate:
    """Create a MemoryCandidate with sensible defaults."""
    defaults = {
        "statement": "User prefers concise answers.",
        "memory_type": MemoryType.PREFERENCE,
        "confidence": 0.9,
        "importance": 0.7,
        "fact_key": "user:prefers_tone",
        "evidence": "I prefer concise answers.",
        "source_turn_index": 3,
        "explicit_request": False,
    }
    defaults.update(overrides)
    return MemoryCandidate(**defaults)


def _make_decision(
    candidate: Optional[MemoryCandidate] = None,
    decision: DecisionType = DecisionType.CREATE,
    superseded_memory_id: Optional[str] = None,
    merged_memory_ids: Optional[list[str]] = None,
    reason: str = "test reason",
    **kwargs: Any,
) -> MemoryDecision:
    """Create a MemoryDecision with sensible defaults."""
    if candidate is None:
        candidate = _make_candidate()
    return MemoryDecision(
        candidate=candidate,
        decision=decision,
        superseded_memory_id=superseded_memory_id,
        merged_memory_ids=merged_memory_ids or [],
        reason=reason,
        **kwargs,
    )


def _make_existing_memory(**overrides: Any) -> dict:
    """Create a canonical_memories row dict."""
    now = _now_iso()
    row = {
        "id": _uid(),
        "user_id": _uid(),
        "tenant_id": "oneness",
        "memory_type": "PREFERENCE",
        "statement": "User prefers concise answers.",
        "normalized_statement": "user prefers concise answers.",
        "fact_key": "user:prefers_tone",
        "confidence": 0.85,
        "importance": 0.6,
        "sensitivity": "normal",
        "status": "active",
        "source_conversation_id": "conv-1",
        "source_message_id": "msg-1",
        "source_turn_index": 3,
        "extraction_method": "llm",
        "evidence_count": 1,
        "created_at": now,
        "updated_at": now,
        "valid_from": now,
        "valid_to": None,
        "version": 1,
        "metadata": {},
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Mock Supabase chain helper
# ---------------------------------------------------------------------------

class MockSupabase:
    """Simulates the Supabase client chain for resolver testing.

    Tracks insertions, updates, and queries for assertion.
    """

    def __init__(self):
        self.memories: dict[str, dict] = {}  # id → row
        self.events: list[dict] = []
        self._table_returns: dict[str, Any] = {}
        self._last_query_result: Any = None

    def table(self, name: str):
        """Return a table proxy that chains operations."""
        return _TableProxy(self, name)


class _TableProxy:
    """Chained mock for supabase.table(...).select(...).eq(...) etc."""

    def __init__(self, mock: MockSupabase, table_name: str):
        self._mock = mock
        self._table = table_name
        self._filters: dict[str, Any] = {}
        self._order_field: Optional[str] = None
        self._order_desc: bool = False
        self._limit_n: Optional[int] = None
        self._insert_data: Optional[dict] = None
        self._update_data: Optional[dict] = None

    def select(self, *args: Any) -> "_TableProxy":
        return self

    def insert(self, data: dict) -> "_TableProxy":
        self._insert_data = data
        return self

    def update(self, data: dict) -> "_TableProxy":
        self._update_data = data
        return self

    def delete(self) -> "_TableProxy":
        return self

    def eq(self, field: str, value: Any) -> "_TableProxy":
        self._filters[field] = value
        return self

    def is_(self, field: str, value: Any) -> "_TableProxy":
        self._filters[field] = value
        return self

    def in_(self, field: str, values: list) -> "_TableProxy":
        self._filters[field] = ("in", values)
        return self

    def order(self, field: str, desc: bool = False) -> "_TableProxy":
        self._order_field = field
        self._order_desc = desc
        return self

    def limit(self, n: int) -> "_TableProxy":
        self._limit_n = n
        return self

    def range(self, start: int, end: int) -> "_TableProxy":
        return self

    def single(self) -> "_TableProxy":
        return self

    def execute(self) -> MagicMock:
        result = MagicMock()

        if self._insert_data is not None:
            # INSERT. Route by TABLE, not by whether the row carries an "id":
            # audit rows do carry one, so the old id-first branch filed every
            # event into `memories` and left `events` permanently empty, which
            # made every audit assertion fail against a working resolver.
            data = self._insert_data.copy()
            if self._table == "canonical_memory_events":
                data.setdefault("id", _uid())
                self._mock.events.append(data)
            else:
                new_id = data.get("id") or _uid()
                data["id"] = new_id
                self._mock.memories[new_id] = data
            result.data = [data]

        elif self._update_data is not None:
            # UPDATE — apply to matching rows
            updated = []
            for mem_id, mem in self._mock.memories.items():
                if self._matches(mem):
                    mem.update(self._update_data)
                    updated.append(mem)
            result.data = updated

        elif self._table == "canonical_memory_events":
            # INSERT audit event
            if self._insert_data:
                self._mock.events.append(self._insert_data)
                result.data = [self._insert_data]
            else:
                result.data = self._mock.events

        else:
            # SELECT — filter from memories
            rows = []
            for mem in self._mock.memories.values():
                if self._matches(mem):
                    rows.append(mem)

            # Apply ordering
            if self._order_field:
                rows.sort(
                    key=lambda r: r.get(self._order_field, ""),
                    reverse=self._order_desc,
                )

            # Apply limit
            if self._limit_n is not None:
                rows = rows[: self._limit_n]

            result.data = rows

        return result

    def _matches(self, row: dict) -> bool:
        """Check if a row matches all filters."""
        for field, value in self._filters.items():
            if isinstance(value, tuple) and value[0] == "in":
                if row.get(field) not in value[1]:
                    return False
            elif row.get(field) != value:
                return False
        return True


# ---------------------------------------------------------------------------
# 1. CREATE
# ---------------------------------------------------------------------------

class TestCreateResolution:
    @pytest.mark.asyncio
    async def test_create_inserts_new_memory(self):
        """CREATE should insert a new memory with status='active'."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        candidate = _make_candidate()
        decision = _make_decision(candidate=candidate, decision=DecisionType.CREATE)

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "created"
        assert result.memory_id is not None
        assert result.memory_id in mock_db.memories
        mem = mock_db.memories[result.memory_id]
        assert mem["status"] == "active"
        assert mem["version"] == 1
        assert mem["user_id"] == "user-001"
        assert mem["fact_key"] == "user:prefers_tone"
        assert mem["statement"] == "User prefers concise answers."

    @pytest.mark.asyncio
    async def test_create_with_same_fact_key_supersedes_existing(self):
        """CREATE with same fact_key supersedes old memory (single-valued)."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        # Seed existing memory
        old_id = _uid()
        mock_db.memories[old_id] = _make_existing_memory(
            id=old_id,
            user_id="user-001",
            fact_key="user:prefers_tone",
            statement="User prefers detailed answers.",
            normalized_statement="user prefers detailed answers.",
            status="active",
            version=1,
        )

        # New candidate with same fact_key but different value
        new_candidate = _make_candidate(
            statement="User prefers concise answers.",
            fact_key="user:prefers_tone",
        )
        decision = _make_decision(
            candidate=new_candidate, decision=DecisionType.CREATE
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "created"
        assert old_id in result.superseded_ids
        assert mock_db.memories[old_id]["status"] == "superseded"
        assert mock_db.memories[old_id]["valid_to"] is not None
        # New memory is active
        new_mem = mock_db.memories[result.memory_id]
        assert new_mem["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_audit_event_written(self):
        """Every CREATE writes an audit event."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        candidate = _make_candidate()
        decision = _make_decision(candidate=candidate, decision=DecisionType.CREATE)

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.audit_event_id is not None
        assert len(mock_db.events) >= 1
        event = mock_db.events[-1]
        assert event["event_type"] == "CREATED"
        assert event["memory_id"] == result.memory_id
        assert event["user_id"] == "user-001"

    @pytest.mark.asyncio
    async def test_create_multi_valued_fact_key_no_supersede(self):
        """Multi-valued fact_key should not supersede (judge handles dedup)."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        # Seed existing
        old_id = _uid()
        mock_db.memories[old_id] = _make_existing_memory(
            id=old_id,
            user_id="user-001",
            fact_key="user:spiritual_interest",
            statement="User is interested in meditation.",
            status="active",
            version=1,
        )

        # New different interest (multi-valued)
        new_candidate = _make_candidate(
            statement="User is interested in yoga.",
            fact_key="user:spiritual_interest",
        )
        decision = _make_decision(
            candidate=new_candidate, decision=DecisionType.CREATE
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "created"
        # Old memory should NOT be superseded (multi-valued key)
        assert old_id not in result.superseded_ids
        assert mock_db.memories[old_id]["status"] == "active"


# ---------------------------------------------------------------------------
# 2. UPDATE
# ---------------------------------------------------------------------------

class TestUpdateResolution:
    @pytest.mark.asyncio
    async def test_update_supersedes_old_and_creates_new(self):
        """UPDATE supersedes the target memory and creates a new version."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        old_id = _uid()
        mock_db.memories[old_id] = _make_existing_memory(
            id=old_id,
            user_id="user-001",
            fact_key="user:prefers_tone",
            statement="User prefers detailed answers.",
            status="active",
            version=2,
        )

        new_candidate = _make_candidate(
            statement="User prefers concise answers.",
            fact_key="user:prefers_tone",
        )
        decision = _make_decision(
            candidate=new_candidate,
            decision=DecisionType.UPDATE,
            superseded_memory_id=old_id,
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "updated"
        assert old_id in result.superseded_ids
        assert mock_db.memories[old_id]["status"] == "superseded"
        assert mock_db.memories[old_id]["valid_to"] is not None
        # New memory active at version 1
        new_mem = mock_db.memories[result.memory_id]
        assert new_mem["status"] == "active"
        assert new_mem["version"] == 1

    @pytest.mark.asyncio
    async def test_update_audit_event_written(self):
        """UPDATE writes an UPDATED audit event."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        old_id = _uid()
        mock_db.memories[old_id] = _make_existing_memory(
            id=old_id, user_id="user-001", version=3, status="active"
        )

        decision = _make_decision(
            decision=DecisionType.UPDATE,
            superseded_memory_id=old_id,
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert len(mock_db.events) >= 1
        event = mock_db.events[-1]
        assert event["event_type"] == "UPDATED"
        assert event["old_version"] == 3


# ---------------------------------------------------------------------------
# 3. MERGE
# ---------------------------------------------------------------------------

class TestMergeResolution:
    @pytest.mark.asyncio
    async def test_merge_supersedes_both_and_creates_merged(self):
        """MERGE supersedes source memories and creates a combined one."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        id_a = _uid()
        id_b = _uid()
        mock_db.memories[id_a] = _make_existing_memory(
            id=id_a,
            user_id="user-001",
            statement="User prefers concise for code.",
            status="active",
            version=1,
            evidence_count=2,
        )
        mock_db.memories[id_b] = _make_existing_memory(
            id=id_b,
            user_id="user-001",
            statement="User prefers detailed for concepts.",
            status="active",
            version=1,
            evidence_count=1,
        )

        merged_candidate = _make_candidate(
            statement="User prefers concise for code, detailed for concepts.",
        )
        decision = _make_decision(
            candidate=merged_candidate,
            decision=DecisionType.MERGE,
            merged_memory_ids=[id_a, id_b],
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "merged"
        assert id_a in result.superseded_ids
        assert id_b in result.superseded_ids
        assert mock_db.memories[id_a]["status"] == "superseded"
        assert mock_db.memories[id_b]["status"] == "superseded"
        # Merged memory has combined evidence count
        merged_mem = mock_db.memories[result.memory_id]
        assert merged_mem["status"] == "active"
        assert merged_mem["evidence_count"] == 3  # 2 + 1

    @pytest.mark.asyncio
    async def test_merge_audit_event_written(self):
        """MERGE writes an audit event with all source IDs."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        id_a = _uid()
        mock_db.memories[id_a] = _make_existing_memory(
            id=id_a, user_id="user-001", status="active"
        )

        decision = _make_decision(
            decision=DecisionType.MERGE,
            merged_memory_ids=[id_a],
        )

        result = await resolver.resolve(decision, user_id="user-001")

        event = mock_db.events[-1]
        assert event["event_type"] == "MERGED"
        assert id_a in event["reason"]


# ---------------------------------------------------------------------------
# 4. IGNORE
# ---------------------------------------------------------------------------

class TestIgnoreResolution:
    @pytest.mark.asyncio
    async def test_ignore_does_nothing(self):
        """IGNORE produces no store mutations."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        candidate = _make_candidate()
        decision = _make_decision(
            candidate=candidate, decision=DecisionType.IGNORE
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "ignored"
        assert result.memory_id is None
        assert len(mock_db.memories) == 0
        assert len(mock_db.events) == 0

    @pytest.mark.asyncio
    async def test_ignore_has_reason(self):
        """IGNORE preserves the judge's reason."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        decision = _make_decision(
            decision=DecisionType.IGNORE,
            reason="Duplicate of existing memory",
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.reason == "Duplicate of existing memory"


# ---------------------------------------------------------------------------
# 5. EXPIRE
# ---------------------------------------------------------------------------

class TestExpireResolution:
    @pytest.mark.asyncio
    async def test_expire_sets_status_expired(self):
        """EXPIRE sets status='expired' and valid_to on the target."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        target_id = _uid()
        mock_db.memories[target_id] = _make_existing_memory(
            id=target_id,
            user_id="user-001",
            status="active",
            version=2,
        )

        candidate = _make_candidate(
            memory_type=MemoryType.TEMPORARY_CONTEXT,
        )
        decision = _make_decision(
            candidate=candidate,
            decision=DecisionType.EXPIRE,
            superseded_memory_id=target_id,
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "expired"
        assert result.memory_id == target_id
        assert mock_db.memories[target_id]["status"] == "expired"
        assert mock_db.memories[target_id]["valid_to"] is not None

    @pytest.mark.asyncio
    async def test_expire_idempotent(self):
        """EXPIRE on already-expired memory is idempotent."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        target_id = _uid()
        mock_db.memories[target_id] = _make_existing_memory(
            id=target_id,
            user_id="user-001",
            status="expired",
        )

        decision = _make_decision(
            decision=DecisionType.EXPIRE,
            superseded_memory_id=target_id,
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "idempotent_expire"

    @pytest.mark.asyncio
    async def test_expire_no_op_when_no_target(self):
        """EXPIRE with no matching memory returns no_op."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        decision = _make_decision(decision=DecisionType.EXPIRE)

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "no_op"


# ---------------------------------------------------------------------------
# 6. DELETE
# ---------------------------------------------------------------------------

class TestDeleteResolution:
    @pytest.mark.asyncio
    async def test_delete_sets_status_deleted(self):
        """DELETE sets status='deleted' on the target."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        target_id = _uid()
        mock_db.memories[target_id] = _make_existing_memory(
            id=target_id,
            user_id="user-001",
            status="active",
        )

        candidate = _make_candidate()
        decision = _make_decision(
            candidate=candidate,
            decision=DecisionType.DELETE,
            superseded_memory_id=target_id,
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "deleted"
        assert result.memory_id == target_id
        assert mock_db.memories[target_id]["status"] == "deleted"
        assert mock_db.memories[target_id]["valid_to"] is not None

    @pytest.mark.asyncio
    async def test_delete_idempotent(self):
        """DELETE on already-deleted memory is idempotent."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        target_id = _uid()
        mock_db.memories[target_id] = _make_existing_memory(
            id=target_id,
            user_id="user-001",
            status="deleted",
        )

        decision = _make_decision(
            decision=DecisionType.DELETE,
            superseded_memory_id=target_id,
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "idempotent_delete"

    @pytest.mark.asyncio
    async def test_delete_audit_event_written(self):
        """DELETE writes a DELETED audit event."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        target_id = _uid()
        mock_db.memories[target_id] = _make_existing_memory(
            id=target_id,
            user_id="user-001",
            status="active",
            version=5,
        )

        decision = _make_decision(
            decision=DecisionType.DELETE,
            superseded_memory_id=target_id,
        )

        result = await resolver.resolve(decision, user_id="user-001")

        event = mock_db.events[-1]
        assert event["event_type"] == "DELETED"
        assert event["old_version"] == 5

    @pytest.mark.asyncio
    async def test_delete_by_semantic_fallback(self):
        """DELETE without explicit target falls back to semantic match."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        # Seed a memory that matches by text similarity
        target_id = _uid()
        mock_db.memories[target_id] = _make_existing_memory(
            id=target_id,
            user_id="user-001",
            statement="I live in Mumbai, India.",
            normalized_statement="i live in mumbai, india.",
            status="active",
        )

        candidate = _make_candidate(
            statement="User lives in Mumbai, India.",
            fact_key="user:lives_in",
        )
        decision = _make_decision(
            candidate=candidate,
            decision=DecisionType.DELETE,
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "deleted"
        assert mock_db.memories[target_id]["status"] == "deleted"


# ---------------------------------------------------------------------------
# 7. ESCALATE
# ---------------------------------------------------------------------------

class TestEscalateResolution:
    @pytest.mark.asyncio
    async def test_escalate_does_nothing(self):
        """ESCALATE produces no store mutations."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        candidate = _make_candidate(sensitivity="highly_sensitive")
        decision = _make_decision(
            candidate=candidate,
            decision=DecisionType.ESCALATE,
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "escalated"
        assert result.memory_id is None
        assert len(mock_db.memories) == 0

    @pytest.mark.asyncio
    async def test_escalate_preserves_metadata(self):
        """ESCALATE preserves judge metadata for downstream processing."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        decision = _make_decision(
            decision=DecisionType.ESCALATE,
            metadata={"consent_required": True},
        )

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.metadata.get("consent_required") is True


# ---------------------------------------------------------------------------
# 8. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    @pytest.mark.asyncio
    async def test_same_decision_twice_same_result(self):
        """Processing the same CREATE decision twice is idempotent."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        candidate = _make_candidate()
        decision = _make_decision(candidate=candidate, decision=DecisionType.CREATE)

        r1 = await resolver.resolve(decision, user_id="user-001")
        r2 = await resolver.resolve(decision, user_id="user-001")

        # Both should succeed; second detects duplicate via fact_key
        assert r1.action == "created"
        assert r2.action in ("created", "idempotent_duplicate")

    @pytest.mark.asyncio
    async def test_double_expire_is_idempotent(self):
        """Expiring an already-expired memory returns idempotent."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        target_id = _uid()
        mock_db.memories[target_id] = _make_existing_memory(
            id=target_id, user_id="user-001", status="expired"
        )

        decision = _make_decision(
            decision=DecisionType.EXPIRE,
            superseded_memory_id=target_id,
        )

        r1 = await resolver.resolve(decision, user_id="user-001")
        r2 = await resolver.resolve(decision, user_id="user-001")

        assert r1.action == "idempotent_expire"
        assert r2.action == "idempotent_expire"

    @pytest.mark.asyncio
    async def test_double_delete_is_idempotent(self):
        """Deleting an already-deleted memory returns idempotent."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        target_id = _uid()
        mock_db.memories[target_id] = _make_existing_memory(
            id=target_id, user_id="user-001", status="deleted"
        )

        decision = _make_decision(
            decision=DecisionType.DELETE,
            superseded_memory_id=target_id,
        )

        r1 = await resolver.resolve(decision, user_id="user-001")
        r2 = await resolver.resolve(decision, user_id="user-001")

        assert r1.action == "idempotent_delete"
        assert r2.action == "idempotent_delete"


# ---------------------------------------------------------------------------
# 9. Audit events
# ---------------------------------------------------------------------------

class TestAuditEvents:
    @pytest.mark.asyncio
    async def test_every_mutation_creates_audit_event(self):
        """CREATE, UPDATE, MERGE, EXPIRE, DELETE all write audit events."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        actions_and_expected = [
            (DecisionType.CREATE, "CREATED"),
            (DecisionType.IGNORE, None),
            (DecisionType.ESCALATE, None),
        ]

        for dec_type, expected_event_type in actions_and_expected:
            initial_event_count = len(mock_db.events)

            if dec_type == DecisionType.CREATE:
                candidate = _make_candidate()
                decision = _make_decision(
                    candidate=candidate, decision=dec_type
                )
            else:
                decision = _make_decision(decision=dec_type)

            await resolver.resolve(decision, user_id="user-001")

            if expected_event_type:
                assert len(mock_db.events) > initial_event_count, (
                    f"{dec_type} should write audit event"
                )
                event = mock_db.events[-1]
                assert event["event_type"] == expected_event_type
            else:
                assert len(mock_db.events) == initial_event_count, (
                    f"{dec_type} should NOT write audit event"
                )

    @pytest.mark.asyncio
    async def test_audit_event_has_required_fields(self):
        """Audit events contain all required fields."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        candidate = _make_candidate()
        decision = _make_decision(candidate=candidate, decision=DecisionType.CREATE)

        await resolver.resolve(decision, user_id="user-001")

        event = mock_db.events[-1]
        assert "id" in event
        assert "user_id" in event
        assert "memory_id" in event
        assert "event_type" in event
        assert "actor" in event
        assert "reason" in event
        assert "created_at" in event


# ---------------------------------------------------------------------------
# 10. Concurrent resolution
# ---------------------------------------------------------------------------

class TestConcurrentResolution:
    @pytest.mark.asyncio
    async def test_concurrent_creates_both_succeed(self):
        """Two concurrent CREATEs with different fact_keys both succeed."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        c1 = _make_candidate(
            statement="User lives in Mumbai.",
            fact_key="user:lives_in",
        )
        c2 = _make_candidate(
            statement="User works as a teacher.",
            fact_key="user:occupation",
            memory_type=MemoryType.PROFILE,
            evidence="I work as a teacher.",
        )

        d1 = _make_decision(candidate=c1, decision=DecisionType.CREATE)
        d2 = _make_decision(candidate=c2, decision=DecisionType.CREATE)

        r1 = await resolver.resolve(d1, user_id="user-001")
        r2 = await resolver.resolve(d2, user_id="user-001")

        assert r1.action == "created"
        assert r2.action == "created"
        assert r1.memory_id != r2.memory_id

    @pytest.mark.asyncio
    async def test_concurrent_same_fact_key_supersedes_correctly(self):
        """Two CREATEs for the same fact_key: first creates, second supersedes."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        c1 = _make_candidate(
            statement="User lives in Mumbai.",
            fact_key="user:lives_in",
        )
        c2 = _make_candidate(
            statement="User lives in Pune.",
            fact_key="user:lives_in",
        )

        d1 = _make_decision(candidate=c1, decision=DecisionType.CREATE)
        d2 = _make_decision(candidate=c2, decision=DecisionType.CREATE)

        r1 = await resolver.resolve(d1, user_id="user-001")
        r2 = await resolver.resolve(d2, user_id="user-001")

        assert r1.action == "created"
        assert r2.action == "created"
        # First memory superseded by second
        assert r1.memory_id in r2.superseded_ids
        assert mock_db.memories[r1.memory_id]["status"] == "superseded"
        assert mock_db.memories[r2.memory_id]["status"] == "active"


# ---------------------------------------------------------------------------
# 11. Version management
# ---------------------------------------------------------------------------

class TestVersionManagement:
    @pytest.mark.asyncio
    async def test_new_memory_starts_at_version_1(self):
        """Newly created memories start at version 1."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        decision = _make_decision(decision=DecisionType.CREATE)

        result = await resolver.resolve(decision, user_id="user-001")

        mem = mock_db.memories[result.memory_id]
        assert mem["version"] == 1

    @pytest.mark.asyncio
    async def test_superseded_old_increments_version(self):
        """Superseding an old memory increments its version."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        old_id = _uid()
        mock_db.memories[old_id] = _make_existing_memory(
            id=old_id,
            user_id="user-001",
            status="active",
            version=3,
        )

        decision = _make_decision(
            decision=DecisionType.UPDATE,
            superseded_memory_id=old_id,
        )

        await resolver.resolve(decision, user_id="user-001")

        assert mock_db.memories[old_id]["version"] == 4


# ---------------------------------------------------------------------------
# 12. Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_unknown_decision_type_returns_error(self):
        """Unknown decision type returns error result."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        decision = _make_decision(decision="UNKNOWN_ACTION")

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "error"
        assert "Unknown decision type" in result.reason

    @pytest.mark.asyncio
    async def test_exception_in_handler_returns_error(self):
        """Exceptions in handlers are caught and returned as error."""
        mock_db = MockSupabase()
        resolver = MemoryResolver(mock_db)

        # Make _find_active_by_fact_key raise
        mock_db.table = MagicMock(side_effect=Exception("DB connection lost"))

        decision = _make_decision(decision=DecisionType.CREATE)

        result = await resolver.resolve(decision, user_id="user-001")

        assert result.action == "error"
        assert "Resolution failed" in result.reason
