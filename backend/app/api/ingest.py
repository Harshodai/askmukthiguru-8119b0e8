"""Content ingestion and ingestion-status routes."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

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
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import ServiceContainer, get_container_async
from app.sanitization import sanitize_log_input
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
    video_id: Optional[str] = None
    media_url: Optional[str] = None


class FederatedIngestRequest(BaseModel):
    """Federated ingestion request body."""

    source_type: str = Field(
        ..., description="youtube, pdf_doctrine, audio_archive, whatsapp_reflection, okf_staging"
    )
    source_ref: str = Field(..., description="File path, URL, or audio path")
    chunker_version: str = Field(
        default="boundary_v1:adaptive", description="Declared chunker version"
    )
    tags: list[str] = Field(default=["general"])


class FederatedIngestResponse(BaseModel):
    status: str
    source_type: str
    source_ref: str
    chunks_ingested: int = 0
    written_qdrant: int = 0
    written_memgraph: int = 0
    message: str = ""


@router.post("/ingest", response_model=IngestResponse)
@limiter.limit("5/minute")
async def ingest_endpoint(
    request: Request,
    ingest_body: IngestRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_aal2),
    container: ServiceContainer = Depends(get_container_async),
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

    from ingest.pipeline import is_url_safe
    from services.web_search_guardrails import check_url_safety

    url_safe, url_reason = check_url_safety(url)
    if not url_safe or not is_url_safe(url):
        reason = url_reason or "Blocked private or loopback IP address"
        raise HTTPException(
            status_code=400, detail=f"URL rejected by security guardrails: {reason}"
        )

    try:
        parsed_url = urlparse(url)
        host = (parsed_url.hostname or "").lower()
        is_yt = (
            host == "youtube.com"
            or host.endswith(".youtube.com")
            or host == "youtu.be"
            or host.endswith(".youtu.be")
        )
    except Exception:
        is_yt = False
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
    qdrant_collection: Optional[str] = Field(
        default=None,
        description="Write to this Qdrant collection instead of the live default "
        "(settings.qdrant_collection) — for isolated testing without touching "
        "what production chat retrieves from.",
    )


MAX_RAW_TEXT_CHARS = 2_000_000  # ~2MB of text — a single video transcript is a few KB-100KB


@router.post("/ingest/raw-text", response_model=IngestResponse)
@limiter.limit("120/minute")
async def ingest_raw_text_endpoint(
    request: Request,
    body: RawTextIngestRequest,
    user: dict = Depends(require_aal2),
    container: ServiceContainer = Depends(get_container_async),
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
        # Idempotency check: match on idempotency_key (content + collection +
        # pipeline version), not source_url alone -- source_url-only matching
        # meant a single successful job permanently blocked any reprocessing
        # of that URL, even with different content or a different target
        # collection. Needs supabase/migrations/20260823130000_... applied;
        # falls back to the old source_url-only behavior until it is, so this
        # doesn't break ingestion if the migration hasn't run yet.
        if body.idempotency_key:
            try:
                existing = (
                    container.supabase_client.table("ingest_jobs")
                    .select("id, status")
                    .eq("idempotency_key", body.idempotency_key)
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
            except Exception as e:
                logger.debug(
                    f"idempotency_key lookup failed (migration not applied yet?), "
                    f"falling back to source_url-only check: {e}"
                )
                try:
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
                                message=f"Already processed (source_url match): {source_url}",
                                source_url=source_url,
                                job_id=row.get("id"),
                            )
                except Exception as e2:
                    logger.warning(f"Idempotency check failed entirely: {e2}")

        try:
            insert_payload = {
                "source_url": source_url,
                "status": "pending",
                "progress_pct": 0,
                "idempotency_key": body.idempotency_key,
            }
            try:
                resp = (
                    container.supabase_client.table("ingest_jobs").insert(insert_payload).execute()
                )
            except Exception:
                insert_payload.pop("idempotency_key", None)
                resp = (
                    container.supabase_client.table("ingest_jobs").insert(insert_payload).execute()
                )
            if resp.data:
                job_id = resp.data[0]["id"]
        except Exception as e:
            logger.warning(f"Failed to create job in Supabase: {e}")

    from tasks.ingest_tasks import ingest_document_task

    dispatch_kwargs = {"task_id": job_id} if job_id else {}
    ingest_document_task.apply_async(
        args=[text, source_url, title, tag_list, body.max_accuracy, job_id, speaker],
        kwargs={"qdrant_collection": body.qdrant_collection},
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
    container: ServiceContainer = Depends(get_container_async),
    _tenant=Depends(set_tenant_from_request),
) -> IngestResponse:
    """Upload a PDF directly (no public URL required) and ingest it (Admin only)."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")

    # Bounded read: read one byte past the limit so we can detect over-size without
    # buffering the entire upload.  Same pattern as chat.py:83.
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400, detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit"
        )
    # Magic-byte gate: PDF files must start with %PDF (\x25\x50\x44\x46).
    # The suffix check above can be bypassed by renaming any file to .pdf;
    # this check ensures we only pass genuine PDF bytes to the parser.
    _PDF_MAGIC = b"%PDF"
    if not content[:4] == _PDF_MAGIC:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")

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


MAX_VIDEO_UPLOAD_BYTES = 500 * 1024 * 1024  # 500MB


def _video_storage_dir() -> str:
    """Where uploaded videos are saved: the persisted volume in Docker, else ./backend/data."""
    video_dir = "/app/data/videos"
    if not os.path.exists(video_dir):
        video_dir = os.path.join(os.getcwd(), "backend", "data", "videos")
        os.makedirs(video_dir, exist_ok=True)
    return video_dir


def _write_bytes(path: str, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)


def _resolve_video_file_path(video_id: str) -> Optional[str]:
    """Resolve physical path of a video file by ID across local and docker mount locations."""
    token = video_id.split(".")[0].strip()
    if not re.fullmatch(r"^[A-Za-z0-9_-]{1,64}$", token):
        return None
    safe_id = token

    candidate_dirs = [
        "/app/data/videos",
        os.path.join(os.getcwd(), "backend", "data", "videos"),
        os.path.join(os.getcwd(), "data", "videos"),
    ]
    extensions = [".mp4", ".webm", ".mov", ".mkv"]

    for d in candidate_dirs:
        real_d = os.path.realpath(d)
        for ext in extensions:
            candidate = os.path.realpath(os.path.join(real_d, f"{safe_id}{ext}"))
            if (
                os.path.commonpath([real_d, candidate]) == real_d
                and os.path.isfile(candidate)
                and os.path.getsize(candidate) > 0
            ):
                return candidate
    return None


def _parse_byte_range(header: str, size: int) -> Optional[tuple[int, int]]:
    """Parse one RFC 7233 byte range into inclusive ``(start, end)``.

    Returns None when the header is not a single ``bytes=`` range (the caller then serves
    the whole file, which RFC 7233 allows). Raises ValueError when the range cannot be
    satisfied (the caller answers 416).
    """
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not match:
        return None
    first, last = match.groups()
    if first == "" and last == "":
        return None
    if first == "":  # suffix range: the last N bytes
        count = int(last)
        if count == 0 or size == 0:
            raise ValueError("unsatisfiable suffix range")
        return max(size - count, 0), size - 1
    start = int(first)
    if start >= size or (last != "" and int(last) < start):
        raise ValueError("unsatisfiable range")
    end = size - 1 if last == "" else min(int(last), size - 1)
    return start, end


@router.get("/media/videos/{video_id}")
async def stream_video_endpoint(
    video_id: str,
    request: Request,
):
    """
    Stream a direct uploaded video with HTTP 206 Partial Content support for seeking (Public).
    Supports HTML5 <video controls> and range headers.
    """
    if not re.fullmatch(r"^[A-Za-z0-9_.-]{1,64}$", video_id.strip()):
        raise HTTPException(status_code=400, detail="Invalid video ID")

    file_path = _resolve_video_file_path(video_id)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found")

    # Serving governance: an admin-excluded video is not streamable either. Same 404 as a
    # missing file so the endpoint does not reveal which ids exist but are excluded.
    from services.first_person_video_decisions import video_is_blocked

    if video_is_blocked(os.path.splitext(os.path.basename(file_path))[0]):
        raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found")

    file_size = os.path.getsize(file_path)
    content_type = "video/mp4"
    if file_path.endswith(".webm"):
        content_type = "video/webm"
    elif file_path.endswith(".mov"):
        content_type = "video/quicktime"
    elif file_path.endswith(".mkv"):
        content_type = "video/x-matroska"

    range_header = request.headers.get("range")
    if range_header:
        try:
            byte_range = _parse_byte_range(range_header, file_size)
        except ValueError:
            raise HTTPException(
                status_code=416,
                detail="Requested range not satisfiable",
                headers={"Content-Range": f"bytes */{file_size}"},
            )
        if byte_range is not None:
            start, end = byte_range
            content_length = end - start + 1

            def iter_file():
                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk_size = min(64 * 1024, remaining)
                        data = f.read(chunk_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": content_type,
            }
            return StreamingResponse(iter_file(), status_code=206, headers=headers)

    return FileResponse(
        file_path,
        media_type=content_type,
        headers={"Accept-Ranges": "bytes"},
    )


@router.post("/ingest/upload-video", response_model=IngestResponse)
@limiter.limit("10/minute")
async def ingest_upload_video_endpoint(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    speaker: str = Form("Sri Preethaji & Sri Krishnaji"),
    tags: str = Form("general"),
    max_accuracy: bool = Form(True),
    user: dict = Depends(require_aal2),
    container: ServiceContainer = Depends(get_container_async),
    _tenant=Depends(set_tenant_from_request),
) -> IngestResponse:
    """
    Direct video file upload (.mp4, .mov, .webm, .mkv) with automatic audio extraction,
    ASR transcription, complete-thought chunking, and dual Qdrant + Memgraph persistence (Admin only).
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    filename = file.filename or "upload.mp4"
    valid_exts = (".mp4", ".mov", ".webm", ".mkv")
    if not any(filename.lower().endswith(ext) for ext in valid_exts):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format '{filename}'. Supported extensions: {list(valid_exts)}",
        )

    content = await file.read(MAX_VIDEO_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded video file is empty")
    if len(content) > MAX_VIDEO_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum video limit of {MAX_VIDEO_UPLOAD_BYTES // (1024 * 1024)}MB",
        )

    # Deterministic video_id from content SHA-256
    video_id = hashlib.sha256(content).hexdigest()[:11]
    resolved_title = (
        title.strip() or filename.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").title()
    )
    tag_list = list({t.strip().lower() for t in tags.split(",") if t.strip()}) or ["general"]

    video_dir = _video_storage_dir()

    file_ext = os.path.splitext(filename)[1].lower() or ".mp4"
    video_save_path = os.path.join(video_dir, f"{video_id}{file_ext}")
    # Blocking disk and ffmpeg work runs off the event loop so one upload cannot stall
    # /api/chat and the health checks (L-DOCKER-18).
    await asyncio.to_thread(_write_bytes, video_save_path, content)

    # Extract audio to 16kHz mono WAV for Whisper / ECAPA
    wav_save_path = os.path.join(video_dir, f"{video_id}.wav")
    try:
        extraction = await asyncio.to_thread(
            subprocess.run,
            [
                "ffmpeg",
                "-y",
                "-i",
                video_save_path,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                wav_save_path,
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        if extraction.returncode != 0:
            # The pipeline below extracts its own audio, so ingestion continues, but a
            # failed archive copy must be visible (it used to be dropped silently).
            logger.warning(
                "Audio archive extraction failed for %s (ffmpeg exit %s)",
                video_id,
                extraction.returncode,
            )
    except Exception as exc:
        logger.warning(f"Audio extraction warning for {video_id}: {exc}")

    source_url = f"video:{video_id}"
    media_url = f"/api/media/videos/{video_id}"

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

    try:
        from ingest.video_pipeline import VideoPipeline

        pipeline = VideoPipeline(
            qdrant_service=container.qdrant,
            embedding_service=container.embedding,
        )
        res = await pipeline.ingest_video(video_save_path)
        chunks_indexed = res.chunks_ingested

        # Stamp direct_video attributes onto exactly the points this write created.
        # The ids come from the pipeline (uuid5). Rebuilding them from
        # "video_id_index" writes to points that do not exist, which is a silent
        # no-op — that is what happened before 2026-11-01, and it left every
        # seeded video without source_type/media_url, so the direct-video player
        # could never render.
        # Rights are NOT stamped here: the pipeline already resolved them from the
        # curated register and fails closed to "unverified" (X40). Writing a
        # literal "licensed" for an arbitrary admin upload would manufacture a
        # rights claim the register never made.
        try:
            from services.qdrant.client import QdrantClientManager

            if not res.point_ids:
                logger.warning(
                    "Direct video %s: pipeline wrote no point ids; skipping payload stamp",
                    video_id,
                )
            else:
                client = QdrantClientManager().client
                client.set_payload(
                    collection_name=getattr(
                        container.settings, "qdrant_collection", "spiritual_wisdom_contextual"
                    ),
                    payload={
                        "source_type": "direct_video",
                        "media_url": media_url,
                        "video_id": video_id,
                        "title": resolved_title,
                        "speaker": speaker,
                        "tags": tag_list,
                    },
                    points=res.point_ids,
                )
                logger.info(
                    "Direct video %s: stamped %d point(s) with source_type=direct_video",
                    video_id,
                    len(res.point_ids),
                )
        except Exception as e:
            # A swallowed debug here is how the no-op survived a whole plan phase.
            logger.warning("Direct video %s: payload stamp failed: %s", video_id, e)

        # Insert video node into Memgraph
        try:
            if hasattr(container, "graph_db") and container.graph_db:
                with container.graph_db.session() as session:
                    session.run(
                        """
                        MERGE (v:Video {id: $video_id})
                        SET v.title = $title,
                            v.source_type = 'direct_video',
                            v.media_url = $media_url,
                            v.speaker = $speaker
                        MERGE (t:Teacher {name: $speaker})
                        MERGE (t)-[:SPEAKER_OF]->(v)
                        """,
                        video_id=video_id,
                        title=resolved_title,
                        media_url=media_url,
                        speaker=speaker,
                    )
        except Exception as e:
            logger.debug(f"Memgraph node merge: {e}")

        if job_id and container.supabase_client:
            try:
                container.supabase_client.table("ingest_jobs").update(
                    {"status": "completed", "progress_pct": 100}
                ).eq("id", job_id).execute()
            except Exception:
                pass

        return IngestResponse(
            status="success",
            message=f"Direct video '{filename}' successfully ingested ({chunks_indexed} chunks indexed).",
            source_url=source_url,
            job_id=job_id,
            chunks_indexed=chunks_indexed,
            video_id=video_id,
            media_url=media_url,
        )
    except Exception as e:
        logger.error(f"Direct video ingestion error for {filename}: {e}", exc_info=True)
        # No fallback ingest. The old path queued a made-up sentence ("Direct video
        # recording: <title> by <speaker>") as a corpus chunk attributed to the teachers and
        # answered "processing", which hid the failure and put non-teaching text in the
        # corpus. A failed ingest is reported as failed.
        if job_id and container.supabase_client:
            try:
                container.supabase_client.table("ingest_jobs").update(
                    {"status": "failed", "error_message": type(e).__name__}
                ).eq("id", job_id).execute()
            except Exception as job_exc:
                logger.warning("Could not mark ingest job %s failed: %s", job_id, job_exc)
        raise HTTPException(
            status_code=502,
            detail=f"Video ingestion failed ({type(e).__name__}). The upload was saved as {video_id}.",
        ) from e


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
    container: ServiceContainer = Depends(get_container_async),
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
    container: ServiceContainer = Depends(get_container_async),
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
        logger.debug(
            "Supabase lookup for task %s failed: %s",
            sanitize_log_input(task_id),
            type(e).__name__,
        )

    return resp


_FEDERATED_PATH_TYPES = ("pdf_doctrine", "audio_archive", "okf_staging")
_YOUTUBE_REF_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _validate_federated_source(source_type: str, source_ref: str) -> str:
    """Return a safe source_ref or raise 400. Path types must live under the allowlisted dir."""
    if source_type == "youtube":
        if not _YOUTUBE_REF_RE.match(source_ref):
            raise HTTPException(
                status_code=400, detail="youtube source_ref must be an 11-character video id"
            )
        return source_ref
    if source_type in _FEDERATED_PATH_TYPES:
        allowed = (settings.federated_ingest_allowed_dir or "").strip()
        if not allowed:
            raise HTTPException(
                status_code=400, detail="No federated ingest directory is configured"
            )
        if "\0" in source_ref or ".." in source_ref:
            raise HTTPException(
                status_code=400, detail="source_ref contains invalid path components"
            )
        root_path = Path(allowed).resolve()
        raw_path = Path(source_ref)
        if raw_path.is_absolute():
            target_path = raw_path.resolve()
        else:
            target_path = (root_path / raw_path).resolve()

        root_str = str(root_path)
        target_str = str(target_path)
        if not target_path.is_relative_to(root_path) or os.path.commonpath([root_str, target_str]) != root_str or not target_path.is_file():
            raise HTTPException(
                status_code=400, detail="source_ref must be a file inside the allowed directory"
            )
        return target_str
    raise HTTPException(status_code=400, detail="Unsupported source_type for this route")


@router.post("/ingest/federated", response_model=FederatedIngestResponse)
@limiter.limit("10/minute")
async def ingest_federated_endpoint(
    request: Request,
    body: FederatedIngestRequest,
    user: dict = Depends(require_aal2),
    container: ServiceContainer = Depends(get_container_async),
    _tenant=Depends(set_tenant_from_request),
) -> FederatedIngestResponse:
    """
    Federated multi-data source ingestion endpoint (Admin only).
    Routes to FederatedDataSourceIngestionEngine with pluggable adapters
    and atomic dual-write to Qdrant (vectors) and Memgraph C++ (knowledge graph).
    """
    # Off by default: before this check the route answers as if it did not exist.
    if not settings.federated_ingest_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    source_ref = _validate_federated_source(body.source_type, body.source_ref)

    from ingest.federated_engine import FederatedDataSourceIngestionEngine

    qdrant_svc = getattr(container, "qdrant_indexer", None) or getattr(container, "qdrant", None)
    memgraph_drv = getattr(container, "memgraph_driver", None)

    engine = FederatedDataSourceIngestionEngine(
        qdrant_service=qdrant_svc,
        memgraph_driver=memgraph_drv,
    )

    try:
        # Blocking fetch/embed/write work stays off the event loop.
        result = await asyncio.to_thread(
            engine.ingest_source,
            source_type=body.source_type,
            source_ref=source_ref,
            chunker_version=body.chunker_version,
        )
    except Exception:
        # Detail goes to the log only; the client gets a generic message.
        logger.exception(
            "Federated ingestion failed for %s (%s)",
            sanitize_log_input(body.source_type),
            sanitize_log_input(source_ref),
        )
        raise HTTPException(status_code=500, detail="Federated ingestion failed")

    status = result.get("status", "success")
    return FederatedIngestResponse(
        status=status,
        source_type=body.source_type,
        source_ref=body.source_ref,
        chunks_ingested=result.get("chunks_ingested", 0),
        written_qdrant=result.get("written_qdrant", 0),
        written_memgraph=result.get("written_memgraph", 0),
        message=(
            "Federated ingestion completed successfully"
            if status == "success"
            else f"Federated ingestion {status}: {result.get('reason', 'nothing ingested')}"
        ),
    )
