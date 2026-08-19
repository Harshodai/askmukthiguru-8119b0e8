"""Content ingestion and ingestion-status routes."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from pydantic import BaseModel, Field

from app.core.limiter import limiter
from app.dependencies import ServiceContainer, get_container
from app.security_utils import is_valid_youtube_url
from ingest.image_loader import is_image_url
from services.auth_service import require_aal2
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
    user: dict = Depends(require_aal2),
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
        raise HTTPException(
            status_code=400, detail=f"URL rejected by security guardrails: {url_reason}"
        )

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
                resp = (
                    container.supabase_client.table("ingest_jobs")
                    .insert(
                        {
                            "source_url": url,
                            "status": "pending",
                            "progress_pct": 0,
                        }
                    )
                    .execute()
                )
                if resp.data:
                    job_id = resp.data[0]["id"]
            except Exception as e:
                logger.warning(f"Failed to create parent job in Supabase: {e}")

        from tasks.ingest_tasks import ingest_playlist

        # Pass job_id as Celery task_id so /ingest/status/{task_id} can match ingest_jobs.id
        dispatch_kwargs = {"task_id": job_id} if job_id else {}
        ingest_playlist.apply_async(
            args=[url, "en", tags, job_id, ingest_body.max_accuracy], **dispatch_kwargs
        )
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
            resp = (
                container.supabase_client.table("ingest_jobs")
                .insert(
                    {
                        "source_url": url,
                        "status": "pending",
                        "progress_pct": 0,
                    }
                )
                .execute()
            )
            if resp.data:
                job_id = resp.data[0]["id"]
        except Exception as e:
            logger.warning(f"Failed to create job in Supabase: {e}")

    from tasks.ingest_tasks import orchestrate_ingestion

    # Pass job_id as Celery task_id so /ingest/status/{task_id} can match ingest_jobs.id
    dispatch_kwargs = {"task_id": job_id} if job_id else {}
    orchestrate_ingestion.apply_async(
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


class RawTextIngestRequest(BaseModel):
    """Body for submitting already-fetched text (e.g. a transcript fetched
    locally, off Railway's blocked/rate-limited IP) for the rest of the
    pipeline: chunk, embed, Qdrant, RAPTOR, LightRAG, OKF."""

    text: str = Field(..., description="Already-fetched raw text (transcript, article, etc.)")
    source_url: str = Field(..., description="Original source URL — used for dedup/citation")
    title: str = Field(default="", description="Title for the content")
    speaker: str = Field(default="Sri Preethaji & Sri Krishnaji", description="Speaker attribution")
    tags: list[str] = Field(default=["general"])
    max_accuracy: bool = Field(default=True)
    quality_state: str = Field(
        default="trusted", description="Quality state: must be 'trusted' or 'trusted_after_review'"
    )
    transcript_hash: Optional[str] = Field(
        default=None, description="SHA-256 hash of transcript text"
    )
    artifact_manifest_hash: Optional[str] = Field(
        default=None, description="Corpus artifact manifest hash"
    )
    pipeline_version: str = Field(default="2.0.0", description="Pipeline version")
    idempotency_key: Optional[str] = Field(
        default=None, description="Idempotency key: sha256(canonical_json(video_id, hash, version))"
    )


MAX_RAW_TEXT_CHARS = 2_000_000  # ~2MB of text — a single video transcript is a few KB-100KB


@router.post("/ingest/raw-text", response_model=IngestResponse)
@limiter.limit("120/minute")
async def ingest_raw_text_endpoint(
    request: Request,
    body: RawTextIngestRequest,
    user: dict = Depends(require_aal2),
    container: ServiceContainer = Depends(get_container),
    _tenant=Depends(set_tenant_from_request),
) -> IngestResponse:
    """Ingest pre-fetched text directly — the receiving half of a split
    pipeline where transcript-fetching runs locally (residential IP, not
    subject to Railway's datacenter-IP bot-block) and the rest of the
    pipeline (chunk/embed/Qdrant/RAPTOR/LightRAG/OKF) runs here. Admin only."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Hard Quality Gate: Reject untrusted transcripts
    if body.quality_state not in ["trusted", "trusted_after_review"]:
        raise HTTPException(
            status_code=400,
            detail=f"Untrusted quality state '{body.quality_state}'. Only 'trusted' or 'trusted_after_review' transcripts may be ingested.",
        )

    import unicodedata

    text = (body.text or "").replace("\x00", "")
    text = unicodedata.normalize("NFC", text).strip()
    if not text:
        raise HTTPException(status_code=400, detail="text cannot be empty")
    if len(text) > MAX_RAW_TEXT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"text exceeds {MAX_RAW_TEXT_CHARS // 1_000_000}MB limit",
        )

    source_url = body.source_url.strip()
    if not source_url:
        raise HTTPException(status_code=400, detail="source_url cannot be empty")

    title = body.title.strip() or source_url
    speaker = (body.speaker or "Sri Preethaji & Sri Krishnaji").strip()
    tag_list = list({t.strip().lower() for t in body.tags if t and t.strip()}) or ["general"]

    job_id = None
    if container.supabase_client:
        try:
            # Idempotency check: look up existing job with matching source_url
            if body.idempotency_key:
                existing = (
                    container.supabase_client.table("ingest_jobs")
                    .select("id, status")
                    .eq("source_url", source_url)
                    .execute()
                )
                for row in getattr(existing, "data", []) or []:
                    if row.get("status") in ["success", "completed"]:
                        return IngestResponse(
                            status="already_processed",
                            message=f"Already processed via idempotency key: {body.idempotency_key}",
                            source_url=source_url,
                            job_id=row.get("id"),
                        )

            resp = (
                container.supabase_client.table("ingest_jobs")
                .insert(
                    {
                        "source_url": source_url,
                        "status": "pending",
                        "progress_pct": 0,
                    }
                )
                .execute()
            )
            if resp.data:
                job_id = resp.data[0]["id"]
        except Exception as e:
            logger.warning(f"Failed to create job in Supabase: {e}")

    from tasks.ingest_tasks import ingest_document_task

    dispatch_kwargs = {"task_id": job_id} if job_id else {}
    ingest_document_task.apply_async(
        args=[text, source_url, title, tag_list, body.max_accuracy, job_id, speaker],
        **dispatch_kwargs,
    )

    return IngestResponse(
        status="processing",
        message=f"Raw text ingestion queued via Celery. Job ID: {job_id or 'N/A'}",
        source_url=source_url,
        job_id=job_id,
    )


MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB


@router.post("/ingest/upload", response_model=IngestResponse)
@limiter.limit("5/minute")
async def ingest_upload_endpoint(
    request: Request,
    file: UploadFile = File(...),
    max_accuracy: bool = Form(False),
    tags: str = Form("general"),
    user: dict = Depends(require_aal2),
    container: ServiceContainer = Depends(get_container),
    _tenant=Depends(set_tenant_from_request),
) -> IngestResponse:
    """Upload a PDF directly (no public URL required) and ingest it (Admin only)."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400, detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit"
        )

    import io

    from pypdf import PdfReader

    try:
        with PdfReader(io.BytesIO(content)) as doc:
            pages_text = [
                (p.extract_text() or "").strip()
                for p in doc.pages
                if (p.extract_text() or "").strip()
            ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse PDF: {e}")

    text = "\n\n".join(pages_text).replace("\x00", "")
    text = unicodedata.normalize("NFC", text).strip()
    if not text:
        raise HTTPException(status_code=400, detail="PDF contains no readable text")

    title = filename.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").title()
    tag_list = list({t.strip().lower() for t in tags.split(",") if t.strip()}) or ["general"]
    source_url = f"upload:{filename}"

    job_id = None
    if container.supabase_client:
        try:
            resp = (
                container.supabase_client.table("ingest_jobs")
                .insert(
                    {
                        "source_url": source_url,
                        "status": "pending",
                        "progress_pct": 0,
                    }
                )
                .execute()
            )
            if resp.data:
                job_id = resp.data[0]["id"]
        except Exception as e:
            logger.warning(f"Failed to create job in Supabase: {e}")

    from tasks.ingest_tasks import ingest_document_task

    dispatch_kwargs = {"task_id": job_id} if job_id else {}
    ingest_document_task.apply_async(
        args=[text, source_url, title, tag_list, max_accuracy, job_id],
        **dispatch_kwargs,
    )

    return IngestResponse(
        status="processing",
        message=f"Document ingestion queued via Celery. Job ID: {job_id or 'N/A'}",
        source_url=source_url,
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
    user: dict = Depends(require_aal2),
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
    user: dict = Depends(require_aal2),
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
            db = (
                container.supabase_client.table("ingest_jobs")
                .select("*")
                .eq("id", task_id)
                .execute()
            )
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
