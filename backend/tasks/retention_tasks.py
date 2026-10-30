"""Periodic data retention cleanup tasks for Celery Beat (AMK-C-003, AMK-C-004)."""

from __future__ import annotations

import logging

from celery_config import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.retention_tasks.cleanup_retention_data")
def cleanup_retention_data(days_retention: int = 90) -> dict[str, int]:
    """Purge expired Supabase telemetry/chat logs and local compliance audit files."""
    from scripts.ops.cleanup_inactive_user_data import cleanup_telemetry_logs
    from services.compliance_logger import cleanup_compliance_audit_files

    telemetry_purged = 0
    audit_files_purged = 0
    staging_purged = 0

    try:
        telemetry_purged = cleanup_telemetry_logs(days_retention=days_retention)
    except Exception as e:
        logger.warning("Telemetry cleanup failed: %s", e)

    try:
        audit_files_purged = cleanup_compliance_audit_files(retention_days=days_retention)
    except Exception as e:
        logger.warning("Compliance audit files cleanup failed: %s", e)

    try:
        from scripts.ops.cleanup_inactive_user_data import cleanup_staging_quality_queue

        staging_purged = cleanup_staging_quality_queue(days_retention=days_retention)
    except Exception as e:
        logger.warning("Staging queue cleanup failed: %s", e)

    # corpus_gate_rejections is deliberately NOT purged here: X40 requires every
    # rejected item to stay recorded (reason, tier, source coordinates). Any
    # future expiry must archive first; it is not an automatic retention job.

    logger.info(
        "Data retention cleanup finished: %d telemetry rows, %d audit files, %d staging rows purged (retention=%dd)",
        telemetry_purged,
        audit_files_purged,
        staging_purged,
        days_retention,
    )
    return {
        "telemetry_purged": telemetry_purged,
        "audit_files_purged": audit_files_purged,
        "staging_purged": staging_purged,
    }
