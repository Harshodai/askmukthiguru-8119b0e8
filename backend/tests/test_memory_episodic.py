"""Tests for EpisodicMemoryService — round-trip against a mocked supabase client.

No live Supabase required. Mirrors the conftest pattern (sys.path already
points at backend/ so 'services.*' and 'app.*' imports resolve).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from services.memory.episodic import EpisodicMemoryService


class _MockResp:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _MockTable:
    """Records calls and returns canned data for insert/select chains."""

    def __init__(self, store: list[dict], insert_data: list[dict]) -> None:
        self._store = store  # the table's current rows
        self._insert_data = insert_data  # rows returned by insert().execute()
        self._row: dict | None = None
        self._filters: dict = {}
        self._or_filter: str | None = None
        self._order_desc = False
        self._limit: int | None = None

    def insert(self, row: dict) -> _MockTable:
        self._row = row
        return self

    def select(self, *_args) -> _MockTable:
        return self

    def eq(self, col: str, val: str) -> _MockTable:
        self._filters[col] = val
        return self

    def or_(self, expr: str) -> _MockTable:
        self._or_filter = expr
        return self

    def order(self, _col: str, desc: bool = False) -> _MockTable:
        self._order_desc = desc
        return self

    def limit(self, n: int) -> _MockTable:
        self._limit = n
        return self

    def execute(self) -> _MockResp:
        if self._row is not None:
            # insert path: append to store and echo back inserted row
            row = dict(self._row)
            row.setdefault("id", "new-id")
            row.setdefault("created_at", "2026-06-30T00:00:00+00:00")
            # citations stored as json string, mirror real client behavior
            row["citations"] = self._row.get("citations", "[]")
            self._store.append(row)
            return _MockResp([row])
        # select path: filter by user_id, optional or_ substring on query/answer
        rows = [r for r in self._store if r.get("user_id") == self._filters.get("user_id")]
        if self._or_filter:
            # parse "query.ilike.%t%,answer.ilike.%t%" naively
            term = self._or_filter.split("ilike.")[-1].strip("%")
            rows = [
                r for r in rows
                if term in (r.get("query", "") + r.get("answer", ""))
            ]
        if self._order_desc:
            rows = sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _MockResp(list(rows))


class _MockClient:
    def __init__(self) -> None:
        self.store: list[dict] = []
        self.insert_data: list[dict] = []

    def table(self, _name: str) -> _MockTable:
        return _MockTable(self.store, self.insert_data)


@pytest.mark.unit
def test_log_and_retrieve_recent_round_trip() -> None:
    client = _MockClient()
    svc = EpisodicMemoryService(supabase_client=client)

    inserted = asyncio.run(
        svc.log_episode("u1", "What is a beautiful state?", "It is calm.", ["url1"], "QUERY")
    )
    assert inserted is not None
    assert inserted["query"] == "What is a beautiful state?"

    rows = asyncio.run(svc.retrieve_recent("u1", limit=10))
    assert len(rows) == 1
    assert rows[0]["answer"] == "It is calm."


@pytest.mark.unit
def test_search_matches_query_or_answer() -> None:
    client = _MockClient()
    svc = EpisodicMemoryService(supabase_client=client)

    asyncio.run(svc.log_episode("u1", "meditation steps", "breathe slowly", [], "MEDITATION"))
    asyncio.run(svc.log_episode("u1", "other question", "unrelated", [], "CASUAL"))

    hits = asyncio.run(svc.search("u1", "meditation"))
    assert len(hits) == 1
    assert hits[0]["query"] == "meditation steps"

    hits2 = asyncio.run(svc.search("u1", "breathe"))
    assert len(hits2) == 1
    assert hits2[0]["answer"] == "breathe slowly"


@pytest.mark.unit
def test_anonymous_and_empty_inputs_are_no_op() -> None:
    client = _MockClient()
    svc = EpisodicMemoryService(supabase_client=client)

    assert asyncio.run(svc.log_episode("anonymous", "q", "a")) is None
    assert asyncio.run(svc.log_episode("u1", "", "a")) is None
    assert asyncio.run(svc.retrieve_recent("anonymous")) == []
    assert asyncio.run(svc.search("u1", "")) == []
    assert client.store == []  # nothing written


@pytest.mark.unit
def test_no_client_degrades_gracefully() -> None:
    svc = EpisodicMemoryService(supabase_client=None)
    assert not svc.available
    assert asyncio.run(svc.log_episode("u1", "q", "a")) is None
    assert asyncio.run(svc.retrieve_recent("u1")) == []
    assert asyncio.run(svc.search("u1", "q")) == []


@pytest.mark.unit
def test_citations_round_trip_as_json() -> None:
    client = _MockClient()
    svc = EpisodicMemoryService(supabase_client=client)
    asyncio.run(svc.log_episode("u1", "q", "a", [{"doc": "x", "quote": "y"}], "QUERY"))
    rows = asyncio.run(svc.retrieve_recent("u1"))
    # stored row carries citations as the json string the service wrote
    assert json.loads(rows[0]["citations"]) == [{"doc": "x", "quote": "y"}]