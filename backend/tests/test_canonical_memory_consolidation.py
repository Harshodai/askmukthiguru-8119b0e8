"""Tests for canonical memory consolidation — Phase 6 of Adaptive Memory System.

These are unit tests using mocked Supabase client (same pattern as
test_canonical_memory_store.py). They verify the consolidation pipeline
without requiring a live database.

Run: cd backend && .venv/bin/pytest tests/test_canonical_memory_consolidation.py -v
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.canonical_memory.consolidator import (
    CanonicalMemoryConsolidator,
    ConsolidationCandidate,
    ConsolidationResult,
    create_consolidator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _make_memory_row(**overrides: Any) -> dict:
    row = {
        "id": _uid(),
        "user_id": "test-user",
        "tenant_id": "default",
        "memory_type": "PREFERENCE",
        "statement": "User prefers concise answers",
        "normalized_statement": "prefers concise answers",
        "fact_key": "prefers_tone",
        "confidence": 0.85,
        "importance": 0.6,
        "sensitivity": "normal",
        "status": "active",
        "source_conversation_id": "conv-1",
        "source_message_id": "msg-1",
        "source_turn_index": 0,
        "extraction_method": "llm",
        "evidence_count": 1,
        "embedding_id": None,
        "metadata": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_used_at": None,
        "last_confirmed_at": None,
        "valid_from": datetime.now(timezone.utc).isoformat(),
        "valid_to": None,
        "expires_at": None,
        "version": 1,
    }
    row.update(overrides)
    return row


def _mock_supabase(
    active_memories: list[dict] | None = None,
    count: int | None = None,
    snapshot_id: str | None = None,
    create_result: dict | None = None,
) -> MagicMock:
    """Build a mock Supabase client with configurable responses."""
    supabase = MagicMock()
    table_mock = MagicMock()
    supabase.table.return_value = table_mock

    # Chain methods
    table_mock.select.return_value = table_mock
    table_mock.insert.return_value = table_mock
    table_mock.update.return_value = table_mock
    table_mock.delete.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.is_.return_value = table_mock
    table_mock.order.return_value = table_mock
    table_mock.single.return_value = table_mock

    # Default execute result
    execute_result = MagicMock()
    execute_result.data = []
    execute_result.count = 0
    table_mock.execute.return_value = execute_result

    # Configure count query
    if active_memories is not None and count is not None:
        count_result = MagicMock()
        count_result.count = count
        count_result.data = active_memories
        # First call (count) returns count, second (select *) returns list
        table_mock.execute.side_effect = [count_result, MagicMock(data=active_memories)]

    # Configure snapshot insert
    if snapshot_id:
        snap_result = MagicMock()
        snap_result.data = [{"id": snapshot_id}]
        # This will be used for snapshot inserts

    # Configure memory create
    if create_result:
        create_res = MagicMock()
        create_res.data = [create_result]
        # Last call returns create result

    return supabase


def _make_llm_service(merge_result: str | None = None) -> MagicMock:
    """Build a mock LLM service."""
    llm = MagicMock()
    if merge_result:
        llm.generate = AsyncMock(return_value=merge_result)
    else:
        llm.generate = AsyncMock(return_value=None)
    return llm


# ---------------------------------------------------------------------------
# 1. should_consolidate
# ---------------------------------------------------------------------------

class TestShouldConsolidate:
    @pytest.mark.asyncio
    async def test_below_threshold_returns_false(self):
        """Memories at or below threshold → False."""
        supabase = _mock_supabase()
        count_result = MagicMock()
        count_result.count = 30
        supabase.table.return_value.execute.return_value = count_result

        consolidator = create_consolidator(supabase, threshold=50)
        result = await consolidator.should_consolidate("user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_at_threshold_returns_false(self):
        """Exactly at threshold → False."""
        supabase = _mock_supabase()
        count_result = MagicMock()
        count_result.count = 50
        supabase.table.return_value.execute.return_value = count_result

        consolidator = create_consolidator(supabase, threshold=50)
        result = await consolidator.should_consolidate("user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_above_threshold_returns_true(self):
        """Above threshold → True."""
        supabase = _mock_supabase()
        count_result = MagicMock()
        count_result.count = 55
        supabase.table.return_value.execute.return_value = count_result

        consolidator = create_consolidator(supabase, threshold=50)
        result = await consolidator.should_consolidate("user-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_custom_threshold(self):
        """Custom threshold is respected."""
        supabase = _mock_supabase()
        count_result = MagicMock()
        count_result.count = 12
        supabase.table.return_value.execute.return_value = count_result

        consolidator = create_consolidator(supabase, threshold=10)
        result = await consolidator.should_consolidate("user-1")
        assert result is True


# ---------------------------------------------------------------------------
# 2. consolidate — below threshold
# ---------------------------------------------------------------------------

class TestConsolidateBelowThreshold:
    @pytest.mark.asyncio
    async def test_no_op_when_below_threshold(self):
        """Consolidation returns early when count <= threshold."""
        memories = [_make_memory_row() for _ in range(10)]
        supabase = MagicMock()
        table_mock = MagicMock()
        supabase.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.order.return_value = table_mock

        result_mock = MagicMock()
        result_mock.data = memories
        result_mock.count = 10
        table_mock.execute.return_value = result_mock

        consolidator = create_consolidator(supabase, threshold=50)
        result = await consolidator.consolidate("user-1")

        assert result.before_count == 10
        assert result.after_count == 10
        assert result.superseded_ids == []
        assert result.created_ids == []
        assert "No consolidation needed" in result.reason

    @pytest.mark.asyncio
    async def test_below_threshold_no_candidates(self):
        """Even if threshold is low, no candidates means no consolidation."""
        # 5 memories with different types and no overlap
        memories = [
            _make_memory_row(
                id=_uid(),
                memory_type="PROFILE",
                statement="User lives in Mumbai",
                fact_key="lives_in",
            ),
            _make_memory_row(
                id=_uid(),
                memory_type="GOAL",
                statement="User wants to learn meditation",
                fact_key="goal_meditation",
            ),
            _make_memory_row(
                id=_uid(),
                memory_type="INTEREST",
                statement="User is interested in yoga",
                fact_key=None,
            ),
            _make_memory_row(
                id=_uid(),
                memory_type="RELATIONSHIP",
                statement="User's guru is Preethaji",
                fact_key=None,
            ),
            _make_memory_row(
                id=_uid(),
                memory_type="REFLECTION",
                statement="User reflects on daily practice",
                fact_key=None,
            ),
        ]
        supabase = MagicMock()
        table_mock = MagicMock()
        supabase.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.order.return_value = table_mock

        # consolidate() calls _fetch_active_memories which uses select("*")
        # and needs .data to return the memories list
        data_result = MagicMock()
        data_result.data = memories
        table_mock.execute.return_value = data_result

        consolidator = create_consolidator(supabase, threshold=3)
        result = await consolidator.consolidate("user-1")

        assert result.before_count == 5
        assert result.after_count == 5
        assert "no consolidation candidates" in result.reason


# ---------------------------------------------------------------------------
# 3. consolidate — same fact_key candidates
# ---------------------------------------------------------------------------

class TestConsolidateFactKeyCandidates:
    @pytest.mark.asyncio
    async def test_same_fact_key_identified(self):
        """Multiple memories with same fact_key are consolidation candidates."""
        memories = [
            _make_memory_row(
                id="mem-1",
                statement="User prefers concise answers",
                fact_key="prefers_tone",
                memory_type="PREFERENCE",
                importance=0.7,
            ),
            _make_memory_row(
                id="mem-2",
                statement="User wants brief responses",
                fact_key="prefers_tone",
                memory_type="PREFERENCE",
                importance=0.6,
            ),
            _make_memory_row(
                id="mem-3",
                statement="User lives in Mumbai",
                fact_key="lives_in",
                memory_type="PROFILE",
                importance=0.8,
            ),
            _make_memory_row(
                id="mem-4",
                statement="User practices meditation daily",
                fact_key="meditation_practice",
                memory_type="PRACTICE",
                importance=0.9,
            ),
            _make_memory_row(
                id="mem-5",
                statement="User is a software engineer",
                fact_key="occupation",
                memory_type="PROFILE",
                importance=0.5,
            ),
        ]
        supabase = MagicMock()
        table_mock = MagicMock()
        supabase.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.order.return_value = table_mock

        result_mock = MagicMock()
        result_mock.data = memories
        result_mock.count = 5
        table_mock.execute.return_value = result_mock

        llm = _make_llm_service(merge_result="User prefers concise, brief responses")
        consolidator = create_consolidator(supabase, llm, threshold=1)

        # Mock the apply step
        with patch.object(consolidator, "_create_snapshot", new_callable=AsyncMock, return_value="snap-1"):
            with patch.object(consolidator, "_apply_consolidation", new_callable=AsyncMock) as mock_apply:
                mock_apply.return_value = {
                    "superseded_ids": ["mem-1", "mem-2"],
                    "created_ids": ["mem-new-1"],
                    "audit_event_ids": ["evt-1"],
                }
                result = await consolidator.consolidate("user-1")

        assert result.before_count == 5
        assert result.superseded_ids == ["mem-1", "mem-2"]
        assert result.created_ids == ["mem-new-1"]
        assert result.rollback_available is True


# ---------------------------------------------------------------------------
# 4. consolidate — dry run
# ---------------------------------------------------------------------------

class TestConsolidateDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_does_not_modify(self):
        """Dry run identifies candidates but does not apply changes."""
        memories = [
            _make_memory_row(
                id="mem-1",
                statement="User prefers concise answers",
                fact_key="prefers_tone",
                memory_type="PREFERENCE",
            ),
            _make_memory_row(
                id="mem-2",
                statement="User wants brief responses",
                fact_key="prefers_tone",
                memory_type="PREFERENCE",
            ),
            _make_memory_row(
                id="mem-3",
                statement="User lives in Mumbai",
                fact_key="lives_in",
                memory_type="PROFILE",
            ),
            _make_memory_row(
                id="mem-4",
                statement="User practices meditation daily",
                fact_key="meditation_practice",
                memory_type="PRACTICE",
            ),
            _make_memory_row(
                id="mem-5",
                statement="User is a software engineer",
                fact_key="occupation",
                memory_type="PROFILE",
            ),
        ]
        supabase = MagicMock()
        table_mock = MagicMock()
        supabase.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.order.return_value = table_mock

        result_mock = MagicMock()
        result_mock.data = memories
        result_mock.count = 5
        table_mock.execute.return_value = result_mock

        consolidator = create_consolidator(supabase, threshold=1)
        result = await consolidator.consolidate("user-1", dry_run=True)

        assert result.dry_run is True
        assert result.superseded_ids == []
        assert result.created_ids == []
        assert "Dry run" in result.reason
        # Verify no update/insert was called
        table_mock.update.assert_not_called()
        table_mock.insert.assert_not_called()


# ---------------------------------------------------------------------------
# 5. validation — too many memories
# ---------------------------------------------------------------------------

class TestConsolidateValidation:
    @pytest.mark.asyncio
    async def test_rejects_consolidating_more_than_50_percent(self):
        """Consolidation is rejected if it would affect >50% of memories."""
        # 10 memories, all same fact_key → would consolidate all
        memories = [
            _make_memory_row(
                id=f"mem-{i}",
                statement=f"Variant {i} of the same fact",
                fact_key="same_key",
            )
            for i in range(10)
        ]
        supabase = MagicMock()
        table_mock = MagicMock()
        supabase.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.order.return_value = table_mock

        result_mock = MagicMock()
        result_mock.data = memories
        result_mock.count = 10
        table_mock.execute.return_value = result_mock

        consolidator = create_consolidator(supabase, threshold=1)
        result = await consolidator.consolidate("user-1")

        assert result.error is not None
        assert "50%" in result.error
        assert result.after_count == 10


# ---------------------------------------------------------------------------
# 6. LLM merge
# ---------------------------------------------------------------------------

class TestLLMMerge:
    @pytest.mark.asyncio
    async def test_llm_merge_called(self):
        """LLM is called with group statements for merging."""
        llm = _make_llm_service(merge_result="User prefers concise answers in general")
        consolidator = create_consolidator(MagicMock(), llm, threshold=1)

        candidates = [
            ConsolidationCandidate(
                memory_ids=["a", "b"],
                reason="Same fact_key",
            )
        ]
        memories = [
            {"id": "a", "statement": "User prefers concise answers", "confidence": 0.8, "importance": 0.6, "memory_type": "PREFERENCE", "fact_key": "prefers_tone"},
            {"id": "b", "statement": "User wants brief responses", "confidence": 0.7, "importance": 0.5, "memory_type": "PREFERENCE", "fact_key": "prefers_tone"},
        ]

        result = await consolidator._llm_merge(candidates, memories)
        assert len(result) == 1
        assert result[0].merged_statement == "User prefers concise answers in general"
        llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_simple_merge(self):
        """When LLM fails, simple merge is used as fallback."""
        llm = _make_llm_service(merge_result=None)
        consolidator = create_consolidator(MagicMock(), llm, threshold=1)

        candidates = [
            ConsolidationCandidate(
                memory_ids=["a", "b"],
                reason="Same fact_key",
            )
        ]
        memories = [
            {"id": "a", "statement": "User prefers concise answers", "confidence": 0.8, "importance": 0.6, "memory_type": "PREFERENCE", "fact_key": "prefers_tone"},
            {"id": "b", "statement": "User wants brief responses", "confidence": 0.7, "importance": 0.5, "memory_type": "PREFERENCE", "fact_key": "prefers_tone"},
        ]

        result = await consolidator._llm_merge(candidates, memories)
        assert len(result) == 1
        # Should have fallback merge
        assert result[0].merged_statement is not None
        assert len(result[0].merged_statement) > 0


# ---------------------------------------------------------------------------
# 7. simple_merge
# ---------------------------------------------------------------------------

class TestSimpleMerge:
    def test_deduplicates_identical(self):
        """Identical statements produce single statement."""
        consolidator = create_consolidator(MagicMock(), MagicMock())
        result = consolidator._simple_merge([
            "User prefers concise answers",
            "User prefers concise answers",
        ])
        assert result == "User prefers concise answers"

    def test_combines_different(self):
        """Different statements are combined."""
        consolidator = create_consolidator(MagicMock(), MagicMock())
        result = consolidator._simple_merge([
            "User prefers concise answers",
            "User wants brief responses",
        ])
        assert "concise" in result
        assert "brief" in result

    def test_empty_input(self):
        """Empty list returns empty string."""
        consolidator = create_consolidator(MagicMock(), MagicMock())
        result = consolidator._simple_merge([])
        assert result == ""


# ---------------------------------------------------------------------------
# 8. keyword extraction and overlap
# ---------------------------------------------------------------------------

class TestKeywordOverlap:
    def test_identical_keywords(self):
        """Identical keywords → overlap 1.0."""
        consolidator = create_consolidator(MagicMock(), MagicMock())
        kw = consolidator._extract_keywords("User prefers concise answers")
        result = consolidator._keyword_overlap(kw, kw)
        assert result == 1.0

    def test_no_overlap(self):
        """Disjoint keywords → overlap 0.0."""
        consolidator = create_consolidator(MagicMock(), MagicMock())
        kw_a = consolidator._extract_keywords("lives in Mumbai")
        kw_b = {"yoga", "meditation", "spiritual"}
        result = consolidator._keyword_overlap(kw_a, kw_b)
        assert result == 0.0

    def test_partial_overlap(self):
        """Partial overlap returns Jaccard index."""
        consolidator = create_consolidator(MagicMock(), MagicMock())
        kw_a = {"user", "prefers", "concise", "answers"}
        kw_b = {"user", "wants", "brief", "responses"}
        result = consolidator._keyword_overlap(kw_a, kw_b)
        # intersection = {user} = 1, union = {user,prefers,concise,answers,wants,brief,responses} = 7
        assert abs(result - 1 / 7) < 0.01


# ---------------------------------------------------------------------------
# 9. candidate identification
# ---------------------------------------------------------------------------

class TestIdentifyCandidates:
    def test_same_fact_key_grouped(self):
        """Memories with same fact_key are grouped."""
        consolidator = create_consolidator(MagicMock(), MagicMock())
        memories = [
            {"id": "a", "statement": "Concise answers", "fact_key": "tone", "memory_type": "PREFERENCE", "importance": 0.5},
            {"id": "b", "statement": "Brief responses", "fact_key": "tone", "memory_type": "PREFERENCE", "importance": 0.5},
            {"id": "c", "statement": "Lives in Mumbai", "fact_key": "location", "memory_type": "PROFILE", "importance": 0.8},
        ]
        candidates = consolidator._identify_candidates(memories)
        assert len(candidates) >= 1
        # The tone group should be a candidate
        tone_candidate = next(
            (c for c in candidates if "tone" in c.reason), None
        )
        assert tone_candidate is not None
        assert set(tone_candidate.memory_ids) == {"a", "b"}

    def test_no_candidates_for_diverse_memories(self):
        """Diverse, non-overlapping memories produce no candidates."""
        consolidator = create_consolidator(MagicMock(), MagicMock())
        memories = [
            {"id": "a", "statement": "Lives in Mumbai", "fact_key": "lives_in", "memory_type": "PROFILE", "importance": 0.8},
            {"id": "b", "statement": "Prefers Hindi", "fact_key": "prefers_language", "memory_type": "PREFERENCE", "importance": 0.6},
            {"id": "c", "statement": "Interested in meditation", "fact_key": None, "memory_type": "INTEREST", "importance": 0.5},
        ]
        candidates = consolidator._identify_candidates(memories)
        assert len(candidates) == 0


# ---------------------------------------------------------------------------
# 10. validation
# ---------------------------------------------------------------------------

class TestValidatePreservation:
    def test_valid_when_under_50_percent(self):
        """Consolidation under 50% passes validation."""
        consolidator = create_consolidator(MagicMock(), MagicMock())
        memories = [{"id": f"m{i}", "importance": 0.5, "memory_type": "PREFERENCE"} for i in range(10)]
        candidates = [ConsolidationCandidate(memory_ids=["m0", "m1"], reason="test")]
        result = consolidator._validate_preservation(memories, candidates)
        assert result["valid"] is True

    def test_invalid_when_over_50_percent(self):
        """Consolidation over 50% fails validation."""
        consolidator = create_consolidator(MagicMock(), MagicMock())
        memories = [{"id": f"m{i}", "importance": 0.5, "memory_type": "PREFERENCE"} for i in range(10)]
        # 6 out of 10 = 60% > 50%
        candidates = [ConsolidationCandidate(memory_ids=[f"m{i}" for i in range(6)], reason="test")]
        result = consolidator._validate_preservation(memories, candidates)
        assert result["valid"] is False
        assert "50%" in result["reason"]


# ---------------------------------------------------------------------------
# 11. rollback
# ---------------------------------------------------------------------------

class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_returns_false_on_missing_snapshot(self):
        """Rollback returns False when snapshot not found."""
        supabase = MagicMock()
        table_mock = MagicMock()
        supabase.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.single.return_value = table_mock
        table_mock.execute.side_effect = Exception("not found")

        consolidator = create_consolidator(supabase, MagicMock())
        result = await consolidator.rollback("user-1", "nonexistent-snap")
        assert result is False


# ---------------------------------------------------------------------------
# 12. audit events
# ---------------------------------------------------------------------------

class TestAuditEvents:
    @pytest.mark.asyncio
    async def test_consolidation_creates_audit_events(self):
        """Consolidation creates MERGED and SUPERSEDED audit events."""
        memories = [
            _make_memory_row(id="mem-1", fact_key="tone", memory_type="PREFERENCE",
                             statement="User prefers concise answers"),
            _make_memory_row(id="mem-2", fact_key="tone", memory_type="PREFERENCE",
                             statement="User wants brief responses"),
            _make_memory_row(id="mem-3", fact_key="location", memory_type="PROFILE",
                             statement="User lives in Mumbai"),
            _make_memory_row(id="mem-4", fact_key="hobby", memory_type="INTEREST",
                             statement="User practices yoga"),
            _make_memory_row(id="mem-5", fact_key="goal", memory_type="GOAL",
                             statement="User wants to learn meditation"),
        ]
        supabase = MagicMock()
        table_mock = MagicMock()
        supabase.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.order.return_value = table_mock

        result_mock = MagicMock()
        result_mock.data = memories
        result_mock.count = 5
        table_mock.execute.return_value = result_mock

        llm = _make_llm_service(merge_result="User prefers concise, brief responses")
        consolidator = create_consolidator(supabase, llm, threshold=1)

        with patch.object(consolidator, "_create_snapshot", new_callable=AsyncMock, return_value="snap-1"):
            with patch.object(consolidator, "_apply_consolidation", new_callable=AsyncMock) as mock_apply:
                mock_apply.return_value = {
                    "superseded_ids": ["mem-1", "mem-2"],
                    "created_ids": ["mem-new"],
                    "audit_event_ids": ["evt-1", "evt-2"],
                }
                result = await consolidator.consolidate("user-1")

        assert len(result.audit_event_ids) == 2
        assert "evt-1" in result.audit_event_ids
        assert "evt-2" in result.audit_event_ids


# ---------------------------------------------------------------------------
# 13. factory
# ---------------------------------------------------------------------------

class TestFactory:
    def test_create_consolidator(self):
        """Factory creates consolidator with correct attributes."""
        supabase = MagicMock()
        llm = MagicMock()
        consolidator = create_consolidator(supabase, llm, threshold=25)
        assert consolidator._db is supabase
        assert consolidator._llm is llm
        assert consolidator._threshold == 25

    def test_default_threshold(self):
        """Factory uses default threshold when not specified."""
        consolidator = create_consolidator(MagicMock())
        assert consolidator._threshold == 50


# ---------------------------------------------------------------------------
# 14. error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_consolidation_error_returns_error(self):
        """Errors during consolidation are caught and reported."""
        supabase = MagicMock()
        table_mock = MagicMock()
        supabase.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.order.return_value = table_mock
        table_mock.execute.side_effect = Exception("DB connection lost")

        consolidator = create_consolidator(supabase, MagicMock(), threshold=1)
        result = await consolidator.consolidate("user-1")

        assert result.error is not None
        assert "DB connection lost" in result.error
        assert result.after_count == 0

    @pytest.mark.asyncio
    async def test_apply_partial_failure_continues(self):
        """Partial failures during apply don't abort the entire operation."""
        memories = [
            _make_memory_row(id="mem-1", fact_key="tone", memory_type="PREFERENCE",
                             statement="User prefers concise answers"),
            _make_memory_row(id="mem-2", fact_key="tone", memory_type="PREFERENCE",
                             statement="User wants brief responses"),
            _make_memory_row(id="mem-3", fact_key="location", memory_type="PROFILE",
                             statement="User lives in Mumbai"),
            _make_memory_row(id="mem-4", fact_key="hobby", memory_type="INTEREST",
                             statement="User practices yoga"),
            _make_memory_row(id="mem-5", fact_key="goal", memory_type="GOAL",
                             statement="User wants to learn meditation"),
        ]
        supabase = MagicMock()
        table_mock = MagicMock()
        supabase.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.order.return_value = table_mock

        result_mock = MagicMock()
        result_mock.data = memories
        result_mock.count = 5
        table_mock.execute.return_value = result_mock

        llm = _make_llm_service(merge_result="Merged statement")
        consolidator = create_consolidator(supabase, llm, threshold=1)

        # Mock apply to simulate partial failure
        async def _partial_apply(user_id, mems, candidates):
            return {
                "superseded_ids": ["mem-1"],  # only one succeeded
                "created_ids": ["mem-new"],
                "audit_event_ids": ["evt-1"],
            }

        with patch.object(consolidator, "_create_snapshot", new_callable=AsyncMock, return_value="snap-1"):
            with patch.object(consolidator, "_apply_consolidation", new_callable=AsyncMock, side_effect=_partial_apply):
                result = await consolidator.consolidate("user-1")

        # Should still report what succeeded
        assert result.superseded_ids == ["mem-1"]
        assert result.created_ids == ["mem-new"]


if __name__ == "__main__":
    print("Running self-check...")
    # Quick smoke test
    from unittest.mock import MagicMock
    supabase = MagicMock()
    llm = MagicMock()
    consolidator = create_consolidator(supabase, llm)
    assert consolidator._threshold == 50
    print("Self-check passed.")
