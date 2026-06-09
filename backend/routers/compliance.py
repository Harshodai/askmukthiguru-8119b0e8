"""
Unit 24 — Compliance Router

Provides admin-only endpoints for compliance and audit log operations.

Endpoints:
  GET /api/compliance/audit/sessions/{user_id}  — List audit sessions for GDPR requests
  GET /api/compliance/audit/stats               — Aggregate stats (record count, date range)
  DELETE /api/compliance/audit/sessions/{user_id} — Mark data deletion request (GDPR Art. 17)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import get_container
from services.auth_service import get_current_user_from_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/compliance", tags=["compliance"])


def _require_admin(user: dict = Depends(get_current_user_from_supabase)) -> dict:
    """Gate: only superusers can access compliance endpoints."""
    if not user.get("is_superuser"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/audit/sessions/{user_id}")
async def get_audit_sessions(
    user_id: str,
    days: int = 30,
    _admin: dict = Depends(_require_admin),
):
    """Return all audit records for a specific user (GDPR Art. 17 data export).

    Prompts are returned as SHA-256 hashes only — no plaintext is exposed.
    """
    container = get_container()
    records = container.compliance_logger.list_sessions_for_user(user_id, days=days)
    return {
        "user_id": user_id,
        "days_queried": days,
        "record_count": len(records),
        "records": records,
    }


@router.get("/audit/stats")
async def get_audit_stats(_admin: dict = Depends(_require_admin)):
    """Return high-level stats from audit logs (record count per day)."""
    import os
    from pathlib import Path

    from services.compliance_logger import _AUDIT_FILE_PREFIX, _DEFAULT_AUDIT_DIR

    audit_dir = Path(os.environ.get("COMPLIANCE_AUDIT_DIR", str(_DEFAULT_AUDIT_DIR)))
    stats = []
    if audit_dir.exists():
        for path in sorted(audit_dir.glob(f"{_AUDIT_FILE_PREFIX}_*.jsonl")):
            try:
                line_count = sum(1 for _ in path.open("r", encoding="utf-8"))
                stats.append({"date": path.stem.replace(f"{_AUDIT_FILE_PREFIX}_", ""), "records": line_count})
            except OSError:
                continue
    return {"files": stats, "total_files": len(stats)}


@router.delete("/audit/sessions/{user_id}")
@limiter.limit(settings.registration_rate_limit)
async def request_data_deletion(
    user_id: str,
    _admin: dict = Depends(_require_admin),
):
    """Record a GDPR Art. 17 data deletion request for a user.

    This endpoint logs the deletion intent. Actual purging of Qdrant/Neo4j data
    should be handled by the offline retention policy script
    (scripts/gdpr_purge.py, not yet implemented).
    """
    container = get_container()
    # Log the deletion request itself as an audit event
    container.compliance_logger.write_record(
        {
            "ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "action": "gdpr_deletion_request",
            "user_id": user_id,
            "status": "pending",
            "note": "Deletion of user data requested by admin. Offline purge required.",
        }
    )
    return {
        "status": "deletion_request_logged",
        "user_id": user_id,
        "message": (
            "Deletion intent recorded. Run scripts/gdpr_purge.py "
            "to complete the offline purge of user data."
        ),
    }
