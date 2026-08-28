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
        patch("services.layered_memory.l2_scene_compressor.compress_turns_to_scene", new=AsyncMock(return_value=None)),
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
    mock_outbox.mark_failed.assert_awaited_once_with("outbox-1", "consent revoked before processing")
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
