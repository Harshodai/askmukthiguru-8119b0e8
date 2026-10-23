"""Fail-closed regression tests for canonical-memory consolidation snapshots."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from services.canonical_memory.consolidator import (
    CanonicalMemoryConsolidator,
    ConsolidationCandidate,
)


@pytest.mark.asyncio
async def test_consolidation_aborts_before_mutation_when_snapshot_is_unconfirmed(monkeypatch):
    memories = [
        {"id": "memory-1", "statement": "I prefer quiet meditation."},
        {"id": "memory-2", "statement": "I like meditation in a quiet place."},
    ]
    candidate = ConsolidationCandidate(
        memory_ids=["memory-1", "memory-2"],
        reason="similar preference",
        merged_statement="I prefer quiet meditation.",
    )
    consolidator = CanonicalMemoryConsolidator(
        supabase_client=object(),
        llm_service=object(),
        threshold=1,
    )
    monkeypatch.setattr(
        consolidator,
        "_fetch_active_memories",
        AsyncMock(return_value=memories),
    )
    monkeypatch.setattr(consolidator, "_identify_candidates", lambda _rows: [candidate])
    monkeypatch.setattr(
        consolidator,
        "_llm_merge",
        AsyncMock(return_value=[candidate]),
    )
    monkeypatch.setattr(
        consolidator,
        "_validate_preservation",
        lambda _before, _merged: {"valid": True, "reason": "preserved"},
    )
    snapshot = AsyncMock(return_value=None)
    apply = AsyncMock(side_effect=AssertionError("must not mutate without a snapshot"))
    monkeypatch.setattr(consolidator, "_create_snapshot", snapshot)
    monkeypatch.setattr(consolidator, "_apply_consolidation", apply)

    result = await consolidator.consolidate("user-1")

    snapshot.assert_awaited_once_with("user-1", memories)
    apply.assert_not_awaited()
    assert result.error == "snapshot_creation_failed"
    assert result.after_count == result.before_count == 2
    assert result.rollback_available is False


def test_snapshot_migration_creates_consent_gated_service_role_table():
    repository_root = Path(__file__).resolve().parents[2]
    migration = (
        repository_root
        / "supabase/migrations/20261022000100_create_canonical_memory_compaction_snapshots.sql"
    )
    sql = migration.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS public.canonical_memory_compaction_snapshots" in sql
    assert "memories_json JSONB NOT NULL" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert (
        "REVOKE ALL ON TABLE public.canonical_memory_compaction_snapshots FROM PUBLIC, anon, authenticated"
        in sql
    )
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.canonical_memory_compaction_snapshots TO service_role"
        in sql
    )
    assert "BEFORE INSERT OR UPDATE" in sql
    assert "EXECUTE FUNCTION public.enforce_active_memory_consent_before_write()" in sql


def test_snapshot_decoder_accepts_jsonb_array_and_legacy_json_string():
    from services.canonical_memory.consolidator import _decode_snapshot_memories

    native = [{"id": "memory-1", "statement": "A preference."}]
    assert _decode_snapshot_memories(native) == native
    assert _decode_snapshot_memories('[{"id":"memory-1","statement":"A preference."}]') == native


def test_snapshot_decoder_rejects_corrupt_or_unexpected_payload():
    from services.canonical_memory.consolidator import _decode_snapshot_memories

    with pytest.raises(ValueError, match="list of memory objects"):
        _decode_snapshot_memories({"not": "a list"})
    with pytest.raises(ValueError, match="list of memory objects"):
        _decode_snapshot_memories(["not a memory object"])
