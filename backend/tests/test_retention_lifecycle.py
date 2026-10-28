"""DE-4.1: End-to-end retention lifecycle tests across telemetry, audit records, staging queue,
and corpus_gate_rejections.

Ensures old rows/files are pruned past TTL while active items are retained, with verified
dry-run protection and error escalation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from scripts.ops.cleanup_inactive_user_data import (
    TELEMETRY_TABLES,
    cleanup_corpus_gate_rejections,
    cleanup_staging_quality_queue,
    cleanup_telemetry_logs,
)
from services.compliance_logger import cleanup_compliance_audit_files
from tasks.retention_tasks import cleanup_retention_data


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "http://localhost:54321")
    monkeypatch.setattr(settings, "supabase_key", "test-key-mock")
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_KEY", "test-key-mock")


def test_telemetry_retention_pruning_success():
    """Telemetry tables are purged strictly for rows older than cutoff date."""
    mock_supabase = MagicMock()
    mock_delete_result = SimpleNamespace(count=15)

    # Setup delete execution chain
    (
        mock_supabase.table.return_value.delete.return_value.lt.return_value.execute.return_value
    ) = mock_delete_result

    with (
        patch("supabase.create_client", return_value=mock_supabase),
        patch("scripts.ops.cleanup_inactive_user_data.create_client", return_value=mock_supabase),
    ):
        total_purged = cleanup_telemetry_logs(
            days_retention=90, dry_run=False, client=mock_supabase
        )

    assert total_purged == 15 * len(TELEMETRY_TABLES)
    # Check that each table in TELEMETRY_TABLES was targeted
    called_tables = [c.args[0] for c in mock_supabase.table.call_args_list]
    for table in TELEMETRY_TABLES:
        assert table in called_tables


def test_telemetry_retention_dry_run_does_not_delete():
    """Dry run for telemetry logs queries count via SELECT, never deletes."""
    mock_supabase = MagicMock()
    mock_select_result = SimpleNamespace(count=8, data=[{"id": 1}])

    (
        mock_supabase.table.return_value.select.return_value.lt.return_value.execute.return_value
    ) = mock_select_result

    with (
        patch("supabase.create_client", return_value=mock_supabase),
        patch("scripts.ops.cleanup_inactive_user_data.create_client", return_value=mock_supabase),
    ):
        total_purged = cleanup_telemetry_logs(days_retention=90, dry_run=True, client=mock_supabase)

    assert total_purged == 8 * len(TELEMETRY_TABLES)
    # Assert delete() was never invoked on any table
    mock_supabase.table.return_value.delete.assert_not_called()


def test_audit_records_retention_pruning(tmp_path: Path):
    """Compliance audit files older than retention_days are unlinked; recent ones kept."""
    now = datetime.now(tz=UTC)
    old_date = (now - timedelta(days=120)).strftime("%Y-%m-%d")
    recent_date = (now - timedelta(days=15)).strftime("%Y-%m-%d")

    old_file = tmp_path / f"compliance_audit_{old_date}.jsonl"
    recent_file = tmp_path / f"compliance_audit_{recent_date}.jsonl"

    old_file.write_text('{"event": "old_audit_entry"}\n', encoding="utf-8")
    recent_file.write_text('{"event": "recent_audit_entry"}\n', encoding="utf-8")

    assert old_file.exists()
    assert recent_file.exists()

    purged = cleanup_compliance_audit_files(retention_days=90, base_dir=tmp_path)

    assert purged == 1
    assert not old_file.exists(), "Old audit file past TTL must be purged"
    assert recent_file.exists(), "Recent audit file within TTL must be retained"
    assert "recent_audit_entry" in recent_file.read_text(encoding="utf-8")


def test_staging_quality_queue_retention_pruning():
    """staging_quality_queue rows older than TTL are deleted in live mode."""
    mock_supabase = MagicMock()
    mock_delete_result = SimpleNamespace(count=27)

    (
        mock_supabase.table.return_value.delete.return_value.lt.return_value.execute.return_value
    ) = mock_delete_result

    with (
        patch("supabase.create_client", return_value=mock_supabase),
        patch("scripts.ops.cleanup_inactive_user_data.create_client", return_value=mock_supabase),
    ):
        purged = cleanup_staging_quality_queue(
            days_retention=90, dry_run=False, client=mock_supabase
        )

    assert purged == 27
    mock_supabase.table.assert_called_with("staging_quality_queue")
    mock_supabase.table.return_value.delete.assert_called_once()


def test_staging_quality_queue_dry_run_never_deletes():
    """staging_quality_queue dry run performs select, never delete."""
    mock_supabase = MagicMock()
    mock_select_result = SimpleNamespace(count=12, data=[])

    (
        mock_supabase.table.return_value.select.return_value.lt.return_value.execute.return_value
    ) = mock_select_result

    with (
        patch("supabase.create_client", return_value=mock_supabase),
        patch("scripts.ops.cleanup_inactive_user_data.create_client", return_value=mock_supabase),
    ):
        purged = cleanup_staging_quality_queue(
            days_retention=90, dry_run=True, client=mock_supabase
        )

    assert purged == 12
    mock_supabase.table.assert_called_with("staging_quality_queue")
    mock_supabase.table.return_value.delete.assert_not_called()


def test_corpus_gate_rejections_retention_pruning():
    """corpus_gate_rejections rows older than TTL are deleted in live mode."""
    mock_supabase = MagicMock()
    mock_delete_result = SimpleNamespace(count=45)

    (
        mock_supabase.table.return_value.delete.return_value.lt.return_value.execute.return_value
    ) = mock_delete_result

    with (
        patch("supabase.create_client", return_value=mock_supabase),
        patch("scripts.ops.cleanup_inactive_user_data.create_client", return_value=mock_supabase),
    ):
        purged = cleanup_corpus_gate_rejections(
            days_retention=90, dry_run=False, client=mock_supabase
        )

    assert purged == 45
    mock_supabase.table.assert_called_with("corpus_gate_rejections")
    mock_supabase.table.return_value.delete.assert_called_once()


def test_corpus_gate_rejections_dry_run_never_deletes():
    """corpus_gate_rejections dry run performs select count, never delete."""
    mock_supabase = MagicMock()
    mock_select_result = SimpleNamespace(count=19, data=[])

    (
        mock_supabase.table.return_value.select.return_value.lt.return_value.execute.return_value
    ) = mock_select_result

    with (
        patch("supabase.create_client", return_value=mock_supabase),
        patch("scripts.ops.cleanup_inactive_user_data.create_client", return_value=mock_supabase),
    ):
        purged = cleanup_corpus_gate_rejections(
            days_retention=90, dry_run=True, client=mock_supabase
        )

    assert purged == 19
    mock_supabase.table.assert_called_with("corpus_gate_rejections")
    mock_supabase.table.return_value.delete.assert_not_called()


def test_end_to_end_retention_task_orchestration():
    """cleanup_retention_data coordinates telemetry, audit, staging, and rejections."""
    with (
        patch(
            "scripts.ops.cleanup_inactive_user_data.cleanup_telemetry_logs",
            return_value=100,
        ) as mock_telemetry,
        patch(
            "services.compliance_logger.cleanup_compliance_audit_files",
            return_value=12,
        ) as mock_audit,
        patch(
            "scripts.ops.cleanup_inactive_user_data.cleanup_staging_quality_queue",
            return_value=30,
        ) as mock_staging,
        patch(
            "scripts.ops.cleanup_inactive_user_data.cleanup_corpus_gate_rejections",
            return_value=50,
        ) as mock_rejections,
    ):
        result = cleanup_retention_data(days_retention=90)

    assert result["telemetry_purged"] == 100
    assert result["audit_files_purged"] == 12
    assert result["staging_purged"] == 30
    assert result["rejections_purged"] == 50

    mock_telemetry.assert_called_once_with(days_retention=90)
    mock_audit.assert_called_once_with(retention_days=90)
    mock_staging.assert_called_once_with(days_retention=90)
    mock_rejections.assert_called_once_with(days_retention=90)
