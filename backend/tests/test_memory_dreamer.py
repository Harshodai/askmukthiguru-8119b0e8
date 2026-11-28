"""Unit tests for Enterprise Memory Dreamer (Sleep-Time Compute).

Tests the 5 core stages of Anthropic's agent memory consolidation:
1. Snapshot creation & fail-closed contract.
2. Transcript Grounding Audit (evicting hallucinated/unsupported claims).
3. Contradiction & Temporal Evolution (newer transcript wins).
4. Mathematical Decay & Selective Pruning.
5. SeekerCoreDashboard Synthesis & guru_core_memory persistence.
"""

from __future__ import annotations

import pytest

from services.canonical_memory.dreamer import MemoryDreamer


class FakeSupabaseClient:
    """In-memory mock for Supabase tables used by MemoryDreamer."""

    def __init__(self, memories: list[dict], transcripts: list[dict]):
        self._memories = {m["id"]: dict(m) for m in memories}
        self._transcripts = list(transcripts)
        self._snapshots = []
        self._audit_events = []
        self._core_memories = {}

    def table(self, table_name: str):
        return FakeTableQuery(self, table_name)


class FakeTableQuery:
    def __init__(self, client: FakeSupabaseClient, table_name: str):
        self._client = client
        self._table = table_name
        self._filters = {}
        self._selected = None
        self._limit = None
        self._action = "select"
        self._action_data = None

    def select(self, cols: str = "*"):
        self._selected = cols
        self._action = "select"
        return self

    def eq(self, col: str, val: any):
        self._filters[col] = val
        return self

    def in_(self, col: str, vals: list):
        self._filters[f"{col}__in"] = list(vals)
        return self

    def order(self, col: str, desc: bool = False):
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def insert(self, data: any):
        self._action = "insert"
        self._action_data = data
        return self

    def upsert(self, data: any, on_conflict: str = "user_id"):
        self._action = "upsert"
        self._action_data = data
        return self

    def update(self, data: any):
        self._action = "update"
        self._action_data = data
        return self

    def execute(self):
        if self._action == "insert":
            data = self._action_data
            if self._table == "canonical_memory_compaction_snapshots":
                row = dict(data)
                row.setdefault("id", "snap-test-uuid")
                self._client._snapshots.append(row)
                return FakeResult([row])
            elif self._table == "canonical_memory_events":
                row = dict(data)
                row.setdefault("id", "audit-test-uuid")
                self._client._audit_events.append(row)
                return FakeResult([row])
            elif self._table == "guru_core_memory":
                row = dict(data)
                self._client._core_memories[row["user_id"]] = row
                return FakeResult([row])
            return FakeResult([data])

        elif self._action == "upsert":
            data = self._action_data
            row = dict(data)
            self._client._core_memories[row["user_id"]] = row
            return FakeResult([row])

        elif self._action == "update":
            updated = []
            for _mid, m in self._client._memories.items():
                match = True
                for k, v in self._filters.items():
                    if k == "id" and m.get("id") != v:
                        match = False
                    elif k == "user_id" and m.get("user_id") != v:
                        match = False
                    elif k == "tenant_id" and m.get("tenant_id") != v:
                        match = False
                if match:
                    m.update(self._action_data)
                    updated.append(m)
            return FakeResult(updated)

        elif self._action == "select":
            if self._table == "canonical_memories":
                res = []
                for m in self._client._memories.values():
                    match = True
                    for k, v in self._filters.items():
                        if k.endswith("__in"):
                            col = k[:-4]
                            if m.get(col) not in v:
                                match = False
                        elif m.get(k) != v:
                            match = False
                    if match:
                        res.append(dict(m))
                return FakeResult(res)
            elif self._table in ("messages", "conversations"):
                res = []
                for t in self._client._transcripts:
                    match = True
                    for k, v in self._filters.items():
                        if t.get(k) != v:
                            match = False
                    if match:
                        res.append(dict(t))
                return FakeResult(res)
            elif self._table == "canonical_memory_compaction_snapshots":
                return FakeResult(list(self._client._snapshots))
            return FakeResult([])


class FakeResult:
    def __init__(self, data: list):
        self.data = data


@pytest.fixture
def test_user_id():
    return "33333333-3333-4333-8333-333333333333"


@pytest.fixture
def seeded_client(test_user_id):
    # Setup test memories:
    # 1. Grounded memory (user actually said this)
    # 2. Hallucinated memory (user never said this)
    # 3. Older contradictory memory ("User feels depressed")
    # 4. Newer state memory ("User feels inner peace and joy")
    # 5. Low decay memory (< 0.15) to test pruning
    # 6. Explicit memory to test decay exemption
    memories = [
        {
            "id": "mem-1-grounded",
            "user_id": test_user_id,
            "tenant_id": "oneness",
            "statement": "User practices Serene Mind meditation daily.",
            "fact_key": "user:practice:serene_mind",
            "memory_type": "PREFERENCE",
            "status": "active",
            "confidence": 0.9,
            "importance": 0.8,
            "source_conversation_id": "conv-1",
            "created_at": "2026-11-01T10:00:00Z",
            "metadata": {"decay_score": 1.0},
        },
        {
            "id": "mem-2-hallucinated",
            "user_id": test_user_id,
            "tenant_id": "oneness",
            "statement": "User visited Kyoto temples in 2021.",
            "fact_key": "user:travel:kyoto",
            "memory_type": "PROFILE",
            "status": "active",
            "confidence": 0.7,
            "importance": 0.3,
            "source_conversation_id": "conv-1",
            "created_at": "2026-11-01T10:05:00Z",
            "metadata": {"decay_score": 0.9},
        },
        {
            "id": "mem-3-old-conflict",
            "user_id": test_user_id,
            "tenant_id": "oneness",
            "statement": "User is struggling with overwhelming anxiety at work.",
            "fact_key": "user:state:work_anxiety",
            "memory_type": "REFLECTION",
            "status": "active",
            "confidence": 0.85,
            "importance": 0.7,
            "source_conversation_id": "conv-1",
            "created_at": "2026-11-01T10:10:00Z",
            "metadata": {"decay_score": 0.8},
        },
        {
            "id": "mem-4-new-state",
            "user_id": test_user_id,
            "tenant_id": "oneness",
            "statement": "User has overcome work anxiety and experiences inner peace.",
            "fact_key": "user:state:work_anxiety",
            "memory_type": "REFLECTION",
            "status": "active",
            "confidence": 0.95,
            "importance": 0.8,
            "source_conversation_id": "conv-2",
            "created_at": "2026-11-07T12:00:00Z",
            "metadata": {"decay_score": 1.0},
        },
        {
            "id": "mem-5-decayed",
            "user_id": test_user_id,
            "tenant_id": "oneness",
            "statement": "User drank green tea this morning.",
            "fact_key": None,
            "memory_type": "TEMPORARY_CONTEXT",
            "status": "active",
            "confidence": 0.5,
            "importance": 0.1,
            "source_conversation_id": "conv-1",
            "created_at": "2026-10-01T08:00:00Z",
            "metadata": {"decay_score": 0.14},
        },
        {
            "id": "mem-6-explicit",
            "user_id": test_user_id,
            "tenant_id": "oneness",
            "statement": "Always explain Sanskrit terms in simple English.",
            "fact_key": "user:instruction:sanskrit",
            "memory_type": "USER_EXPLICIT",
            "status": "active",
            "confidence": 1.0,
            "importance": 0.9,
            "source_conversation_id": "conv-1",
            "created_at": "2026-10-01T08:05:00Z",
            "metadata": {"decay_score": 0.10},  # Low score, but USER_EXPLICIT is immune
        },
    ]

    transcripts = [
        {
            "id": "msg-1",
            "conversation_id": "conv-1",
            "role": "user",
            "content": "I practice Serene Mind meditation every morning for 10 minutes. I have overwhelming anxiety at work.",
            "created_at": "2026-11-01T10:00:00Z",
        },
        {
            "id": "msg-2",
            "conversation_id": "conv-1",
            "role": "user",
            "content": "Please always explain any Sanskrit spiritual terms in simple English.",
            "created_at": "2026-11-01T10:05:00Z",
        },
        {
            "id": "msg-3",
            "conversation_id": "conv-2",
            "role": "user",
            "content": "The practices really worked! I have completely overcome my work anxiety and feel deep inner peace now.",
            "created_at": "2026-11-07T12:00:00Z",
        },
    ]

    return FakeSupabaseClient(memories=memories, transcripts=transcripts)


@pytest.mark.asyncio
async def test_dreamer_grounding_audit_evicts_hallucination(seeded_client, test_user_id):
    """Memory with no transcript support (Kyoto temple) must be evicted."""
    dreamer = MemoryDreamer(supabase_client=seeded_client)

    report = await dreamer.dream(user_id=test_user_id, dry_run=False)

    # Hallucinated memory must be evicted
    assert report.evicted_count >= 1
    kyoto_mem = seeded_client._memories["mem-2-hallucinated"]
    assert kyoto_mem["status"] == "deleted"

    # Grounded memory must remain active
    grounded_mem = seeded_client._memories["mem-1-grounded"]
    assert grounded_mem["status"] == "active"
    assert seeded_client._audit_events
    assert {event["actor"] for event in seeded_client._audit_events} == {"system"}


@pytest.mark.asyncio
async def test_dreamer_resolves_temporal_contradiction(seeded_client, test_user_id):
    """Newer state (overcome anxiety) must supersede older state (struggling with anxiety)."""
    dreamer = MemoryDreamer(supabase_client=seeded_client)

    report = await dreamer.dream(user_id=test_user_id, dry_run=False)

    assert report.superseded_count >= 1
    old_mem = seeded_client._memories["mem-3-old-conflict"]
    assert old_mem["status"] == "superseded"

    new_mem = seeded_client._memories["mem-4-new-state"]
    assert new_mem["status"] == "active"


@pytest.mark.asyncio
async def test_dreamer_mathematical_decay_and_pruning(seeded_client, test_user_id):
    """Decayed temporary memory (< 0.15) expires, while USER_EXPLICIT is protected."""
    dreamer = MemoryDreamer(supabase_client=seeded_client)

    report = await dreamer.dream(user_id=test_user_id, dry_run=False)

    assert report.decayed_count >= 1

    # mem-5 was decay_score 0.14 and low importance -> expired
    tea_mem = seeded_client._memories["mem-5-decayed"]
    assert tea_mem["status"] == "expired"

    # mem-6 was decay_score 0.10, but USER_EXPLICIT -> stays active
    explicit_mem = seeded_client._memories["mem-6-explicit"]
    assert explicit_mem["status"] == "active"


@pytest.mark.asyncio
async def test_dreamer_synthesizes_and_persists_dashboard(seeded_client, test_user_id):
    """Stage 5 must re-synthesize SeekerCoreDashboard and persist to guru_core_memory."""
    dreamer = MemoryDreamer(supabase_client=seeded_client)

    report = await dreamer.dream(user_id=test_user_id, dry_run=False)

    assert report.dashboard_updated is True
    assert test_user_id in seeded_client._core_memories

    core_record = seeded_client._core_memories[test_user_id]
    content = core_record["content"]

    assert "# Seeker Core Dashboard" in content
    assert "Serene Mind" in content
    assert len(content) <= 2048


@pytest.mark.asyncio
async def test_dreamer_snapshot_and_dry_run(seeded_client, test_user_id):
    """Dry run identifies actions without modifying database state."""
    dreamer = MemoryDreamer(supabase_client=seeded_client)

    report = await dreamer.dream(user_id=test_user_id, dry_run=True)

    assert report.dry_run is True
    assert report.evicted_count >= 1

    # In dry run, records must remain active
    kyoto_mem = seeded_client._memories["mem-2-hallucinated"]
    assert kyoto_mem["status"] == "active"
