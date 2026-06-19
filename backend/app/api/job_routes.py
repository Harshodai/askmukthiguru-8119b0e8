from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import ServiceContainer, get_container

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    container: ServiceContainer = Depends(get_container),
):
    """Poll job status and result."""
    if not container.job_queue:
        raise HTTPException(status_code=503, detail="Job queue is disabled")
    job = await container.job_queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return job


@router.delete("/{job_id}")
async def cancel_job(
    job_id: str,
    container: ServiceContainer = Depends(get_container),
):
    """Cancel a queued job."""
    if not container.job_queue:
        raise HTTPException(status_code=503, detail="Job queue is disabled")
    cancelled = await container.job_queue.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Job not found or already processing")
    return {"status": "cancelled", "job_id": job_id}
