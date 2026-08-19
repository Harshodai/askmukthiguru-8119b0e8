"""Specialized Celery tasks for the ingestion pipeline.

Task types routed to separate queues:
  1. orchestrate_ingestion — full pipeline coordinator with job tracking
  2. ingest_playlist — playlist/channel ingestion via Celery chord
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from celery import Task
from httpx import HTTPError

from app.config import settings
from celery_config import celery_app, update_job_progress

logger = logging.getLogger(__name__)

# Only transient transport failures are automatically retried. Deterministic
# parse, quality, schema, authorization, and validation failures must surface to
# the job/DLQ instead of replaying partial writes indefinitely.
RETRYABLE_INGEST_ERRORS = (
    TimeoutError,
    ConnectionError,
    OSError,
    HTTPError,
)


def classify_ingest_error(error: BaseException) -> str:
    """Classify a failed ingestion as 'no_speech' | 'permanent' | 'transient'.

    Mirrors scripts/ingestion/bulk_ingest_async.py's classify_error so both
    ingestion paths (host script and Celery task) bucket the same DLQ the
    same way. no_speech and permanent are not worth auto-retrying; only
    transient (network/rate-limit/timeout-shaped) errors are.
    """
    msg = str(error).lower()
    if "no speech detected" in msg:
        return "no_speech"
    permanent_signals = [
        "extraction failed",
        "no transcript",
        "private video",
        "video unavailable",
        "has been removed",
        "does not exist",
        "sign in to confirm",
    ]
    for sig in permanent_signals:
        if sig in msg:
            return "permanent"
    return "transient"


class AsyncTask(Task):
    """Base task with async support via asyncio.run() and failed-job tracking."""

    _loop: Optional[asyncio.AbstractEventLoop] = None

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = (kwargs.get("job_id") or kwargs.get("parent_job_id")) if kwargs else None
        if job_id is None and args:
            # Extract job_id from positional args using each task's documented signature.
            # Celery strips `self` for bound tasks, so indices are 0-based excluding self.
            #
            #   orchestrate_ingestion(video_url, language, metadata, job_id, tags, …) → args[3]
            #   ingest_playlist(playlist_url, language, tags, job_id)                → args[3]
            #   playlist_complete(results, playlist_url, parent_job_id, total_count) → args[2]
            #
            # Use self.name to avoid ambiguity; fall back to None rather than
            # scanning and risking a serialised metadata/tags string being used.
            task_name = self.name or ""
            if "playlist_complete" in task_name:
                candidate = args[2] if len(args) > 2 else None
            else:
                # orchestrate_ingestion and ingest_playlist both put job_id at index 3
                candidate = args[3] if len(args) > 3 else None
            if isinstance(candidate, str) and candidate:
                job_id = candidate
        if job_id:
            category = classify_ingest_error(exc)
            update_job_progress(job_id, "failed", error_message=f"[{category}] {exc}")
        super().on_failure(exc, task_id, args, kwargs, einfo)

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop

    def run_async(self, coro):
        return self.loop.run_until_complete(coro)


@celery_app.task(
    base=AsyncTask,
    bind=True,
    autoretry_for=RETRYABLE_INGEST_ERRORS,
    retry_kwargs={"max_retries": 1},
    retry_backoff=True,
    retry_jitter=True,
)
def ingest_book_task(
    self,
    json_path: str,
    collection: str,
    job_id: str = None,
) -> dict[str, Any]:
    """Ingest a PageIndex-JSON book into Qdrant + LightRAG + OKF (see ingest/book_ingest.py).

    Runs inside celery-worker so LightRAG can reach Neo4j over the internal
    Railway network -- the host-side scripts/ingestion/bulk_ingest_async.py
    path can only reach the public Qdrant proxy, not Neo4j's bolt port.
    """
    logger.info(f"Ingesting book: {json_path} -> {collection}")
    if job_id:
        update_job_progress(job_id, "running", progress_pct=10, worker_id=self.request.hostname)

    from ingest.book_ingest import ingest_book

    result = self.run_async(ingest_book(json_path, collection))

    if job_id:
        update_job_progress(job_id, "completed", progress_pct=100)
    logger.info(f"Book ingestion done: {result}")
    return result


@celery_app.task(
    base=AsyncTask,
    bind=True,
    autoretry_for=RETRYABLE_INGEST_ERRORS,
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_jitter=True,
)
def orchestrate_ingestion(
    self,
    video_url: str,
    language: str = "en",
    metadata: Optional[dict[str, Any]] = None,
    job_id: str = None,
    tags: Optional[list[str]] = None,
    max_accuracy: bool = True,
) -> dict[str, Any]:
    """Orchestrate the full ingestion pipeline using the unified IngestionPipeline."""
    logger.info(f"Orchestrating ingestion for: {video_url}")

    if job_id:
        update_job_progress(job_id, "running", progress_pct=10, worker_id=self.request.hostname)

    self.update_state(state="STARTED", meta={"progress_pct": 5, "stage": "fetching"})

    try:
        from app.dependencies import get_container

        container = get_container()

        # Define progress callback
        def progress_cb(msg: str, pct: float):
            if job_id:
                # Map 0.0-1.0 to 10-90% progress
                progress_pct = int(10 + pct * 80)
                update_job_progress(job_id, "running", progress_pct=progress_pct)

        # Run the unified pipeline
        # Run async function in Celery's event loop
        result = self.run_async(
            container.ingestion.ingest_url(
                video_url,
                max_accuracy=max_accuracy,
                on_progress=progress_cb,
                tags=tags or ["general"],
            )
        )

        if isinstance(result, dict) and result.get("status") == "error":
            raise RuntimeError(result.get("message", "Ingestion failed"))

        chunks_indexed = 0
        if isinstance(result, dict):
            chunks_indexed = result.get("chunks_indexed", result.get("chunks_added", 0))

        if job_id:
            update_job_progress(
                job_id, "completed", progress_pct=100, chunks_indexed=chunks_indexed
            )

        # Invalidate response cache after successful ingestion
        try:
            container.exact_cache.invalidate_all()
            container.semantic_cache.invalidate_all()
        except Exception as cache_e:
            logger.warning(f"Failed to invalidate cache: {cache_e}")

        return {
            "status": "success",
            "video_url": video_url,
            "indexing": {"count": chunks_indexed},
            "result": result,
        }
    except Exception as exc:
        logger.error(f"Orchestration failed for {video_url}: {exc}")
        raise


@celery_app.task(
    base=AsyncTask,
    bind=True,
    autoretry_for=RETRYABLE_INGEST_ERRORS,
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
    retry_jitter=True,
)
def ingest_document_task(
    self,
    text: str,
    source_url: str,
    title: str,
    tags: Optional[list[str]] = None,
    max_accuracy: bool = False,
    job_id: str = None,
    speaker: str = "Unknown",
) -> dict[str, Any]:
    """Ingest already-extracted document text (e.g. an uploaded PDF or local transcript) through the
    full pipeline: hierarchical chunking, embed, Qdrant, RAPTOR, LightRAG, OKF."""
    logger.info(f"Ingesting uploaded document: {source_url} (Speaker: {speaker})")

    if job_id:
        update_job_progress(job_id, "running", progress_pct=10, worker_id=self.request.hostname)

    def progress_cb(msg: str, pct: float):
        if job_id:
            update_job_progress(job_id, "running", progress_pct=int(10 + pct * 80))

    try:
        from app.dependencies import get_container

        container = get_container()

        result = self.run_async(
            container.ingestion.ingest_raw_text(
                text=text,
                source_url=source_url,
                title=title,
                speaker=speaker or "Unknown",
                content_type="document",
                max_accuracy=max_accuracy,
                on_progress=progress_cb,
                tags=tags or ["general"],
            )
        )

        if isinstance(result, dict) and result.get("status") == "error":
            raise RuntimeError(result.get("message", "Ingestion failed"))

        chunks_indexed = result.get("chunks_indexed", 0) if isinstance(result, dict) else 0

        if job_id:
            update_job_progress(
                job_id, "completed", progress_pct=100, chunks_indexed=chunks_indexed
            )

        try:
            container.exact_cache.invalidate_all()
            container.semantic_cache.invalidate_all()
        except Exception as cache_e:
            logger.warning(f"Failed to invalidate cache: {cache_e}")

        return {
            "status": "success",
            "source_url": source_url,
            "indexing": {"count": chunks_indexed},
            "result": result,
        }
    except Exception as exc:
        logger.error(f"Document ingestion failed for {source_url}: {exc}")
        if job_id:
            update_job_progress(job_id, "failed", error_message=str(exc))
        raise


@celery_app.task(
    base=AsyncTask,
    bind=True,
    autoretry_for=RETRYABLE_INGEST_ERRORS,
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
    retry_jitter=True,
)
def ingest_playlist(
    self,
    playlist_url: str,
    language: str = "en",
    tags: Optional[list[str]] = None,
    job_id: str = None,
    max_accuracy: bool = True,
) -> dict[str, Any]:
    """Process a playlist: extract video URLs, create ingest_jobs for each, and chain them as a Celery chord."""
    from celery import chord
    from supabase import create_client

    from ingest.youtube_loader import get_playlist_video_urls

    logger.info(f"Extracting playlist videos for URL: {playlist_url}")
    if job_id:
        update_job_progress(job_id, "running", progress_pct=10, worker_id=self.request.hostname)

    self.update_state(state="STARTED", meta={"progress_pct": 5, "stage": "extracting_playlist"})

    videos = get_playlist_video_urls(playlist_url)
    if not videos:
        err_msg = "No videos found in playlist or failed to extract."
        logger.error(err_msg)
        if job_id:
            update_job_progress(job_id, "failed", error_message=err_msg)
        return {"status": "failed", "error": err_msg}

    child_tasks = []
    supabase_client = None
    key = settings.supabase_service_key or settings.supabase_key
    if settings.supabase_url and key:
        try:
            supabase_client = create_client(settings.supabase_url, key)
        except Exception as e:
            logger.warning(f"Could not init Supabase in ingest_playlist: {e}")

    for _idx, video in enumerate(videos):
        child_job_id = None
        if supabase_client:
            try:
                resp = (
                    supabase_client.table("ingest_jobs")
                    .insert(
                        {
                            "source_url": video["url"],
                            "status": "pending",
                            "progress_pct": 0,
                        }
                    )
                    .execute()
                )
                if resp.data:
                    child_job_id = resp.data[0]["id"]
            except Exception as e:
                logger.warning(f"Failed to create child job record: {e}")

        metadata = {
            "title": video.get("title", "Unknown"),
            "speaker": video.get("speaker", "Unknown"),
            "topic": video.get("topic", "Spiritual"),
        }
        child_tasks.append(
            orchestrate_ingestion.signature(
                args=[video["url"]],
                kwargs={
                    "language": language,
                    "metadata": metadata,
                    "job_id": child_job_id,
                    "tags": tags,
                    "max_accuracy": max_accuracy,
                },
            )
        )

    callback = playlist_complete.s(
        playlist_url=playlist_url, parent_job_id=job_id, total_count=len(videos)
    )
    chord(child_tasks)(callback)

    return {
        "status": "queued",
        "video_count": len(videos),
        "message": f"Queued chord with {len(videos)} videos.",
    }


@celery_app.task(
    base=AsyncTask,
    bind=True,
    autoretry_for=RETRYABLE_INGEST_ERRORS,
    retry_kwargs={"max_retries": 1},
)
def post_ingestion_maintenance(self, trigger: str = "playlist_complete") -> dict[str, Any]:
    """Dedup Neo4j entities and audit cross-store data quality after an ingestion batch.

    Runs scripts/ops/consolidate_entities.py (--execute) and ruthless_data_audit.py as
    subprocesses against the live env — same scripts previously run manually after each
    ingestion push. Fired once per playlist/batch completion, not per video: both scripts
    scan the whole graph, so running them after every single video would be wasteful.
    """
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    runs = {
        "consolidate_entities": [
            sys.executable,
            "scripts/ops/consolidate_entities.py",
            "--execute",
        ],
        "ruthless_data_audit": [sys.executable, "scripts/ops/ruthless_data_audit.py"],
    }
    results: dict[str, Any] = {}
    for name, cmd in runs.items():
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=900)
        results[name] = {
            "returncode": proc.returncode,
            "tail": proc.stdout[-3000:] or proc.stderr[-3000:],
        }
        if proc.returncode != 0:
            logger.warning(
                f"post_ingestion_maintenance: {name} exited {proc.returncode}: {proc.stderr[-1000:]}"
            )

    logger.info(f"post_ingestion_maintenance ({trigger}) complete: {results}")
    return results


@celery_app.task(
    base=AsyncTask,
    bind=True,
    autoretry_for=RETRYABLE_INGEST_ERRORS,
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
    retry_jitter=True,
)
def playlist_complete(
    self, results, playlist_url: str, parent_job_id: str = None, total_count: int = 0
) -> dict[str, Any]:
    """Called when all orchestrate_ingestion tasks in the playlist chord finish."""
    success_count = 0
    fail_count = 0
    rejected_count = 0
    indexed_chunks = 0

    for r in results:
        if not r:
            fail_count += 1
            continue
        status = r.get("status")
        if status == "success":
            success_count += 1
            indexed_chunks += r.get("indexing", {}).get("count", 0)
        elif status == "rejected":
            rejected_count += 1
        else:
            fail_count += 1

    msg = f"Playlist ingestion completed: {success_count}/{total_count} succeeded, {rejected_count} rejected by quality gate, {fail_count} failed."
    logger.info(msg)

    if success_count > 0:
        post_ingestion_maintenance.delay(trigger="playlist_complete")

    if parent_job_id:
        status_str = "completed" if fail_count == 0 else "failed"
        update_job_progress(
            parent_job_id,
            status_str,
            progress_pct=100,
            chunks_indexed=indexed_chunks,
            error_message=None if fail_count == 0 else msg,
        )

    return {
        "status": "success",
        "playlist_url": playlist_url,
        "total": total_count,
        "success": success_count,
        "rejected": rejected_count,
        "failed": fail_count,
        "chunks_indexed": indexed_chunks,
    }
