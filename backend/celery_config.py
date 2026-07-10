"""Celery Configuration for Mukthi Guru.

Distributed task queue for ingestion pipeline:
  - transcription: YouTube video → text
  - embedding: text → vector embeddings
  - indexing: vectors → Qdrant
  - ingestion: full pipeline orchestration

Requires Redis (already in docker-compose.yml) as broker + backend.
"""

from __future__ import annotations

import os

from celery import Celery
from kombu import Exchange, Queue

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "mukthi_guru",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks.ingest_tasks", "tasks.okf_extract_tasks", "tasks.okf_compile_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_max_tasks_per_child=10,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_soft_time_limit=1800,
    task_time_limit=2400,
    # Exponential backoff on retry: 2^retry_count * base_delay
    task_acks_on_failure_or_timeout=True,
)

# Queue routing by task type
task_queues = (
    Queue("transcription", Exchange("ingestion"), routing_key="transcription"),
    Queue("embedding", Exchange("ingestion"), routing_key="embedding"),
    Queue("indexing", Exchange("ingestion"), routing_key="indexing"),
    Queue("ingestion", Exchange("ingestion"), routing_key="ingestion"),
    Queue("okf", Exchange("ingestion"), routing_key="okf"),
)

celery_app.conf.task_queues = task_queues

celery_app.conf.task_routes = {
    "tasks.ingest_tasks.transcribe_video": {"queue": "transcription"},
    "tasks.ingest_tasks.embed_chunks": {"queue": "embedding"},
    "tasks.ingest_tasks.index_vectors": {"queue": "indexing"},
    "tasks.ingest_tasks.orchestrate_ingestion": {"queue": "ingestion"},
    "tasks.ingest_tasks.ingest_playlist": {"queue": "ingestion"},
    "tasks.ingest_tasks.playlist_complete": {"queue": "ingestion"},
    "tasks.okf_compile_tasks.compile_okf_index": {"queue": "okf"},
    "tasks.okf_extract_tasks.extract_okf_entries": {"queue": "okf"},
}


@celery_app.task(bind=True)
def health_check(self) -> dict:
    return {
        "status": "healthy",
        "worker": self.request.hostname,
        "broker": REDIS_URL,
    }


# ---- Ingest job progress tracking (PostgreSQL via Supabase) ----

def update_job_progress(job_id: str, status: str, progress_pct: int = 0, chunks_indexed: int = 0, error_message: str = None, worker_id: str = None) -> None:
    """Update ingest_jobs row. Best-effort — failures are logged, not raised."""
    try:
        from app.config import settings
        if not settings.supabase_url or not settings.supabase_key:
            return
        from supabase import create_client
        client = create_client(settings.supabase_url, settings.supabase_key)

        updates = {"status": status, "progress_pct": progress_pct, "chunks_indexed": chunks_indexed}
        if status == "running" and progress_pct == 0:
            updates["started_at"] = "now()"
        if status in ("completed", "failed"):
            updates["completed_at"] = "now()"
        if error_message:
            updates["error_message"] = error_message
        if worker_id:
            updates["worker_id"] = worker_id

        client.table("ingest_jobs").update(updates).eq("id", job_id).execute()
    except Exception as e:
        # Don't fail the task — progress tracking is non-critical
        import logging
        logging.getLogger(__name__).warning(f"Job progress update failed for {job_id}: {e}")


def retry_backoff(self, exc: Exception) -> None:
    """Exponential backoff: 2^retry * base_delay (30s max)."""
    import math
    delay = min(2 ** self.request.retries * 5, 30)
    raise self.retry(exc=exc, countdown=delay)