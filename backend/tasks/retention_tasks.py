"""Periodic data retention cleanup tasks for Celery Beat (AMK-C-003, AMK-C-004)."""

from __future__ import annotations

import logging

from celery_config import celery_app

logger = logging.getLogger(__name__)


LAUNCH_SUBSCRIBER_RETENTION_MONTHS = 12  # documented on /privacy; keep both in step


def purge_launch_subscribers(
    months: int = LAUNCH_SUBSCRIBER_RETENTION_MONTHS, client: object | None = None
) -> int:
    """Call the service_role-only SQL purge for launch-update emails older than `months`."""
    if client is None:
        from supabase import create_client

        from app.config import settings

        client = create_client(
            settings.supabase_url, settings.supabase_service_key or settings.supabase_key
        )
    result = client.rpc("purge_expired_launch_subscribers", {"p_months": months}).execute()
    return int(result.data or 0)


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

    launch_subscribers_purged = 0
    try:
        launch_subscribers_purged = purge_launch_subscribers()
    except Exception:
        # Retention is a legal duty: log at error level so an alert can see it.
        logger.exception("Launch subscriber purge failed")

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
        "launch_subscribers_purged": launch_subscribers_purged,
    }
