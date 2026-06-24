"""Content ingestion and ingestion-status routes."""

from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import ServiceContainer, get_container
from app.security_utils import is_valid_youtube_url
from app.telemetry_db import log_ingestion_run
from ingest.image_loader import is_image_url
from services.auth_service import get_current_user_from_supabase

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

    # Run ingestion in the background for large content
    async def _run_ingestion():
        start_time = time.time()
        chunks_added = 0
        status = "ok"
        error_log = None

        tags = list({t.strip().lower() for t in ingest_body.tags if t and t.strip()})
        tags = tags or ["general"]

        def progress_callback(msg: str, pct: float):
            container.update_progress(url, msg, pct, tags=tags)

        try:
            # Init tracker
            container.update_progress(url, "Starting...", 0.0, tags=tags)

            result = await container.ingestion.ingest_url(
                url,
                max_accuracy=ingest_body.max_accuracy,
                on_progress=progress_callback,
                tags=tags,
            )
            logger.info(f"Ingestion complete: {result}")
            container.update_progress(url, "Complete!", 1.0)

            if isinstance(result, dict):
                chunks_added = result.get("chunks_indexed", result.get("chunks_added", 0))

            # Invalidate response cache after new content ingestion
            container.exact_cache.invalidate_all()
            container.semantic_cache.invalidate_all()

        except Exception as e:
            logger.error(f"Ingestion failed for {url}: {e}", exc_info=True)
            status = "failed"
            error_log = str(e)
            # Mark as error
            container.ingestion_tracker.mark_error(url, str(e), tags=tags)
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            try:
                await log_ingestion_run(
                    {
                        "id": str(uuid.uuid4()),
                        "source": url,
                        "chunks_added": chunks_added,
                        "embedding_model": settings.embedding_model,
                        "duration_ms": duration_ms,
                        "status": status,
                        "error_log": error_log,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            except Exception as db_e:
                logger.error(f"Failed to log ingestion run in background task: {db_e}")

    background_tasks.add_task(_run_ingestion)

    return IngestResponse(
        status="processing",
        message=f"Ingestion started for: {url}",
        source_url=url,
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
