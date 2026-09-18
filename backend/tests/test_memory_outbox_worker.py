"""Tests for durable Memory Outbox Celery worker and queue drain logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from tasks.memory_outbox_tasks import _drain_once, drain_memory_outbox


def _mock_payload():
    return {
        "user_message": "What is the nature of suffering?",
        "assistant_answer": "Suffering arises from resistance to what is.",
        "citations": [{"title": "Four Sacred Secrets", "source_url": "https://example.com/1"}],
        "intent": "PHILOSOPHY",
        "distress_level": 0,
        "prior_messages": [],
    }


def _mock_outbox_row(
    outbox_id: str = "outbox-1",
    user_id: str = "user-123",
    tenant_id: str = "tenant-abc",
    session_id: str = "session-xyz",
    payload: dict | None = None,
):
    return {
        "id": outbox_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "session_id": session_id,
        "payload": payload or _mock_payload(),
        "status": "claimed",
    }


@pytest.mark.asyncio
async def test_drain_once_processes_pending_entries_and_marks_completed():
    """Verify that pending memory outbox entries are processed and marked done."""
    mock_container = MagicMock()
    mock_outbox = AsyncMock()
    mock_memory_svc = AsyncMock()
    mock_episodic_svc = AsyncMock()
    mock_user_profile = AsyncMock()

    row = _mock_outbox_row()
    mock_outbox.get_pending.return_value = [row]
    mock_outbox.active_consent.return_value = {"granted": True, "consent_version": "memory-v1"}
    mock_outbox.mark_processed.return_value = None

    mock_container.memory_outbox = mock_outbox
    mock_container.memory_service = mock_memory_svc
    mock_container.episodic_memory_service = mock_episodic_svc
    mock_container.user_profile = mock_user_profile
    mock_container.supabase_client = MagicMock()

    with (
        patch("app.dependencies.get_container", return_value=mock_container),
        patch.object(settings, "feature_memory_write", True),
        patch("services.layered_memory.l1_extractor.extract_atoms", new=AsyncMock(return_value=[])),
        patch(
            "services.layered_memory.l2_scene_compressor.compress_turns_to_scene",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await _drain_once(limit=10)

    assert result == {"claimed": 1, "processed": 1, "failed": 0}
    mock_outbox.get_pending.assert_awaited_once_with(limit=10)
    mock_outbox.active_consent.assert_awaited_once_with(user_id="user-123", tenant_id="tenant-abc")
    mock_memory_svc.extract_and_write.assert_awaited_once()
    mock_episodic_svc.log_episode.assert_awaited_once_with(
        user_id="user-123",
        query="What is the nature of suffering?",
        answer="Suffering arises from resistance to what is.",
        citations=[{"title": "Four Sacred Secrets", "source_url": "https://example.com/1"}],
        intent="PHILOSOPHY",
    )
    mock_outbox.mark_processed.assert_awaited_once_with("outbox-1")


@pytest.mark.asyncio
async def test_drain_once_marks_failed_when_consent_revoked():
    """Verify that outbox entry is marked failed if user consent was revoked."""
    mock_container = MagicMock()
    mock_outbox = AsyncMock()
    mock_memory_svc = AsyncMock()

    row = _mock_outbox_row()
    mock_outbox.get_pending.return_value = [row]
    mock_outbox.active_consent.return_value = None  # Revoked / absent
    mock_outbox.mark_failed.return_value = None

    mock_container.memory_outbox = mock_outbox
    mock_container.memory_service = mock_memory_svc
    mock_container.episodic_memory_service = None
    mock_container.user_profile = None

    with (
        patch("app.dependencies.get_container", return_value=mock_container),
        patch.object(settings, "feature_memory_write", True),
    ):
        result = await _drain_once(limit=10)

    assert result == {"claimed": 1, "processed": 0, "failed": 1}
    mock_outbox.mark_failed.assert_awaited_once_with(
        "outbox-1", "consent revoked before processing"
    )
    mock_memory_svc.extract_and_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_drain_once_handles_processing_exception():
    """Verify that exceptions during memory extraction mark the outbox entry failed."""
    mock_container = MagicMock()
    mock_outbox = AsyncMock()
    mock_memory_svc = AsyncMock()
    mock_memory_svc.extract_and_write.side_effect = RuntimeError("Database connection lost")

    row = _mock_outbox_row()
    mock_outbox.get_pending.return_value = [row]
    mock_outbox.active_consent.return_value = {"granted": True}
    mock_outbox.mark_failed.return_value = None

    mock_container.memory_outbox = mock_outbox
    mock_container.memory_service = mock_memory_svc
    mock_container.episodic_memory_service = None
    mock_container.user_profile = None

    with (
        patch("app.dependencies.get_container", return_value=mock_container),
        patch.object(settings, "feature_memory_write", True),
    ):
        result = await _drain_once(limit=10)

    assert result == {"claimed": 1, "processed": 0, "failed": 1}
    mock_outbox.mark_failed.assert_awaited_once_with("outbox-1", "Database connection lost")


@pytest.mark.asyncio
async def test_drain_once_returns_zero_when_feature_disabled():
    """Verify that _drain_once short-circuits when feature_memory_write is False."""
    mock_container = MagicMock()
    mock_outbox = AsyncMock()
    mock_container.memory_outbox = mock_outbox
    mock_container.memory_service = AsyncMock()

    with (
        patch("app.dependencies.get_container", return_value=mock_container),
        patch.object(settings, "feature_memory_write", False),
    ):
        result = await _drain_once(limit=10)

    assert result == {"claimed": 0, "processed": 0, "failed": 0}
    mock_outbox.get_pending.assert_not_awaited()


def test_drain_memory_outbox_task_entrypoint():
    """Verify that drain_memory_outbox Celery task executes _drain_once."""
    expected_result = {"claimed": 2, "processed": 2, "failed": 0}

    with patch("tasks.memory_outbox_tasks._drain_once", return_value=expected_result):
        # Direct task invocation
        res = drain_memory_outbox.apply()
        assert res.result == expected_result


# ======================================================================
# AMK-C-005 — crash-and-reclaim must not duplicate enrichment writes
# ======================================================================


def _wire(container, outbox, memory_svc, episodic, profile):
    container.memory_outbox = outbox
    container.memory_service = memory_svc
    container.episodic_memory_service = episodic
    container.user_profile = profile
    container.supabase_client = MagicMock()


def _recorded_steps(outbox) -> list[str]:
    """Last step-list the drain persisted via mark_step_done."""
    calls = outbox.mark_step_done.await_args_list
    return list(calls[-1].args[1]) if calls else []


@pytest.mark.asyncio
async def test_reclaim_after_crash_does_not_rerun_committed_enrichment():
    """A row reclaimed after a worker crash resumes; it does not re-write.

    claim_memory_outbox() reclaims any row stuck in 'processing' for 10
    minutes, including one whose worker was SIGKILLed after the enrichment
    writes but before mark_processed(). Without per-step markers that replays
    every write — a second episodic memory, a second set of L1 atoms, a second
    L2 scene block for one conversation turn (AMK-C-005).
    """
    container = MagicMock()
    outbox = AsyncMock()
    memory_svc = AsyncMock()
    episodic = AsyncMock()
    profile = AsyncMock()
    _wire(container, outbox, memory_svc, episodic, profile)

    outbox.get_pending.return_value = [_mock_outbox_row()]
    outbox.active_consent.return_value = {"granted": True, "consent_version": "memory-v1"}

    patches = (
        patch("app.dependencies.get_container", return_value=container),
        patch.object(settings, "feature_memory_write", True),
        patch(
            "services.layered_memory.l1_extractor.extract_atoms",
            new=AsyncMock(return_value=[{"text": "atom"}]),
        ),
        patch(
            "services.layered_memory.l2_scene_compressor.compress_turns_to_scene",
            new=AsyncMock(return_value={"scene": "s"}),
        ),
        patch(
            "services.layered_memory.l2_scene_compressor.save_scene_block",
            new=AsyncMock(return_value=None),
        ),
    )

    # --- attempt 1: all enrichment commits, then the worker "dies" ---------
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        await _drain_once(limit=10)

    committed = _recorded_steps(outbox)
    assert committed, "no completed steps were recorded — a reclaim would replay everything"
    assert "extract_and_write" in committed
    assert "episodic_log" in committed

    # --- attempt 2: the staleness reclaim hands the SAME row back ----------
    memory_svc.reset_mock()
    episodic.reset_mock()
    profile.reset_mock()
    outbox.reset_mock()
    outbox.get_pending.return_value = [_mock_outbox_row() | {"completed_steps": committed}]
    outbox.active_consent.return_value = {"granted": True, "consent_version": "memory-v1"}

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = await _drain_once(limit=10)

    assert result == {"claimed": 1, "processed": 1, "failed": 0}
    memory_svc.extract_and_write.assert_not_awaited()
    episodic.log_episode.assert_not_awaited()
    memory_svc.add_atoms.assert_not_awaited()
    profile.save_conversation_memory.assert_not_awaited()
    # The row still finishes — resuming must not strand it in 'processing'.
    outbox.mark_processed.assert_awaited_once_with("outbox-1")


@pytest.mark.asyncio
async def test_reclaim_resumes_only_the_steps_that_had_not_committed():
    """Partial progress replays the missing step and nothing else."""
    container = MagicMock()
    outbox = AsyncMock()
    memory_svc = AsyncMock()
    episodic = AsyncMock()
    _wire(container, outbox, memory_svc, episodic, None)

    # extract_and_write committed before the crash; episodic did not.
    row = _mock_outbox_row() | {"completed_steps": ["extract_and_write"]}
    outbox.get_pending.return_value = [row]
    outbox.active_consent.return_value = {"granted": True, "consent_version": "memory-v1"}

    with (
        patch("app.dependencies.get_container", return_value=container),
        patch.object(settings, "feature_memory_write", True),
        patch("services.layered_memory.l1_extractor.extract_atoms", new=AsyncMock(return_value=[])),
        patch(
            "services.layered_memory.l2_scene_compressor.compress_turns_to_scene",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await _drain_once(limit=10)

    assert result == {"claimed": 1, "processed": 1, "failed": 0}
    memory_svc.extract_and_write.assert_not_awaited()
    episodic.log_episode.assert_awaited_once()


@pytest.mark.asyncio
async def test_step_marker_failure_degrades_to_replay_not_to_row_failure():
    """A failed marker write must not fail the row.

    Losing a marker costs the resume optimisation for one step; failing the
    row would cost the user's memory entirely. The first is the correct
    degradation.
    """
    container = MagicMock()
    outbox = AsyncMock()
    memory_svc = AsyncMock()
    _wire(container, outbox, memory_svc, None, None)

    outbox.get_pending.return_value = [_mock_outbox_row()]
    outbox.active_consent.return_value = {"granted": True, "consent_version": "memory-v1"}
    outbox.mark_step_done.side_effect = RuntimeError("supabase unavailable")

    with (
        patch("app.dependencies.get_container", return_value=container),
        patch.object(settings, "feature_memory_write", True),
        patch("services.layered_memory.l1_extractor.extract_atoms", new=AsyncMock(return_value=[])),
        patch(
            "services.layered_memory.l2_scene_compressor.compress_turns_to_scene",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await _drain_once(limit=10)

    assert result == {"claimed": 1, "processed": 1, "failed": 0}
    outbox.mark_processed.assert_awaited_once_with("outbox-1")
