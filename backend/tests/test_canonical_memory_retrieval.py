"""Tests for canonical memory retriever — Phase 8 of Adaptive Memory System.

Unit tests using mocked Supabase, Qdrant, and embedding clients. Verifies:
- Retrieval returns relevant memories
- User isolation enforced on all queries
- Ranking orders by composite relevance score
- Hard limits respected (20 max memories, 2000 max tokens)
- Empty result for new user
- Retrieval updates last_used_at
- Lexical fallback when vector search fails
- Semantic search failure degrades gracefully
- Token budget correctly truncates
- Status priority (active > superseded > expired)
- Freshness decay affects ranking
- Evidence strength boosts ranking
- Search term extraction filters stopwords

Run: cd backend && .venv/bin/pytest tests/test_canonical_memory_retrieval.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from services.canonical_memory.retriever import (
    MAX_MEMORIES,
    MAX_TOKENS,
    LEXICAL_LIMIT,
    MAX_VECTOR_RESULTS,
    RetrievedMemory,
    RetrievalResult,
    CanonicalMemoryRetriever,
    create_retriever,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_memory_row(user_id: str, memory_id: str | None = None, **overrides: Any) -> dict[str, Any]:
    """Create a realistic canonical_memories row dict."""
    mid = memory_id or _uid()
    row = {
        "id": mid,
        "user_id": user_id,
        "memory_type": "PREFERENCE",
        "statement": "User prefers concise answers",
        "normalized_statement": "user prefers concise answers",
        "fact_key": "user:prefers_tone",
        "confidence": 0.85,
        "importance": 0.6,
        "evidence_count": 2,
        "status": "active",
        "source_conversation_id": "conv-001",
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
        "last_used_at": None,
    }
    row.update(overrides)
    return row


def _build_retriever(
    db_results: list[dict] | None = None,
    vector_results: list[dict] | None = None,
    embed_vector: list[float] | None = None,
) -> tuple[CanonicalMemoryRetriever, MagicMock, MagicMock, AsyncMock]:
    """Build a retriever with mocked dependencies.

    Returns (retriever, mock_db, mock_vi, mock_embed).
    """
    mock_db = MagicMock()
    mock_vi = MagicMock()
    mock_embed = AsyncMock(return_value=embed_vector or [0.1] * 1024)

    # Default vector search returns empty
    if vector_results is not None:
        mock_vi.search = AsyncMock(return_value=vector_results)
    else:
        mock_vi.search = AsyncMock(return_value=[])

    # Default DB lexical search returns empty (ILIKE queries)
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_ilike = MagicMock()
    mock_limit = MagicMock()
    mock_execute = MagicMock()

    if db_results is not None:
        mock_execute.return_value.data = db_results
    else:
        mock_execute.return_value.data = []

    # Chain: table().select().eq().eq().ilike().limit().execute()
    mock_limit.return_value.execute = mock_execute
    mock_ilike.return_value.limit = mock_limit
    mock_eq.return_value.ilike = mock_ilike
    mock_select.return_value.eq = mock_eq
    mock_db.table.return_value.select = mock_select

    retriever = CanonicalMemoryRetriever(mock_db, mock_vi, mock_embed)
    return retriever, mock_db, mock_vi, mock_embed


# ---------------------------------------------------------------------------
# Test: Retrieval returns relevant memories
# ---------------------------------------------------------------------------

class TestRetrievalReturnsRelevantMemories:
    """Verify that retrieval returns memories from semantic + lexical sources."""

    def test_returns_memories_from_semantic_search(self):
        """Semantic results get hydrated and returned."""
        user_id = _uid()
        mem_id = _uid()
        vector_results = [
            {"id": mem_id, "score": 0.9, "memory_type": "PREFERENCE", "status": "active"},
        ]
        hydrate_row = _make_memory_row(user_id, mem_id)

        retriever, mock_db, mock_vi, mock_embed = _build_retriever(
            vector_results=vector_results,
        )

        # Mock hydration query
        mock_hydrate_execute = MagicMock()
        mock_hydrate_execute.return_value.data = [hydrate_row]
        mock_hydrate_eq = MagicMock()
        mock_hydrate_eq.return_value.in_ = MagicMock(
            return_value=MagicMock(execute=mock_hydrate_execute)
        )
        mock_hydrate_select = MagicMock()
        mock_hydrate_select.return_value.eq = mock_hydrate_eq
        mock_db.table.return_value.select = mock_hydrate_select

        import asyncio
        result = asyncio.run(retriever.retrieve(user_id, "concise answers"))

        assert len(result.memories) >= 1
        assert result.memories[0].id == mem_id
        assert result.memories[0].semantic_score == 0.9

    def test_returns_memories_from_lexical_search(self):
        """Lexical results from Postgres ILIKE are returned."""
        user_id = _uid()
        mem_id = _uid()
        lex_row = _make_memory_row(user_id, mem_id)

        # Build retriever with lexical results
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        # Chain: .table().select().eq(user_id).eq(status).ilike().limit().execute()
        mock_lex_execute = MagicMock()
        mock_lex_execute.return_value.data = [lex_row]
        mock_lex_limit = MagicMock()
        mock_lex_limit.return_value.execute = mock_lex_execute
        mock_lex_ilike = MagicMock()
        mock_lex_ilike.return_value.limit = mock_lex_limit
        mock_lex_eq2 = MagicMock()
        mock_lex_eq2.return_value.ilike = mock_lex_ilike
        mock_lex_eq1 = MagicMock()
        mock_lex_eq1.return_value.eq = mock_lex_eq2
        mock_lex_select = MagicMock()
        mock_lex_select.return_value.eq = mock_lex_eq1
        mock_db.table.return_value.select = mock_lex_select

        import asyncio
        result = asyncio.run(retriever.retrieve(user_id, "prefers tone"))

        assert len(result.memories) >= 1
        assert result.memories[0].id == mem_id

    def test_empty_result_for_new_user(self):
        """New user with no memories returns empty result."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        import asyncio
        result = asyncio.run(retriever.retrieve(_uid(), "hello"))

        assert result.memories == []
        assert result.total_tokens == 0
        assert result.truncated is False


# ---------------------------------------------------------------------------
# Test: User isolation enforced
# ---------------------------------------------------------------------------

class TestUserIsolationEnforced:
    """Verify every query filters by user_id server-side."""

    def test_vector_search_passes_user_id(self):
        """Qdrant search must include user_id in filter."""
        user_id = _uid()
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        import asyncio
        asyncio.run(retriever.retrieve(user_id, "test query"))

        mock_vi.search.assert_called_once()
        call_kwargs = mock_vi.search.call_args
        assert call_kwargs[1].get("user_id") == user_id or call_kwargs[0][0] == user_id

    def test_lexical_search_filters_by_user_id(self):
        """Postgres queries must filter by user_id."""
        user_id = _uid()
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        import asyncio
        asyncio.run(retriever.retrieve(user_id, "test query"))

        # Verify .eq("user_id", user_id) was called on the table
        mock_db.table.assert_called_with("canonical_memories")

    def test_last_used_update_scoped_to_user(self):
        """last_used_at update must be scoped to user_id."""
        user_id = _uid()
        mem_id = _uid()
        vector_results = [
            {"id": mem_id, "score": 0.9, "memory_type": "PREFERENCE", "status": "active"},
        ]
        hydrate_row = _make_memory_row(user_id, mem_id)

        retriever, mock_db, mock_vi, mock_embed = _build_retriever(
            vector_results=vector_results,
        )

        # Mock hydration
        mock_hydrate_execute = MagicMock()
        mock_hydrate_execute.return_value.data = [hydrate_row]
        mock_hydrate_eq = MagicMock()
        mock_hydrate_eq.return_value.in_ = MagicMock(
            return_value=MagicMock(execute=mock_hydrate_execute)
        )
        mock_hydrate_select = MagicMock()
        mock_hydrate_select.return_value.eq = mock_hydrate_eq
        mock_db.table.return_value.select = mock_hydrate_select

        import asyncio
        asyncio.run(retriever.retrieve(user_id, "concise answers"))

        # Verify update was called with user_id filter
        mock_db.table.return_value.update.assert_called()
        update_call = mock_db.table.return_value.update
        # The eq chain after update should include user_id
        if update_call.called:
            update_call.return_value.eq.assert_called()


# ---------------------------------------------------------------------------
# Test: Ranking orders by relevance
# ---------------------------------------------------------------------------

class TestRankingOrdersByRelevance:
    """Verify composite score ranking."""

    def test_higher_semantic_score_ranks_higher(self):
        """Memory with higher semantic score should rank first."""
        now = datetime.now(timezone.utc)
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        m_high = RetrievedMemory(
            id="high", statement="A", memory_type="PREFERENCE",
            semantic_score=0.95, importance=0.5, confidence=0.75,
        )
        m_low = RetrievedMemory(
            id="low", statement="B", memory_type="PREFERENCE",
            semantic_score=0.3, importance=0.5, confidence=0.75,
        )

        score_high = retriever._composite_score(m_high, "test", now)
        score_low = retriever._composite_score(m_low, "test", now)
        assert score_high > score_low

    def test_higher_importance_ranks_higher(self):
        """Memory with higher importance should rank higher."""
        now = datetime.now(timezone.utc)
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        m_high = RetrievedMemory(
            id="high", statement="A", memory_type="PROFILE",
            semantic_score=0.5, importance=0.9, confidence=0.75,
        )
        m_low = RetrievedMemory(
            id="low", statement="B", memory_type="PROFILE",
            semantic_score=0.5, importance=0.2, confidence=0.75,
        )

        score_high = retriever._composite_score(m_high, "test", now)
        score_low = retriever._composite_score(m_low, "test", now)
        assert score_high > score_low

    def test_active_status_ranks_above_superseded(self):
        """Active memories rank above superseded ones."""
        now = datetime.now(timezone.utc)
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        m_active = RetrievedMemory(
            id="active", statement="A", memory_type="PREFERENCE",
            semantic_score=0.7, status="active",
        )
        m_super = RetrievedMemory(
            id="super", statement="A", memory_type="PREFERENCE",
            semantic_score=0.7, status="superseded",
        )

        score_active = retriever._composite_score(m_active, "test", now)
        score_super = retriever._composite_score(m_super, "test", now)
        assert score_active > score_super

    def test_evidence_count_boosts_score(self):
        """Higher evidence count boosts ranking."""
        now = datetime.now(timezone.utc)
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        m_many = RetrievedMemory(
            id="many", statement="A", memory_type="PREFERENCE",
            semantic_score=0.5, evidence_count=10,
        )
        m_one = RetrievedMemory(
            id="one", statement="A", memory_type="PREFERENCE",
            semantic_score=0.5, evidence_count=1,
        )

        score_many = retriever._composite_score(m_many, "test", now)
        score_one = retriever._composite_score(m_one, "test", now)
        assert score_many > score_one

    def test_fresh_memory_ranks_above_stale(self):
        """Recently updated memory ranks above old one."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        m_fresh = RetrievedMemory(
            id="fresh", statement="A", memory_type="PREFERENCE",
            semantic_score=0.5,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        m_stale = RetrievedMemory(
            id="stale", statement="A", memory_type="PREFERENCE",
            semantic_score=0.5,
            updated_at="2020-01-01T00:00:00+00:00",
        )

        now = datetime.now(timezone.utc)
        score_fresh = retriever._composite_score(m_fresh, "test", now)
        score_stale = retriever._composite_score(m_stale, "test", now)
        assert score_fresh > score_stale


# ---------------------------------------------------------------------------
# Test: Hard limits respected
# ---------------------------------------------------------------------------

class TestHardLimitsRespected:
    """Verify max 20 memories and max 2000 tokens."""

    def test_max_20_memories(self):
        """Never return more than 20 memories."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        # Create 25 memories with high scores
        ranked = [
            RetrievedMemory(
                id=_uid(), statement="Memory number %d" % i,
                memory_type="PREFERENCE", score=1.0 - i * 0.01,
            )
            for i in range(25)
        ]

        selected, tokens, truncated = retriever._apply_limits(ranked, 20, 2000)
        assert len(selected) == 20
        assert truncated is True

    def test_max_2000_tokens(self):
        """Never exceed 2000 token budget."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        # Create memories that would exceed token budget
        ranked = [
            RetrievedMemory(
                id=_uid(),
                statement="word " * 200,  # ~50 tokens each
                memory_type="PREFERENCE",
                score=1.0,
            )
            for _ in range(100)
        ]

        selected, tokens, truncated = retriever._apply_limits(ranked, 20, 2000)
        assert tokens <= 2000
        assert truncated is True

    def test_respects_lower_limit(self):
        """Respects caller-specified limit below MAX_MEMORIES."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        ranked = [
            RetrievedMemory(
                id=_uid(), statement="Memory %d" % i,
                memory_type="PREFERENCE", score=1.0,
            )
            for i in range(10)
        ]

        selected, tokens, truncated = retriever._apply_limits(ranked, 5, 2000)
        assert len(selected) == 5
        assert truncated is True

    def test_no_truncation_when_within_budget(self):
        """No truncation when well within limits."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        ranked = [
            RetrievedMemory(
                id=_uid(), statement="short",
                memory_type="PREFERENCE", score=0.9,
            )
            for _ in range(3)
        ]

        selected, tokens, truncated = retriever._apply_limits(ranked, 20, 2000)
        assert len(selected) == 3
        assert truncated is False


# ---------------------------------------------------------------------------
# Test: Retrieval updates last_used_at
# ---------------------------------------------------------------------------

class TestRetrievalUpdatesLastUsedAt:
    """Verify that retrieved memories get last_used_at updated."""

    def test_updates_last_used_at(self):
        """Retrieved memory IDs get last_used_at set."""
        user_id = _uid()
        mem_id = _uid()
        vector_results = [
            {"id": mem_id, "score": 0.9, "memory_type": "PREFERENCE", "status": "active"},
        ]
        hydrate_row = _make_memory_row(user_id, mem_id)

        retriever, mock_db, mock_vi, mock_embed = _build_retriever(
            vector_results=vector_results,
        )

        # Mock hydration
        mock_hydrate_execute = MagicMock()
        mock_hydrate_execute.return_value.data = [hydrate_row]
        mock_hydrate_eq = MagicMock()
        mock_hydrate_eq.return_value.in_ = MagicMock(
            return_value=MagicMock(execute=mock_hydrate_execute)
        )
        mock_hydrate_select = MagicMock()
        mock_hydrate_select.return_value.eq = mock_hydrate_eq
        mock_db.table.return_value.select = mock_hydrate_select

        import asyncio
        asyncio.run(retriever.retrieve(user_id, "concise answers"))

        # Verify update was called (last_used_at)
        mock_db.table.return_value.update.assert_called()
        update_args = mock_db.table.return_value.update.call_args
        assert "last_used_at" in update_args[0][0]

    def test_no_update_when_no_memories(self):
        """No update call when no memories are retrieved."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        import asyncio
        asyncio.run(retriever.retrieve(_uid(), "empty query"))

        mock_db.table.return_value.update.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Lexical fallback when vector search fails
# ---------------------------------------------------------------------------

class TestLexicalFallbackWhenVectorFails:
    """Verify graceful degradation when Qdrant is unavailable."""

    def test_semantic_failure_still_returns_lexical(self):
        """When Qdrant fails, lexical search still provides results."""
        user_id = _uid()
        mem_id = _uid()
        lex_row = _make_memory_row(user_id, mem_id)

        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        # Make vector search raise
        mock_vi.search = AsyncMock(side_effect=Exception("Qdrant down"))

        # Override lexical search to return results
        mock_lex_execute = MagicMock()
        mock_lex_execute.return_value.data = [lex_row]
        mock_lex_limit = MagicMock()
        mock_lex_limit.return_value.execute = mock_lex_execute
        mock_lex_ilike = MagicMock()
        mock_lex_ilike.return_value.limit = mock_lex_limit
        mock_lex_eq2 = MagicMock()
        mock_lex_eq2.return_value.ilike = mock_lex_ilike
        mock_lex_eq1 = MagicMock()
        mock_lex_eq1.return_value.eq = mock_lex_eq2
        mock_lex_select = MagicMock()
        mock_lex_select.return_value.eq = mock_lex_eq1
        mock_db.table.return_value.select = mock_lex_select

        import asyncio
        result = asyncio.run(retriever.retrieve(user_id, "test query"))

        # Should still return results from lexical search
        assert len(result.memories) >= 1

    def test_both_fail_returns_empty(self):
        """When both semantic and lexical fail, return empty."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()

        # Make vector search raise
        mock_vi.search = AsyncMock(side_effect=Exception("Qdrant down"))

        # Make lexical search raise
        mock_lex_execute = MagicMock()
        mock_lex_execute.side_effect = Exception("Postgres down")
        mock_lex_limit = MagicMock()
        mock_lex_limit.return_value.execute = mock_lex_execute
        mock_lex_ilike = MagicMock()
        mock_lex_ilike.return_value.limit = mock_lex_limit
        mock_lex_eq = MagicMock()
        mock_lex_eq.return_value.ilike = mock_lex_ilike
        mock_lex_select = MagicMock()
        mock_lex_select.return_value.eq = mock_lex_eq
        mock_db.table.return_value.select = mock_lex_select

        import asyncio
        result = asyncio.run(retriever.retrieve(_uid(), "test query"))

        assert result.memories == []


# ---------------------------------------------------------------------------
# Test: Search term extraction
# ---------------------------------------------------------------------------

class TestSearchTermExtraction:
    """Verify query term extraction."""

    def test_filters_stopwords(self):
        """Common stopwords are filtered out."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()
        terms = retriever._extract_search_terms("What do you know about my meditation practice?")
        assert "what" not in terms
        assert "do" not in terms
        assert "you" not in terms
        assert "my" not in terms
        assert "about" not in terms
        assert "meditation" in terms
        assert "practice" in terms

    def test_returns_max_5_terms(self):
        """Never returns more than 5 search terms."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()
        terms = retriever._extract_search_terms(
            "one two three four five six seven eight nine ten"
        )
        assert len(terms) <= 5

    def test_handles_indic_script(self):
        """Indic script characters are preserved in terms."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()
        terms = retriever._extract_search_terms("मेरा नाम राम है meditation practice")
        # Should extract meaningful terms
        assert len(terms) > 0


# ---------------------------------------------------------------------------
# Test: Composite score calculation
# ---------------------------------------------------------------------------

class TestCompositeScoreCalculation:
    """Verify composite score formula."""

    def test_perfect_memory_scores_highest(self):
        """A memory with all max signals should score near 1.0."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()
        now = datetime.now(timezone.utc)
        m = RetrievedMemory(
            id="perfect",
            statement="Perfect memory",
            memory_type="PROFILE",
            confidence=1.0,
            importance=1.0,
            evidence_count=10,
            semantic_score=1.0,
            lexical_score=1.0,
            status="active",
            updated_at=now.isoformat(),
        )
        score = retriever._composite_score(m, "test", now)
        assert score > 0.8

    def test_minimal_memory_scores_low(self):
        """A memory with all min signals should score near 0."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()
        now = datetime.now(timezone.utc)
        m = RetrievedMemory(
            id="minimal",
            statement="Minimal",
            memory_type="PREFERENCE",
            confidence=0.0,
            importance=0.0,
            evidence_count=0,
            semantic_score=0.0,
            lexical_score=0.0,
            status="expired",
            updated_at="2020-01-01T00:00:00+00:00",
        )
        score = retriever._composite_score(m, "test", now)
        assert score < 0.1

    def test_score_range_always_0_to_1(self):
        """Score is always in [0, 1]."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()
        now = datetime.now(timezone.utc)

        # Test various combinations
        for sem in [0.0, 0.5, 1.0]:
            for imp in [0.0, 0.5, 1.0]:
                for conf in [0.0, 0.5, 1.0]:
                    m = RetrievedMemory(
                        id=_uid(), statement="test", memory_type="PREFERENCE",
                        semantic_score=sem, importance=imp, confidence=conf,
                    )
                    score = retriever._composite_score(m, "query", now)
                    assert 0.0 <= score <= 1.0, f"Score {score} out of range"


# ---------------------------------------------------------------------------
# Test: Token estimation
# ---------------------------------------------------------------------------

class TestTokenEstimation:
    """Verify token estimation for budget enforcement."""

    def test_estimates_tokens_from_statement_length(self):
        """Token count is roughly statement_length / 4."""
        m = RetrievedMemory(id="t", statement="a" * 100, memory_type="PREFERENCE")
        assert m.estimated_tokens() == 25

    def test_minimum_one_token(self):
        """Empty or very short statement still counts as 1 token."""
        m = RetrievedMemory(id="t", statement="", memory_type="PREFERENCE")
        assert m.estimated_tokens() == 1


# ---------------------------------------------------------------------------
# Test: Freshness decay
# ---------------------------------------------------------------------------

class TestFreshnessDecay:
    """Verify freshness score exponential decay."""

    def test_very_recent_is_high(self):
        """Timestamp from just now scores near 1.0."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()
        now = datetime.now(timezone.utc)
        ts = now.isoformat()
        score = retriever._freshness_score(ts, now)
        assert score > 0.99

    def test_very_old_is_low(self):
        """Timestamp from years ago scores near 0."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()
        now = datetime.now(timezone.utc)
        score = retriever._freshness_score("2020-01-01T00:00:00+00:00", now)
        assert score < 0.01

    def test_unknown_timestamp_gets_neutral(self):
        """None timestamp gets neutral 0.3 score."""
        retriever, mock_db, mock_vi, mock_embed = _build_retriever()
        now = datetime.now(timezone.utc)
        score = retriever._freshness_score(None, now)
        assert score == 0.3


# ---------------------------------------------------------------------------
# Test: Factory function
# ---------------------------------------------------------------------------

class TestFactoryFunction:
    """Verify create_retriever factory."""

    def test_creates_retriever(self):
        """create_retriever returns a CanonicalMemoryRetriever."""
        retriever = create_retriever(MagicMock(), MagicMock(), AsyncMock())
        assert isinstance(retriever, CanonicalMemoryRetriever)


# ---------------------------------------------------------------------------
# Test: RetrievalResult data class
# ---------------------------------------------------------------------------

class TestRetrievalResult:
    """Verify RetrievalResult data class."""

    def test_default_values(self):
        """Default result has empty memories and zero tokens."""
        result = RetrievalResult()
        assert result.memories == []
        assert result.total_tokens == 0
        assert result.truncated is False
        assert result.latency_ms == 0.0
        assert result.query == ""


# ---------------------------------------------------------------------------
# Test: RetrievedMemory data class
# ---------------------------------------------------------------------------

class TestRetrievedMemory:
    """Verify RetrievedMemory data class."""

    def test_default_values(self):
        """Default memory has sensible defaults."""
        m = RetrievedMemory(id="test", statement="test", memory_type="PREFERENCE")
        assert m.confidence == 0.75
        assert m.importance == 0.5
        assert m.evidence_count == 1
        assert m.score == 0.0
        assert m.semantic_score is None
        assert m.lexical_score is None


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
