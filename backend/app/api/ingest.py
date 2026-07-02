"""Content ingestion and ingestion-status routes."""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
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


# ── Supported file types for direct upload ───────────────────────────────────

_ALLOWED_EXTENSIONS = {
    ".pdf", ".txt", ".csv", ".docx", ".pptx", ".xlsx",
    ".mp3", ".wav", ".m4a",         # audio
    ".mp4", ".mkv", ".mov", ".avi",  # video
    ".jpg", ".jpeg", ".png", ".webp",  # images
}
_MAX_UPLOAD_MB = 500  # 500 MB limit


@router.post("/ingest/upload")
@limiter.limit("3/minute")
async def ingest_file_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Content file to ingest (PDF, DOCX, MP4, MP3, JPG, PNG, etc.)"),
    tags: str = Form(default="general", description="Comma-separated knowledge tags"),
    max_accuracy: bool = Form(default=False, description="Use Whisper/enhanced transcription for audio/video"),
    guru_slug: str = Form(default="default", description="Guru collection slug (e.g. preethaji_krishnaji)"),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
    _tenant=Depends(set_tenant_from_request),
) -> dict:
    """
    Direct file upload for ingestion (Admin only).

    Supports: PDF, DOCX, PPTX, XLSX, TXT, CSV, MP3, WAV, M4A, MP4, MKV, JPG, PNG.
    Saves to temp dir, runs ingestion in background, returns immediately with job ID.
    Quality gate (Iceberg-style) runs before any content reaches Qdrant/Neo4j/LightRAG.
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    # Read and size-check
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > _MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Max allowed: {_MAX_UPLOAD_MB} MB.",
        )

    # Parse tags
    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
    tag_list = tag_list or ["general"]
    if guru_slug and guru_slug != "default":
        tag_list = list(set(tag_list + [guru_slug]))

    # Save to temp file (background task reads from here)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="mukthi_upload_")
    tmp.write(content)
    tmp.flush()
    tmp_path = tmp.name
    tmp.close()

    original_filename = file.filename
    logger.info(f"Upload received: {original_filename} ({size_mb:.1f} MB) → {tmp_path}")

    async def _run_upload_ingestion():
        start_time = time.time()
        chunks_added = 0
        status = "ok"
        error_log = None

        def progress_callback(msg: str, pct: float):
            container.update_progress(original_filename, msg, pct, tags=tag_list)

        try:
            container.update_progress(original_filename, "Starting file ingestion...", 0.0, tags=tag_list)

            result = await container.ingestion.ingest_file(
                file_path=tmp_path,
                max_accuracy=max_accuracy,
                on_progress=progress_callback,
            )
            logger.info(f"File ingestion complete: {original_filename} → {result}")
            container.update_progress(original_filename, "Complete!", 1.0)

            if isinstance(result, dict):
                chunks_added = result.get("chunks_indexed", result.get("chunks_added", 0))
                if result.get("status") == "rejected":
                    status = "partial"
                    error_log = result.get("message", "Quality gate rejected content")

            # Invalidate caches after new content
            container.exact_cache.invalidate_all()
            container.semantic_cache.invalidate_all()

        except Exception as e:
            logger.error(f"File ingestion failed for {original_filename}: {e}", exc_info=True)
            status = "failed"
            error_log = str(e)
            container.ingestion_tracker.mark_error(original_filename, str(e), tags=tag_list)
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            duration_ms = int((time.time() - start_time) * 1000)
            try:
                await log_ingestion_run({
                    "id": str(uuid.uuid4()),
                    "source": original_filename,
                    "chunks_added": chunks_added,
                    "embedding_model": settings.embedding_model,
                    "duration_ms": duration_ms,
                    "status": status,
                    "error_log": error_log,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as db_e:
                logger.error(f"Failed to log file ingestion run: {db_e}")

    background_tasks.add_task(_run_upload_ingestion)

    return {
        "status": "processing",
        "message": f"File '{original_filename}' ({size_mb:.1f} MB) queued for ingestion.",
        "filename": original_filename,
        "size_mb": round(size_mb, 2),
        "tags": tag_list,
    }


# ── Staging quality queue routes ─────────────────────────────────────────────

@router.get("/ingest/staging")
async def get_staging_queue(
    status: str = "pending",
    limit: int = 50,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """List content that failed quality gate and is staged for human review (Admin only)."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    if not getattr(container, "supabase_client", None):
        return []

    try:
        result = await __import__("asyncio").to_thread(
            lambda: container.supabase_client.table("staging_quality_queue")
            .select("*")
            .eq("status", status)
            .order("created_at", desc=True)
            .limit(min(limit, 200))
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"Staging queue fetch failed: {e}")
        return []


class StagingReviewRequest(BaseModel):
    action: str  # "approve" | "reject"
    notes: str = ""


@router.patch("/ingest/staging/{staging_id}")
async def review_staging_item(
    staging_id: str,
    body: StagingReviewRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> dict:
    """Approve or reject a staged content item (Admin only).
    Approve → triggers re-ingestion bypassing quality gate.
    Reject → marks as permanently rejected.
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    if not getattr(container, "supabase_client", None):
        raise HTTPException(status_code=503, detail="Database not available")

    import asyncio as _asyncio
    from datetime import datetime, timezone

    # Fetch the item
    try:
        result = await _asyncio.to_thread(
            lambda: container.supabase_client.table("staging_quality_queue")
            .select("*")
            .eq("id", staging_id)
            .single()
            .execute()
        )
        item = result.data
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Staging item not found: {e}")

    if not item:
        raise HTTPException(status_code=404, detail="Staging item not found")

    new_status = "approved" if body.action == "approve" else "rejected"

    # Update status in Supabase
    await _asyncio.to_thread(
        lambda: container.supabase_client.table("staging_quality_queue")
        .update({
            "status": new_status,
            "reviewer_notes": body.notes,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "reviewed_by": user.get("id"),
        })
        .eq("id", staging_id)
        .execute()
    )

    # If approved → re-ingest the source URL bypassing quality gate
    if body.action == "approve" and item.get("source_url"):
        async def _force_reingest():
            try:
                # Temporarily disable quality gate for approved content
                container.ingestion._quality_gate._enabled = False
                result = await container.ingestion.ingest_url(
                    item["source_url"], max_accuracy=True
                )
                container.ingestion._quality_gate._enabled = True
                logger.info(f"Force re-ingested approved staging item {staging_id}: {result}")
            except Exception as exc:
                container.ingestion._quality_gate._enabled = True
                logger.error(f"Force re-ingest failed for staging {staging_id}: {exc}")

        background_tasks.add_task(_force_reingest)

    return {
        "id": staging_id,
        "action": body.action,
        "new_status": new_status,
        "message": f"Item {body.action}d. Re-ingestion queued." if body.action == "approve" else "Item rejected.",
    }
