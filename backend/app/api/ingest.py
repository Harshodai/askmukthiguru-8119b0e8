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
        task = ingest_playlist.delay(url, "en", tags, job_id)
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
    # Queue single video ingestion to Celery
    task = orchestrate_ingestion.delay(
        url,
        "en",
        None,  # metadata
        job_id,
        tags,
        max_accuracy=ingest_body.max_accuracy,
    )

    return IngestResponse(
        status="processing",
        message=f"Ingestion queued via Celery. Job ID: {job_id or 'N/A'}",
        source_url=url,
        job_id=job_id,
    )


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
