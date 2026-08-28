"""Celery Configuration for Mukthi Guru.

Distributed task queue for ingestion pipeline:
  - ingestion: full pipeline orchestration
  - okf: OKF knowledge extraction

Requires Redis (already in docker-compose.yml) as broker + backend.
"""

from __future__ import annotations

import os

# Apply thread-count caps (OMP/MKL/BLIS/OpenBLAS) before any heavy import.
# configure_threading() is also called from app/main.py for the uvicorn process;
# this copy covers the Celery worker process path. Idempotent — safe to call twice.
from app.core.threading_config import configure_threading

configure_threading()

from celery import Celery
from kombu import Exchange, Queue

def _derive_celery_url(base_url: str) -> str:
    """Ensure Celery uses DB 1 if default DB 0 was supplied in REDIS_URL."""
    if "@" in base_url:
        prefix = "rediss://" if base_url.startswith("rediss://") else "redis://"
        parts = base_url.split("@", 1)
        auth_part = parts[0].replace(prefix, "")
        if ":" in auth_part:
            username, password = auth_part.split(":", 1)
            if username == "default":
                base_url = f"{prefix}:{password}@{parts[1]}"
    if base_url.endswith("/0"):
        return base_url[:-2] + "/1"
    return base_url


CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL") or _derive_celery_url(
    os.environ.get("REDIS_URL", "redis://localhost:6379/1")
)
# Local dev: run .delay() calls synchronously in the backend process itself,
# no separate celery-worker container needed. Off by default -- Railway
# production still wants the real async worker split.
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"


celery_app = Celery(
    "mukthi_guru",
    broker=CELERY_BROKER_URL,
    backend=CELERY_BROKER_URL,
    include=[
        "tasks.ingest_tasks",
        "tasks.layered_memory_tasks",
        "tasks.memory_outbox_tasks",
        "tasks.okf_extract_tasks",
        "tasks.okf_compile_tasks",
        "tasks.cancel_flow_tasks",
        "tasks.contextual_reingest_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=CELERY_TASK_ALWAYS_EAGER,
    # Recycle ingestion children both by task count and RSS. Celery expects
    # this value in kilobytes; 1.5 GB bounds model/client high-water marks
    # without affecting the parent worker process.
    worker_max_tasks_per_child=10,
    worker_max_memory_per_child=1_500_000,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 3600},
    task_track_started=True,
    task_soft_time_limit=1800,
    task_time_limit=2400,
    # True: with task_acks_late=True, acknowledge exhausted-retry tasks so they are
    # not redelivered indefinitely. Transient worker crashes are handled by
    # task_reject_on_worker_lost=True; transient errors are retried via autoretry_for.
    # NOTE: This option is deprecated in Celery 6.0 — remove when upgrading.
    task_acks_on_failure_or_timeout=True,
    # Celery Beat — daily dispatch of due win-back emails (Task B3a).
    beat_schedule={
        "dispatch-due-win-back-emails": {
            "task": "tasks.cancel_flow_tasks.dispatch_due_win_back_emails",
            "schedule": 86400.0,  # every 24h
        },
        "process-batched-layered-memories": {
            "task": "tasks.layered_memory_tasks.process_batched_memories",
            "schedule": 300.0,  # every 5 minutes
        },
        "drain-memory-outbox": {
            "task": "tasks.memory_outbox_tasks.drain_memory_outbox",
            "schedule": 60.0,
        },
    },
)

# Queue routing by task type
task_queues = (
    Queue("ingestion", Exchange("ingestion"), routing_key="ingestion"),
    Queue("okf", Exchange("ingestion"), routing_key="okf"),
    Queue("memory", Exchange("memory"), routing_key="memory"),
)

celery_app.conf.task_queues = task_queues

celery_app.conf.task_routes = {
    "tasks.ingest_tasks.orchestrate_ingestion": {"queue": "ingestion"},
    "tasks.ingest_tasks.ingest_document_task": {"queue": "ingestion"},
    "tasks.ingest_tasks.ingest_playlist": {"queue": "ingestion"},
    "tasks.ingest_tasks.playlist_complete": {"queue": "ingestion"},
    "tasks.okf_compile_tasks.compile_okf_index": {"queue": "okf"},
    "tasks.okf_extract_tasks.extract_okf_entries": {"queue": "okf"},
    "tasks.memory_outbox_tasks.drain_memory_outbox": {"queue": "memory"},
}


@celery_app.task(bind=True)
def health_check(self) -> dict:
    return {
        "status": "healthy",
        "worker": self.request.hostname,
        "broker": REDIS_URL,
    }


# ---- Ingest job progress tracking (PostgreSQL via Supabase) ----


def update_job_progress(
    job_id: str,
    status: str,
    progress_pct: int = 0,
    chunks_indexed: int = 0,
    error_message: str = None,
    worker_id: str = None,
) -> None:
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
    delay = min(2**self.request.retries * 5, 30)
    raise self.retry(exc=exc, countdown=delay)
