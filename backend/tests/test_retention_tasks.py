"""Tests for AMK-C-003 and AMK-C-004: Celery Beat data retention cleanup tasks."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch


def test_celery_beat_schedule_contains_retention_task():
    """Verify that celery_config.py has cleanup-retention-data scheduled daily."""
    from celery_config import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "cleanup-retention-data" in schedule, "cleanup-retention-data missing from beat_schedule"

    entry = schedule["cleanup-retention-data"]
    assert entry["task"] == "tasks.retention_tasks.cleanup_retention_data"
    assert (
        entry["schedule"] == 86400.0
        or getattr(entry["schedule"], "total_seconds", lambda: 0)() == 86400.0
    )


def test_cleanup_compliance_audit_files(tmp_path: Path):
    """Verify that compliance audit files older than retention_days are purged."""
    from services.compliance_logger import cleanup_compliance_audit_files

    now = datetime.now(tz=UTC)
    old_date = (now - timedelta(days=95)).strftime("%Y-%m-%d")
    recent_date = (now - timedelta(days=10)).strftime("%Y-%m-%d")

    old_file = tmp_path / f"compliance_audit_{old_date}.jsonl"
    recent_file = tmp_path / f"compliance_audit_{recent_date}.jsonl"

    old_file.write_text('{"record": "old"}\n')
    recent_file.write_text('{"record": "recent"}\n')

    purged = cleanup_compliance_audit_files(retention_days=90, base_dir=tmp_path)

    assert purged == 1
    assert not old_file.exists()
    assert recent_file.exists()


def test_cleanup_retention_data_task_invokes_both():
    """Verify that cleanup_retention_data task runs telemetry and audit cleanups."""
    from tasks.retention_tasks import cleanup_retention_data

    with (
        patch(
            "scripts.ops.cleanup_inactive_user_data.cleanup_telemetry_logs",
            return_value=42,
        ) as mock_telemetry,
        patch(
            "services.compliance_logger.cleanup_compliance_audit_files",
            return_value=5,
        ) as mock_audit,
    ):
        result = cleanup_retention_data(days_retention=90)

    assert result["telemetry_purged"] == 42
    assert result["audit_files_purged"] == 5
    mock_telemetry.assert_called_once_with(days_retention=90)
    mock_audit.assert_called_once_with(retention_days=90)
