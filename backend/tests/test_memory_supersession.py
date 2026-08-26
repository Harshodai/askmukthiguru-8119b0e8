"""Tests for Bi-Temporal Fact-Key Derivation, Contradiction, and Supersession.

Covers Criteria A2.3, A2.4, A2.5:
- Deterministic single-valued fact key extraction (lives_in, occupation).
- Multi-valued relations (possession, preference, practice) returning None to prevent accidental overwrites.
- Explicit metadata fact_key override support.
- Coexistence of multi-valued facts (both active, valid_to is None).
- Deterministic supersession of single-valued facts (prior fact closed with valid_to, new fact active).
- Unbounded duplicate prevention (bounded active memory count via supersession & compaction).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from services.memory_service import MemoryService, _derive_fact_key


# ---------------------------------------------------------------------------
# In-Memory Supabase Mock for High-Fidelity Bi-Temporal Testing
# ---------------------------------------------------------------------------


class MockResponse:
    def __init__(self, data: list[dict[str, Any]], count: int | None = None):
        self.data = data
        self.count = count


class MockQueryBuilder:
    def __init__(self, store: list[dict[str, Any]]):
        self._store = store
        self._action = "select"
        self._select_cols = "*"
        self._count_mode: str | None = None
        self._insert_data: list[dict[str, Any]] | None = None
        self._update_data: dict[str, Any] | None = None
        self._filters: list[Any] = []
        self._order_col: str | None = None
        self._order_desc: bool = False
        self._range_start: int | None = None
        self._range_end: int | None = None
        self._limit: int | None = None

    def select(self, cols: str = "*", count: str | None = None):
        self._action = "select"
        self._select_cols = cols
        self._count_mode = count
        return self

    def insert(self, data: dict[str, Any] | list[dict[str, Any]]):
        self._action = "insert"
        if isinstance(data, list):
            self._insert_data = [dict(d) for d in data]
        else:
            self._insert_data = [dict(data)]
        return self

    def update(self, data: dict[str, Any]):
        self._action = "update"
        self._update_data = dict(data)
        return self

    def delete(self):
        self._action = "delete"
        return self

    def eq(self, col: str, val: Any):
        self._filters.append(lambda row: row.get(col) == val)
        return self

    def in_(self, col: str, vals: list[Any]):
        self._filters.append(lambda row: row.get(col) in vals)
        return self

    def is_(self, col: str, val: Any):
        if val == "null" or val is None:
            self._filters.append(lambda row: row.get(col) is None)
        else:
            self._filters.append(lambda row: row.get(col) == val)
        return self

    def order(self, col: str, desc: bool = False):
        self._order_col = col
        self._order_desc = desc
        return self

    def range(self, start: int, end: int):
        self._range_start = start
        self._range_end = end
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def execute(self) -> MockResponse:
        if self._action == "insert":
            inserted = []
            for item in (self._insert_data or []):
                row = dict(item)
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", datetime.now(UTC).isoformat())
                row.setdefault("valid_to", None)
                self._store.append(row)
                inserted.append(row)
            return MockResponse(inserted, count=len(inserted))

        matching = [r for r in self._store if all(f(r) for f in self._filters)]

        if self._action == "update":
            updated = []
            for row in matching:
                row.update(self._update_data or {})
                updated.append(dict(row))
            return MockResponse(updated, count=len(updated))

        if self._action == "delete":
            deleted = []
            for row in list(matching):
                self._store.remove(row)
                deleted.append(row)
            return MockResponse(deleted, count=len(deleted))

        # select action
        total_count = len(matching)
        result_rows = [dict(r) for r in matching]

        if self._order_col:
            result_rows.sort(
                key=lambda r: str(r.get(self._order_col) or ""),
                reverse=self._order_desc,
            )

        if self._range_start is not None and self._range_end is not None:
            result_rows = result_rows[self._range_start : self._range_end + 1]
        elif self._limit is not None:
            result_rows = result_rows[: self._limit]

        return MockResponse(result_rows, count=total_count if self._count_mode else None)


class MockSupabaseClient:
    def __init__(self):
        self.tables: dict[str, list[dict[str, Any]]] = {
            "guru_memories": [],
            "guru_core_memory": [],
            "guru_session_summaries": [],
        }

    def table(self, name: str) -> MockQueryBuilder:
        if name not in self.tables:
            self.tables[name] = []
        return MockQueryBuilder(self.tables[name])

    def rpc(self, name: str, params: dict[str, Any]):
        mock = MagicMock()
        mock.execute.return_value = MockResponse([])
        return mock


class MockEmbeddingService:
    def encode_single_full(self, text: str) -> dict[str, Any]:
        return {"dense": [0.05] * 1024}


TEST_USER_ID = "a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6"


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_derive_fact_key_multi_valued_returns_none():
    """Multi-valued relations (possession, preference, practice) must return None.

    This ensures statements like 'I have anxiety' and 'I have a daughter' never
    collide or auto-supersede each other.
    """
    assert _derive_fact_key("I have anxiety about work") is None
    assert _derive_fact_key("I have a daughter") is None
    assert _derive_fact_key("I practice meditation") is None
    assert _derive_fact_key("I prefer morning meditation") is None
    assert _derive_fact_key("I like green tea") is None
    assert _derive_fact_key("I have 2 pets") is None
    assert _derive_fact_key("Seeker feels deep sorrow") is None
    assert _derive_fact_key("", metadata={"claim": "Seeker has anxiety about work"}) is None
    assert _derive_fact_key("", metadata={"insight": "Daily meditation practice"}) is None


def test_derive_fact_key_single_valued():
    """Single-valued relations (lives_in, occupation) must resolve to deterministic user:<relation> keys."""
    # Location / lives_in patterns
    assert _derive_fact_key("I live in Delhi") == "user:lives_in"
    assert _derive_fact_key("I moved to Chennai") == "user:lives_in"
    assert _derive_fact_key("User lives at Bangalore") == "user:lives_in"
    assert _derive_fact_key("Seeker moved to London") == "user:lives_in"
    assert _derive_fact_key("we live in Pune") == "user:lives_in"

    # Occupation patterns
    assert _derive_fact_key("I work as an engineer") == "user:occupation"
    assert _derive_fact_key("I study physics") == "user:occupation"
    assert _derive_fact_key("User works at Google") == "user:occupation"
    assert _derive_fact_key("Seeker studies psychology") == "user:occupation"

    # Metadata candidate extraction
    assert _derive_fact_key("", metadata={"claim": "Seeker works as a physician"}) == "user:occupation"
    assert _derive_fact_key("", metadata={"insight": "User moved to Seattle"}) == "user:lives_in"


def test_derive_fact_key_explicit_metadata():
    """Explicit metadata['fact_key'] overrides auto-derivation and is sanitized."""
    assert _derive_fact_key("any content", metadata={"fact_key": "user:custom"}) == "user:custom"
    assert (
        _derive_fact_key("I live in Delhi", metadata={"fact_key": "user:explicit_override"})
        == "user:explicit_override"
    )
    # Special character sanitization and lowercasing
    assert (
        _derive_fact_key("", metadata={"fact_key": "USER:Special_Slot#123!"})
        == "user:special_slot_123"
    )
    assert _derive_fact_key("", metadata={"fact_key": "  user:custom_slot  "}) == "user:custom_slot"


@pytest.mark.asyncio
async def test_multi_valued_facts_coexist():
    """Multi-valued facts added sequentially both remain active (valid_to is None)."""
    supabase = MockSupabaseClient()
    embedding_svc = MockEmbeddingService()
    service = MemoryService(supabase_client=supabase, embedding_service=embedding_svc)

    mem1 = await service.add_explicit(
        TEST_USER_ID, "I have anxiety about work", run_compaction=False
    )
    mem2 = await service.add_explicit(
        TEST_USER_ID, "I have a daughter", run_compaction=False
    )
    mem3 = await service.add_explicit(
        TEST_USER_ID, "I practice meditation", run_compaction=False
    )

    assert mem1 and mem2 and mem3
    raw_store = supabase.tables["guru_memories"]
    assert len(raw_store) == 3

    # All three memories must remain active with valid_to == None
    for row in raw_store:
        assert row["valid_to"] is None
        assert row.get("fact_key") is None

    # Querying active memories returns all 3
    listing = await service.list_memories(TEST_USER_ID)
    assert listing["total"] == 3
    contents = [m["content"] for m in listing["memories"]]
    assert "I have anxiety about work" in contents
    assert "I have a daughter" in contents
    assert "I practice meditation" in contents


@pytest.mark.asyncio
async def test_single_valued_fact_supersession():
    """Adding an updated single-valued fact supersedes and closes the prior fact."""
    supabase = MockSupabaseClient()
    embedding_svc = MockEmbeddingService()
    service = MemoryService(supabase_client=supabase, embedding_service=embedding_svc)

    # 1. Add initial location: Delhi
    delhi_mem = await service.add_explicit(
        TEST_USER_ID, "I live in Delhi", run_compaction=False
    )
    assert delhi_mem["fact_key"] == "user:lives_in"
    assert delhi_mem["valid_from"] is not None

    raw_store = supabase.tables["guru_memories"]
    assert len(raw_store) == 1
    assert raw_store[0]["content"] == "I live in Delhi"
    assert raw_store[0]["valid_to"] is None

    # 2. Add contradictory/updated location: Chennai
    chennai_mem = await service.add_explicit(
        TEST_USER_ID, "I moved to Chennai", run_compaction=False
    )
    assert chennai_mem["fact_key"] == "user:lives_in"
    assert chennai_mem["valid_from"] is not None

    # Total rows in store is 2 (bi-temporal audit history preserved)
    assert len(raw_store) == 2

    # Prior Delhi fact is now closed: valid_to is set to Chennai's valid_from timestamp
    delhi_row = next(r for r in raw_store if r["content"] == "I live in Delhi")
    chennai_row = next(r for r in raw_store if r["content"] == "I moved to Chennai")

    assert delhi_row["valid_to"] is not None
    assert delhi_row["valid_to"] == chennai_mem["valid_from"]
    assert chennai_row["valid_to"] is None

    # Active listing returns ONLY the latest active fact (Chennai)
    active_listing = await service.list_memories(TEST_USER_ID)
    assert active_listing["total"] == 1
    assert len(active_listing["memories"]) == 1
    assert active_listing["memories"][0]["content"] == "I moved to Chennai"
    assert active_listing["memories"][0]["valid_to"] is None


@pytest.mark.asyncio
async def test_unbounded_duplicate_prevention(monkeypatch):
    """Repeated identical facts and accumulated unkeyed memories remain strictly bounded.

    Part A: Repeated insertions of single-valued facts supersede each other, keeping
            active count bounded at exactly 1.
    Part B: Memory compaction triggers when unkeyed memory count > 15, consolidating
            to <= 8 memories.
    """
    supabase = MockSupabaseClient()
    embedding_svc = MockEmbeddingService()
    service = MemoryService(supabase_client=supabase, embedding_service=embedding_svc)

    # --- Part A: Single-valued fact duplicate boundedness ---
    for _ in range(5):
        await service.add_explicit(TEST_USER_ID, "I live in Delhi", run_compaction=False)

    raw_store = supabase.tables["guru_memories"]
    assert len(raw_store) == 5

    # Exactly 1 active row remains
    active_rows = [r for r in raw_store if r["valid_to"] is None]
    closed_rows = [r for r in raw_store if r["valid_to"] is not None]
    assert len(active_rows) == 1
    assert len(closed_rows) == 4

    active_listing = await service.list_memories(TEST_USER_ID)
    assert active_listing["total"] == 1

    # --- Part B: Memory compaction bounding unkeyed memories ---
    # Clear store for clean compaction test
    supabase.tables["guru_memories"].clear()

    monkeypatch.setattr("services.memory_service.settings.llm_provider", "openrouter")
    monkeypatch.setattr("services.memory_service.settings.openrouter_classify_model", "test-model")

    mock_client = AsyncMock()
    mock_completions = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[
        0
    ].message.content = '{"compacted_memories": ["Compacted Memory 1", "Compacted Memory 2", "Compacted Memory 3"]}'
    mock_completions.create.return_value = mock_response
    mock_client.chat = MagicMock()
    mock_client.chat.completions = mock_completions

    import openai

    class MockAsyncOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = mock_client.chat

    monkeypatch.setattr(openai, "AsyncOpenAI", MockAsyncOpenAI)

    # Add 16 distinct unkeyed memories with run_compaction=True
    for i in range(16):
        await service.add_explicit(
            TEST_USER_ID, f"Spiritual reflection number {i}", run_compaction=True
        )

    # After inserting 16th item, compaction triggered and consolidated to 3 memories
    final_store = supabase.tables["guru_memories"]
    assert len(final_store) <= 8
    assert len(final_store) == 3
    final_listing = await service.list_memories(TEST_USER_ID)
    assert final_listing["total"] == 3


@pytest.mark.asyncio
async def test_mixed_single_and_multi_valued_facts_isolation():
    """Single-valued supersession isolates by fact_key and does not affect other keys or multi-valued facts."""
    supabase = MockSupabaseClient()
    embedding_svc = MockEmbeddingService()
    service = MemoryService(supabase_client=supabase, embedding_service=embedding_svc)

    # 1. Location fact
    await service.add_explicit(TEST_USER_ID, "I live in Delhi", run_compaction=False)
    # 2. Occupation fact
    await service.add_explicit(TEST_USER_ID, "I work as an engineer", run_compaction=False)
    # 3. Multi-valued facts
    await service.add_explicit(TEST_USER_ID, "I have anxiety about work", run_compaction=False)
    await service.add_explicit(TEST_USER_ID, "I have a daughter", run_compaction=False)

    # 4. Update location to Chennai (should ONLY supersede location, not occupation or multi-valued facts)
    await service.add_explicit(TEST_USER_ID, "I moved to Chennai", run_compaction=False)

    # 5. Update occupation to Doctor (should ONLY supersede occupation)
    await service.add_explicit(TEST_USER_ID, "I work as a doctor", run_compaction=False)

    raw_store = supabase.tables["guru_memories"]
    assert len(raw_store) == 6

    active_rows = [r for r in raw_store if r["valid_to"] is None]
    assert len(active_rows) == 4

    active_contents = {r["content"] for r in active_rows}
    assert active_contents == {
        "I moved to Chennai",
        "I work as a doctor",
        "I have anxiety about work",
        "I have a daughter",
    }
