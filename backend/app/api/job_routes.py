from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import ServiceContainer, get_container
from services.auth_service import get_optional_user, require_scoped_identity, resolve_anon_identity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


def _owns_job(job: dict, user: dict) -> bool:
    owner = str(job.get("user_id") or "")
    uid = str(user.get("id") or "")
    return bool(owner) and bool(uid) and owner == uid


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    request: Request,
    container: ServiceContainer = Depends(get_container),
    user: dict = Depends(get_optional_user),
):
    """Poll job status and result. Only the job owner may read."""
    if not container.job_queue:
        raise HTTPException(status_code=503, detail="Job tracking is not available.")
    session_id: Optional[str] = request.headers.get("X-Session-Id")
    user = resolve_anon_identity(user, session_id)
    require_scoped_identity(user)
    job = await container.job_queue.get_job(job_id)
    owner = str(job.get("user_id") or "") if job else ""
    uid = str(user.get("id") or "")
    if job is None or not (bool(owner) and bool(uid) and owner == uid):
        # Return 404 on mismatch to avoid confirming existence.
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return job


@router.delete("/{job_id}")
async def cancel_job(
    job_id: str,
    request: Request,
    container: ServiceContainer = Depends(get_container),
    user: dict = Depends(get_optional_user),
):
    """Cancel a queued job. Only the job owner may cancel."""
    if not container.job_queue:
        raise HTTPException(status_code=503, detail="Job tracking is not available.")
    session_id: Optional[str] = request.headers.get("X-Session-Id")
    user = resolve_anon_identity(user, session_id)
    require_scoped_identity(user)
    job = await container.job_queue.get_job(job_id)
    owner = str(job.get("user_id") or "") if job else ""
    uid = str(user.get("id") or "")
    if job is None or not (bool(owner) and bool(uid) and owner == uid):
        raise HTTPException(status_code=404, detail="Job not found or already processing")
    cancelled = await container.job_queue.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Job not found or already processing")
    # A cancelled chat job never reaches the worker, so its anonymous-quota
    # reservation (made at the endpoint gate) must be returned here.
    request_data = await container.job_queue.get_request_data(job_id)
    reservation_id = request_data.get("quota_reservation_id")
    if reservation_id:
        try:
            await container.anon_quota_service.release(request_data.get("user", {}), reservation_id)
        except Exception as exc:
            logger.warning(f"anon quota release on job cancel failed (non-fatal): {exc}")
    return {"status": "cancelled", "job_id": job_id}
