"""Test suite for Memory Bi-Temporal Fact-Key, Contradiction, and Supersession.

Criteria A2.3, A2.4, A2.5 from latency-at-scale-and-correctness-plan-2026-08-26.md:
- A2.3: Multi-valued non-collision (possession, preference, daily_practice return fact_key=None, no erroneous overwriting)
- A2.4: Genuine single-valued supersession (lives_in, occupation auto-key and supersede old rows with valid_to)
- A2.5: Explicit fact_key via metadata respected; Near-identical facts stay bounded / deduplicated
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.memory_service import (
    MemoryService,
    _derive_fact_key,
    _SINGLE_VALUED_FACT_KEY_PATTERNS,
)


# ---------------------------------------------------------------------------
# In-Memory Mock Supabase Client for State Tracking & Bi-Temporal Invariants
# ---------------------------------------------------------------------------


class _MockResponse:
    def __init__(self, data: list[dict[str, Any]], count: Optional[int] = None) -> None:
        self.data = data
        self.count = count if count is not None else len(data)


class _MockTableQuery:
    def __init__(self, store: list[dict[str, Any]], table_name: str) -> None:
        self._store = store
        self._table_name = table_name
        self._eq_filters: dict[str, Any] = {}
        self._null_filters: list[str] = []
        self._in_filters: dict[str, list[Any]] = {}
        self._pending_insert: list[dict[str, Any]] | dict[str, Any] | None = None
        self._pending_update: dict[str, Any] | None = None
        self._is_delete = False
        self._order_by: Optional[str] = None
        self._order_desc = False
        self._range_start: Optional[int] = None
        self._range_end: Optional[int] = None
        self._limit_n: Optional[int] = None
        self._count_mode: Optional[str] = None

    def select(self, _cols: str = "*", count: Optional[str] = None) -> _MockTableQuery:
        self._count_mode = count
        return self

    def insert(self, data: dict[str, Any] | list[dict[str, Any]]) -> _MockTableQuery:
        self._pending_insert = data
        return self

    def update(self, data: dict[str, Any]) -> _MockTableQuery:
        self._pending_update = data
        return self

    def delete(self) -> _MockTableQuery:
        self._is_delete = True
        return self

    def upsert(self, data: dict[str, Any], on_conflict: Optional[str] = None) -> _MockTableQuery:
        self._pending_insert = data
        return self

    def eq(self, col: str, val: Any) -> _MockTableQuery:
        self._eq_filters[col] = val
        return self

    def is_(self, col: str, val: Any) -> _MockTableQuery:
        if val == "null" or val is None:
            self._null_filters.append(col)
        return self

    def in_(self, col: str, vals: list[Any]) -> _MockTableQuery:
        self._in_filters[col] = list(vals)
        return self

    def order(self, col: str, desc: bool = False) -> _MockTableQuery:
        self._order_by = col
        self._order_desc = desc
        return self

    def range(self, start: int, end: int) -> _MockTableQuery:
        self._range_start = start
        self._range_end = end
        return self

    def limit(self, n: int) -> _MockTableQuery:
        self._limit_n = n
        return self

    def _matches_filters(self, row: dict[str, Any]) -> bool:
        for col, val in self._eq_filters.items():
            if row.get(col) != val:
                return False
        for col in self._null_filters:
            if row.get(col) is not None:
                return False
        for col, vals in self._in_filters.items():
            if row.get(col) not in vals:
                return False
        return True

    def execute(self) -> _MockResponse:
        # 1. Insert
        if self._pending_insert is not None:
            items = (
                self._pending_insert
                if isinstance(self._pending_insert, list)
                else [self._pending_insert]
            )
            inserted_rows = []
            for item in items:
                row = dict(item)
                row.setdefault("id", f"mem-{uuid.uuid4().hex[:8]}")
                row.setdefault("created_at", "2026-08-26T12:00:00+00:00")
                row.setdefault("valid_to", None)
                self._store.append(row)
                inserted_rows.append(row)
            return _MockResponse(inserted_rows)

        # 2. Update
        if self._pending_update is not None:
            updated_rows = []
            for row in self._store:
                if self._matches_filters(row):
                    row.update(self._pending_update)
                    updated_rows.append(row)
            return _MockResponse(updated_rows)

        # 3. Delete
        if self._is_delete:
            deleted_rows = []
            remaining = []
            for row in self._store:
                if self._matches_filters(row):
                    deleted_rows.append(row)
                else:
                    remaining.append(row)
            self._store.clear()
            self._store.extend(remaining)
            return _MockResponse(deleted_rows)

        # 4. Select
        matching = [row for row in self._store if self._matches_filters(row)]
        count_val = len(matching)

        if self._order_by:
            matching = sorted(
                matching,
                key=lambda r: r.get(self._order_by, ""),
                reverse=self._order_desc,
            )

        if self._range_start is not None and self._range_end is not None:
            matching = matching[self._range_start : self._range_end + 1]
        elif self._limit_n is not None:
            matching = matching[: self._limit_n]

        return _MockResponse(matching, count=count_val)


class _MockSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "guru_memories": [],
            "guru_core_memory": [],
            "guru_session_summaries": [],
        }

    def table(self, table_name: str) -> _MockTableQuery:
        if table_name not in self.tables:
            self.tables[table_name] = []
        return _MockTableQuery(self.tables[table_name], table_name)

    def rpc(self, _func_name: str, _params: dict[str, Any]) -> Any:
        mock = MagicMock()
        mock.execute.return_value = _MockResponse([])
        return mock


class _MockEmbeddingService:
    def encode_single_full(self, _content: str) -> dict[str, Any]:
        return {"dense": [0.1] * 1024}


# ---------------------------------------------------------------------------
# Unit Tests for _derive_fact_key
# ---------------------------------------------------------------------------


class TestDeriveFactKey:
    """Validate fact key derivation logic and single-valued boundary rules."""

    def test_single_valued_patterns_only_include_lives_in_and_occupation(self):
        relations = [rel for rel, _ in _SINGLE_VALUED_FACT_KEY_PATTERNS]
        assert relations == ["lives_in", "occupation"]
        assert "possession" not in relations
        assert "preference" not in relations
        assert "daily_practice" not in relations

    def test_lives_in_phrases_derive_consistent_key(self):
        assert _derive_fact_key("I live in Delhi") == "user:lives_in"
        assert _derive_fact_key("I moved to Chennai") == "user:lives_in"
        assert _derive_fact_key("Seeker lives in San Francisco") == "user:lives_in"
        assert _derive_fact_key("User moved to London") == "user:lives_in"
        assert _derive_fact_key("We live at Rishikesh Ashram") == "user:lives_in"

    def test_occupation_phrases_derive_consistent_key(self):
        assert _derive_fact_key("I work as an engineer") == "user:occupation"
        assert _derive_fact_key("I work as a designer") == "user:occupation"
        assert _derive_fact_key("I study computer science") == "user:occupation"
        assert _derive_fact_key("Seeker works in healthcare") == "user:occupation"

    def test_multi_valued_relations_return_none(self):
        # Possessions / symptoms / relationships
        assert _derive_fact_key("I have anxiety about work") is None
        assert _derive_fact_key("I have a daughter") is None
        assert _derive_fact_key("I own a meditation cushion") is None
        assert _derive_fact_key("Seeker has chronic back pain") is None

        # Preferences
        assert _derive_fact_key("I prefer morning meditation") is None
        assert _derive_fact_key("I like silent contemplation") is None
        assert _derive_fact_key("I love walking in nature") is None

        # Daily practices
        assert _derive_fact_key("I practice Soul Sync daily") is None
        assert _derive_fact_key("I do pranayama breathing") is None

    def test_explicit_fact_key_via_metadata_is_respected(self):
        assert (
            _derive_fact_key("Random text", metadata={"fact_key": "user:custom"}) == "user:custom"
        )
        assert (
            _derive_fact_key("I have anxiety", metadata={"fact_key": "user:mental_state"})
            == "user:mental_state"
        )
        assert (
            _derive_fact_key(
                "I like tea", metadata={"fact_key": "user:preference:beverage"}
            )
            == "user:preference:beverage"
        )

    def test_explicit_fact_key_sanitization(self):
        assert (
            _derive_fact_key("test", metadata={"fact_key": "User:Meditation Routine #1"})
            == "user:meditation_routine_1"
        )
        assert (
            _derive_fact_key("test", metadata={"fact_key": "   custom_key_123   "})
            == "custom_key_123"
        )

    def test_candidate_from_metadata_claim_or_insight(self):
        assert _derive_fact_key("", metadata={"claim": "Seeker lives in Mumbai"}) == "user:lives_in"
        assert (
            _derive_fact_key("", metadata={"insight": "Seeker works as teacher"})
            == "user:occupation"
        )

    def test_non_string_returns_none(self):
        assert _derive_fact_key(None) is None  # type: ignore
        assert _derive_fact_key(12345) is None  # type: ignore


# ---------------------------------------------------------------------------
# Bi-Temporal Supersession & Multi-Valued Non-Collision End-to-End Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMemorySupersessionSuite:
    """Verifies Criteria A2.3, A2.4, and A2.5 with full round-trip MemoryService."""

    async def test_criterion_a2_3_multi_valued_non_collision(self):
        """Criterion A2.3: Storing multi-valued facts ("I have anxiety about work" followed

        by "I have a daughter") keeps both active (neither supersedes the other, valid_to is None).
        """
        client = _MockSupabaseClient()
        service = MemoryService(
            supabase_client=client,
            embedding_service=_MockEmbeddingService(),
        )
        user_id = "00000000-0000-0000-0000-000000000001"

        # 1. Store first multi-valued memory
        res1 = await service.add_explicit(
            user_id=user_id,
            content="I have anxiety about work",
            is_core=False,
            run_compaction=False,
        )
        assert res1 and res1["id"]

        # 2. Store second multi-valued memory
        res2 = await service.add_explicit(
            user_id=user_id,
            content="I have a daughter",
            is_core=False,
            run_compaction=False,
        )
        assert res2 and res2["id"]

        # 3. Verify in store: both rows exist and neither has valid_to set
        rows = client.tables["guru_memories"]
        assert len(rows) == 2

        row1 = next(r for r in rows if r["id"] == res1["id"])
        row2 = next(r for r in rows if r["id"] == res2["id"])

        assert row1["content"] == "I have anxiety about work"
        assert row1.get("fact_key") is None
        assert row1.get("valid_to") is None

        assert row2["content"] == "I have a daughter"
        assert row2.get("fact_key") is None
        assert row2.get("valid_to") is None

        # 4. List memories: both are returned as active
        listed = await service.list_memories(user_id=user_id)
        assert listed["total"] == 2
        contents = [m["content"] for m in listed["memories"]]
        assert "I have anxiety about work" in contents
        assert "I have a daughter" in contents

    async def test_criterion_a2_4_location_single_valued_supersession(self):
        """Criterion A2.4: Storing "I live in Delhi" followed by "I moved to Chennai"

        supersedes the old row (valid_to is set on the old row, new row is active).
        """
        client = _MockSupabaseClient()
        service = MemoryService(
            supabase_client=client,
            embedding_service=_MockEmbeddingService(),
        )
        user_id = "00000000-0000-0000-0000-000000000002"

        # 1. Add first location
        res1 = await service.add_explicit(
            user_id=user_id,
            content="I live in Delhi",
            is_core=False,
            run_compaction=False,
        )
        assert res1 and res1["id"]
        row1_id = res1["id"]

        # Verify initial state: row1 is active with fact_key user:lives_in
        rows = client.tables["guru_memories"]
        assert len(rows) == 1
        assert rows[0]["fact_key"] == "user:lives_in"
        assert rows[0]["valid_to"] is None
        assert rows[0]["valid_from"] is not None

        # 2. Add second location (contradicts / supersedes previous location)
        res2 = await service.add_explicit(
            user_id=user_id,
            content="I moved to Chennai",
            is_core=False,
            run_compaction=False,
        )
        assert res2 and res2["id"]
        row2_id = res2["id"]

        # Verify both rows in database: old row has valid_to set, new row is active
        assert len(rows) == 2
        old_row = next(r for r in rows if r["id"] == row1_id)
        new_row = next(r for r in rows if r["id"] == row2_id)

        assert old_row["content"] == "I live in Delhi"
        assert old_row["fact_key"] == "user:lives_in"
        assert old_row["valid_to"] is not None
        assert old_row["valid_to"] == new_row["valid_from"]

        assert new_row["content"] == "I moved to Chennai"
        assert new_row["fact_key"] == "user:lives_in"
        assert new_row["valid_to"] is None

        # 3. Verify list_memories only returns active rows (valid_to is null)
        listed = await service.list_memories(user_id=user_id)
        assert listed["total"] == 1
        assert len(listed["memories"]) == 1
        assert listed["memories"][0]["content"] == "I moved to Chennai"
        assert listed["memories"][0]["valid_to"] is None

    async def test_criterion_a2_4_occupation_single_valued_supersession(self):
        """Criterion A2.4: Storing "I work as an engineer" followed by "I work as a designer"

        supersedes the old row (valid_to is set on old row, new row is active).
        """
        client = _MockSupabaseClient()
        service = MemoryService(
            supabase_client=client,
            embedding_service=_MockEmbeddingService(),
        )
        user_id = "00000000-0000-0000-0000-000000000003"

        # 1. Add engineer occupation
        res1 = await service.add_explicit(
            user_id=user_id,
            content="I work as an engineer",
            is_core=False,
            run_compaction=False,
        )
        # 2. Add designer occupation
        res2 = await service.add_explicit(
            user_id=user_id,
            content="I work as a designer",
            is_core=False,
            run_compaction=False,
        )

        rows = client.tables["guru_memories"]
        assert len(rows) == 2

        old_row = next(r for r in rows if r["id"] == res1["id"])
        new_row = next(r for r in rows if r["id"] == res2["id"])

        assert old_row["content"] == "I work as an engineer"
        assert old_row["fact_key"] == "user:occupation"
        assert old_row["valid_to"] is not None

        assert new_row["content"] == "I work as a designer"
        assert new_row["fact_key"] == "user:occupation"
        assert new_row["valid_to"] is None

        # Active view check
        listed = await service.list_memories(user_id=user_id)
        assert listed["total"] == 1
        assert listed["memories"][0]["content"] == "I work as a designer"

    async def test_criterion_a2_5_explicit_fact_key_via_metadata(self):
        """Criterion A2.5: Explicit fact_key via metadata (e.g.

        metadata={"fact_key": "user:custom"}) is respected and triggers supersession.
        """
        client = _MockSupabaseClient()
        service = MemoryService(
            supabase_client=client,
            embedding_service=_MockEmbeddingService(),
        )
        user_id = "00000000-0000-0000-0000-000000000004"

        # 1. Store memory with explicit fact_key
        res1 = await service.add_explicit(
            user_id=user_id,
            content="Current Spiritual Goal: Complete 21-Day Ekam Meditation",
            is_core=False,
            run_compaction=False,
            metadata={"fact_key": "user:primary_goal"},
        )

        # 2. Store updated goal with same explicit fact_key
        res2 = await service.add_explicit(
            user_id=user_id,
            content="Current Spiritual Goal: Daily Soul Sync and Seva",
            is_core=False,
            run_compaction=False,
            metadata={"fact_key": "user:primary_goal"},
        )

        rows = client.tables["guru_memories"]
        assert len(rows) == 2

        old_row = next(r for r in rows if r["id"] == res1["id"])
        new_row = next(r for r in rows if r["id"] == res2["id"])

        assert old_row["fact_key"] == "user:primary_goal"
        assert old_row["valid_to"] is not None
        assert old_row["valid_to"] == new_row["valid_from"]

        assert new_row["fact_key"] == "user:primary_goal"
        assert new_row["valid_to"] is None

        listed = await service.list_memories(user_id=user_id)
        assert listed["total"] == 1
        assert listed["memories"][0]["content"] == "Current Spiritual Goal: Daily Soul Sync and Seva"

    async def test_criterion_a2_5_repeated_supersessions_stay_bounded(self):
        """Criterion A2.5: Successive updates to a single-valued relation produce

        at most 1 active row, keeping active state strictly bounded.
        """
        client = _MockSupabaseClient()
        service = MemoryService(
            supabase_client=client,
            embedding_service=_MockEmbeddingService(),
        )
        user_id = "00000000-0000-0000-0000-000000000005"

        cities = ["Delhi", "Mumbai", "Bangalore", "Hyderabad", "Chennai"]
        for city in cities:
            await service.add_explicit(
                user_id=user_id,
                content=f"I live in {city}",
                is_core=False,
                run_compaction=False,
            )

        rows = client.tables["guru_memories"]
        assert len(rows) == 5

        # 4 previous cities are closed (valid_to is set)
        superseded = [r for r in rows if r["valid_to"] is not None]
        assert len(superseded) == 4

        # Exactly 1 active city
        active = [r for r in rows if r["valid_to"] is None]
        assert len(active) == 1
        assert active[0]["content"] == "I live in Chennai"

        # list_memories returns exactly 1 active record
        listed = await service.list_memories(user_id=user_id)
        assert listed["total"] == 1
        assert listed["memories"][0]["content"] == "I live in Chennai"

    async def test_criterion_a2_5_deduplication_and_compaction_boundedness(self, monkeypatch):
        """Criterion A2.5: Near-identical facts and high volume trigger compaction

        consolidating memories into a bounded set (<= 8 memories).
        """
        client = _MockSupabaseClient()
        service = MemoryService(
            supabase_client=client,
            embedding_service=_MockEmbeddingService(),
        )
        user_id = "00000000-0000-0000-0000-000000000006"

        # Mock LLM for compaction
        mock_client = AsyncMock()
        mock_completions = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"compacted_memories": ['
            '"Seeker practices daily morning meditation and breathing exercises", '
            '"Seeker is focused on overcoming work stress and finding peace", '
            '"Seeker feels deep gratitude for family connections"'
            "]}"
        )
        mock_completions.create.return_value = mock_response
        mock_client.chat = MagicMock()
        mock_client.chat.completions = mock_completions

        import openai

        class MockAsyncOpenAI:
            def __init__(self, *args, **kwargs):
                self.chat = mock_client.chat

        monkeypatch.setattr(openai, "AsyncOpenAI", MockAsyncOpenAI)
        monkeypatch.setattr("services.memory_service.settings.llm_provider", "openrouter")
        monkeypatch.setattr("services.memory_service.settings.openrouter_classify_model", "test-model")

        # Insert 16 episodic reflections to trigger compaction threshold (> 15)
        for i in range(16):
            await service.add_explicit(
                user_id=user_id,
                content=f"Reflection #{i}: I feel calm during meditation practice",
                is_core=False,
                run_compaction=(i == 15),  # Trigger compaction on 16th item
            )

        # Compaction replaces the 16 individual memories with the 3 consolidated memories
        rows = client.tables["guru_memories"]
        assert len(rows) == 3
        assert len(rows) <= 8
        assert rows[0]["content"] == "Seeker practices daily morning meditation and breathing exercises"

    async def test_anonymous_sessions_do_not_persist(self):
        """Anonymous sessions (e.g. anon:<session_id>) do not write to store."""
        client = _MockSupabaseClient()
        service = MemoryService(
            supabase_client=client,
            embedding_service=_MockEmbeddingService(),
        )

        res = await service.add_explicit(
            user_id="anon:session-abc-123",
            content="I live in Delhi",
            is_core=False,
        )
        assert res == {}
        assert len(client.tables["guru_memories"]) == 0
