"""Canonical memory, live 2026-11-19.

1. Chat-extracted memories were written to Postgres but never vector-indexed
   (5 of 6 rows): only the REST create path indexed. The resolver now hands every
   inserted row to an injected indexer.
2. Lexical recall ran its Supabase queries one after another (2 lanes x up to 5
   terms); 2 of 3 signed-in recalls hit the 2 s canonical_memory_timeout. The
   queries now run concurrently.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from services.canonical_memory.judge import DecisionType
from services.canonical_memory.resolver import MemoryResolver
from services.canonical_memory.retriever import CanonicalMemoryRetriever
from tests.test_canonical_memory_resolution import (
    MockSupabase,
    _make_candidate,
    _make_decision,
)


@pytest.mark.asyncio
async def test_resolver_indexes_every_inserted_memory() -> None:
    indexed: list[dict] = []

    async def indexer(row: dict) -> None:
        indexed.append(row)

    resolver = MemoryResolver(MockSupabase(), vector_indexer=indexer)
    result = await resolver.resolve(
        _make_decision(candidate=_make_candidate(), decision=DecisionType.CREATE),
        user_id="user-001",
    )
    assert result.action == "created"
    assert [r["id"] for r in indexed] == [result.memory_id]
    assert indexed[0]["statement"] == "User prefers concise answers."


@pytest.mark.asyncio
async def test_index_failure_does_not_undo_saved_memory() -> None:
    async def broken(row: dict) -> None:
        raise RuntimeError("qdrant down")

    db = MockSupabase()
    result = await MemoryResolver(db, vector_indexer=broken).resolve(
        _make_decision(candidate=_make_candidate(), decision=DecisionType.CREATE),
        user_id="user-001",
    )
    assert result.action == "created"
    assert result.memory_id in db.memories


@pytest.mark.asyncio
async def test_superseded_memory_found_by_vector_is_not_retrieved() -> None:
    """Indexing every insert means a superseded row's vector still matches;
    its true status comes from hydration and must exclude it."""
    retriever = CanonicalMemoryRetriever(
        supabase_client=None, vector_index=None, embedding_service=None
    )

    async def semantic(*_a):
        return [{"id": "old", "score": 0.9}, {"id": "new", "score": 0.8}]

    async def lexical(*_a):
        return []

    async def hydrate(_u, ids, _t):
        rows = {
            "old": {"id": "old", "statement": "Favourite colour is blue", "status": "superseded"},
            "new": {"id": "new", "statement": "Favourite colour is green", "status": "active"},
        }
        return [rows[i] for i in ids]

    async def touch(*_a):
        return None

    retriever._semantic_search = semantic
    retriever._lexical_search = lexical
    retriever._hydrate_memories = hydrate
    retriever._update_last_used = touch
    result = await retriever.retrieve(user_id="u", query="favourite colour", tenant_id="oneness")
    assert [m.statement for m in result.memories] == ["Favourite colour is green"]


class _SlowQuery:
    """PostgREST builder stub whose execute() costs one simulated round trip."""

    DELAY_S = 0.2

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        time.sleep(self.DELAY_S)
        return SimpleNamespace(data=[])


@pytest.mark.asyncio
async def test_lexical_queries_run_concurrently() -> None:
    db = SimpleNamespace(table=lambda _name: _SlowQuery())
    retriever = CanonicalMemoryRetriever(
        supabase_client=db, vector_index=None, embedding_service=None
    )
    terms = ["anxiety", "mother", "career", "sleep", "anger"]
    retriever._extract_search_terms = lambda _q: terms
    start = time.monotonic()
    await retriever._lexical_search("u", "q", "oneness")
    elapsed = time.monotonic() - start
    sequential = 2 * len(terms) * _SlowQuery.DELAY_S  # 2.0 s
    assert elapsed < sequential / 2, f"lexical search took {elapsed:.2f}s"
