"""Content ingestion and ingestion-status routes."""

from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import ServiceContainer, get_container
from app.security_utils import is_valid_youtube_url
from app.telemetry_db import log_ingestion_run
from ingest.image_loader import is_image_url
from services.auth_service import get_current_user_from_supabase
from services.tenant_context import set_tenant_from_request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Ingestion"])


class IngestRequest(BaseModel):
    """Ingestion API request body."""

    url: str = Field(..., description="YouTube video/playlist URL or image URL")
    max_accuracy: bool = Field(
        default=False,
        description="If True, skip auto-generated captions (T3) and rely on Manual (T1) or Whisper (T2)",
    )
    tags: list[str] = Field(
        default=["general"],
        description="Knowledge tags to attach to every indexed chunk",
    )


class IngestResponse(BaseModel):
    """Ingestion API response body."""

    status: str
    message: str = ""
    source_url: str = ""
    job_id: Optional[str] = None
    chunks_indexed: int = 0
    summaries_created: int = 0


@router.post("/ingest", response_model=IngestResponse)
@limiter.limit("5/minute")
async def ingest_endpoint(
    request: Request,
    ingest_body: IngestRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
    _tenant=Depends(set_tenant_from_request),
) -> IngestResponse:
    """
    Content ingestion endpoint (Admin only).
    Accepts YouTube video/playlist URLs and image URLs.
    Runs ingestion in the background so the API responds immediately.
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    url = ingest_body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    from services.web_search_guardrails import check_url_safety

    url_safe, url_reason = check_url_safety(url)
    if not url_safe:
        raise HTTPException(status_code=400, detail=f"URL rejected by security guardrails: {url_reason}")

    is_yt = "youtube.com" in url or "youtu.be" in url
    if is_yt:
        if not is_valid_youtube_url(url):
            raise HTTPException(status_code=400, detail="Invalid YouTube URL format.")
    elif is_image_url(url):
        if not re.match(r"^https?://[a-zA-Z0-9_.:/?=&%#-]+$", url) or len(url) > 250:
            raise HTTPException(status_code=400, detail="Invalid image URL format.")
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported URL format. Only YouTube and image URLs are supported.",
        )

    from ingest.youtube_loader import is_playlist_url

    tags = list({t.strip().lower() for t in ingest_body.tags if t and t.strip()})
    tags = tags or ["general"]

    if is_yt and is_playlist_url(url):
        job_id = None
        if container.supabase_client:
            try:
                resp = container.supabase_client.table("ingest_jobs").insert({
                    "source_url": url,
                    "status": "pending",
                    "progress_pct": 0,
                }).execute()
                if resp.data:
                    job_id = resp.data[0]["id"]
            except Exception as e:
                logger.warning(f"Failed to create parent job in Supabase: {e}")

        from tasks.ingest_tasks import ingest_playlist
        # Pass job_id as Celery task_id so /ingest/status/{task_id} can match ingest_jobs.id
        dispatch_kwargs = {"task_id": job_id} if job_id else {}
        task = ingest_playlist.apply_async(args=[url, "en", tags, job_id], **dispatch_kwargs)
        return IngestResponse(
            status="processing",
            message=f"Playlist ingestion queued via Celery. Job ID: {job_id or 'N/A'}",
            source_url=url,
            job_id=job_id,
        )

    # For single video/media, queue it directly to Celery instead of running as BackgroundTasks.
    # We can use the orchestrate_ingestion task.
    job_id = None
    if container.supabase_client:
        try:
            resp = container.supabase_client.table("ingest_jobs").insert({
                "source_url": url,
                "status": "pending",
                "progress_pct": 0,
            }).execute()
            if resp.data:
                job_id = resp.data[0]["id"]
        except Exception as e:
            logger.warning(f"Failed to create job in Supabase: {e}")

    from tasks.ingest_tasks import orchestrate_ingestion
    # Pass job_id as Celery task_id so /ingest/status/{task_id} can match ingest_jobs.id
    dispatch_kwargs = {"task_id": job_id} if job_id else {}
    task = orchestrate_ingestion.apply_async(
        args=[url, "en", None, job_id, tags],
        kwargs={"max_accuracy": ingest_body.max_accuracy},
        **dispatch_kwargs,
    )

    return IngestResponse(
        status="processing",
        message=f"Ingestion queued via Celery. Job ID: {job_id or 'N/A'}",
        source_url=url,
        job_id=job_id,
    )


class IngestStatusResponse(BaseModel):
    """Task status polling response."""

    task_id: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[int] = None
    stage: Optional[str] = None
    error: Optional[str] = None
    job_id: Optional[str] = None


@router.get("/ingest/status")
async def ingest_status_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """
    Get the status of active/recent ingestion jobs (Admin only).
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return container.ingestion_tracker.get_all()


@router.get("/ingest/status/{task_id}", response_model=IngestStatusResponse)
async def ingest_task_status_endpoint(
    task_id: str,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> IngestStatusResponse:
    """
    Poll a single Celery task's status by task ID (Admin only).
    Returns task state from Celery, enriched with Supabase job data if available.
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    from celery_config import celery_app

    result = celery_app.AsyncResult(task_id)
    resp = IngestStatusResponse(
        task_id=task_id,
        status=result.state,
        progress=None,
        stage=None,
        error=None,
        job_id=None,
    )

    if result.state == "STARTED" and isinstance(result.info, dict):
        resp.progress = result.info.get("progress_pct", result.info.get("progress"))
        resp.stage = result.info.get("stage")

    if result.state == "FAILURE":
        resp.error = str(result.result) if result.result else "Unknown error"

    # DB status → Celery vocabulary mapping
    _DB_STATUS_MAP = {
        "running": "STARTED",
        "completed": "SUCCESS",
        "failed": "FAILURE",
        "pending": "PENDING",
    }

    try:
        if container.supabase_client:
            db = container.supabase_client.table("ingest_jobs").select("*").eq("id", task_id).execute()
            if db.data:
                row = db.data[0]
                resp.job_id = row.get("id")
                if resp.progress is None:
                    resp.progress = row.get("progress_pct")
                resp.stage = row.get("stage") or resp.stage
                resp.error = row.get("error_message") or resp.error
                db_status = row.get("status")
                # Only let the DB override Celery when Celery is still non-terminal.
                # Never downgrade a resolved SUCCESS or FAILURE to a stale DB state.
                _CELERY_TERMINAL = {"SUCCESS", "FAILURE"}
                if db_status and result.state not in _CELERY_TERMINAL:
                    resp.status = _DB_STATUS_MAP.get(db_status, resp.status)
    except Exception as e:
        logger.debug(f"Supabase lookup for task {task_id} failed: {e}")

    return resp
