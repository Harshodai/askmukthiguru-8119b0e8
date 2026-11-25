"""Periodic data retention cleanup tasks for Celery Beat (AMK-C-003, AMK-C-004)."""

from __future__ import annotations

import logging
from collections.abc import Callable

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
def cleanup_retention_data(
    days_retention: int = 90, days_inactivity: int = 365
) -> dict[str, int]:
    """Run every scheduled retention surface documented in ``RETENTION.md``.

    Each surface is isolated so one unavailable dependency does not prevent the
    remaining legal-retention jobs from running. Failed surfaces return zero and
    are logged; the task result keeps per-surface counts for operational alerts.
    ``corpus_gate_rejections`` is intentionally absent because X40 requires its
    rejection ledger to remain recorded.
    """
    from scripts.ops.cleanup_inactive_user_data import (
        cleanup_anonymous_session_summaries,
        cleanup_redis_keys,
        cleanup_stale_qdrant_memories,
        cleanup_staging_quality_queue,
        cleanup_telemetry_logs,
    )
    from services.compliance_logger import cleanup_compliance_audit_files

    counts: dict[str, int] = {}

    def run_surface(name: str, fn: Callable[..., int], **kwargs: object) -> None:
        try:
            counts[name] = int(fn(**kwargs))
        except Exception as exc:
            counts[name] = 0
            logger.warning("Retention surface %s failed: %s", name, exc)

    run_surface("redis_keys_purged", cleanup_redis_keys)
    run_surface(
        "qdrant_memory_vectors_purged",
        cleanup_stale_qdrant_memories,
        days_inactivity=days_inactivity,
    )
    run_surface("telemetry_purged", cleanup_telemetry_logs, days_retention=days_retention)
    run_surface(
        "anonymous_session_summaries_purged",
        cleanup_anonymous_session_summaries,
    )
    run_surface(
        "audit_files_purged",
        cleanup_compliance_audit_files,
        retention_days=days_retention,
    )
    run_surface(
        "staging_purged",
        cleanup_staging_quality_queue,
        days_retention=days_retention,
    )

    try:
        counts["launch_subscribers_purged"] = purge_launch_subscribers()
    except Exception as exc:
        counts["launch_subscribers_purged"] = 0
        # Retention is a legal duty: log at error level so an alert can see it.
        logger.exception("Launch subscriber purge failed: %s", exc)

    # corpus_gate_rejections is deliberately NOT purged here: X40 requires every
    # rejected item to stay recorded (reason, tier, source coordinates). Any
    # future expiry must archive first; it is not an automatic retention job.

    logger.info(
        "Data retention cleanup finished: %s (telemetry_retention=%dd, inactivity=%dd)",
        counts,
        days_retention,
        days_inactivity,
    )
    return counts
