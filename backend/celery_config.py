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
    include=["tasks.ingest_tasks"],
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
    task_soft_time_limit=600,
    task_time_limit=900,
)

# Queue routing by task type
task_queues = (
    Queue("transcription", Exchange("ingestion"), routing_key="transcription"),
    Queue("embedding", Exchange("ingestion"), routing_key="embedding"),
    Queue("indexing", Exchange("ingestion"), routing_key="indexing"),
    Queue("ingestion", Exchange("ingestion"), routing_key="ingestion"),
)

celery_app.conf.task_queues = task_queues

celery_app.conf.task_routes = {
    "tasks.ingest_tasks.transcribe_video": {"queue": "transcription"},
    "tasks.ingest_tasks.embed_chunks": {"queue": "embedding"},
    "tasks.ingest_tasks.index_vectors": {"queue": "indexing"},
    "tasks.ingest_tasks.orchestrate_ingestion": {"queue": "ingestion"},
}


@celery_app.task(bind=True)
def health_check(self) -> dict:
    return {
        "status": "healthy",
        "worker": self.request.hostname,
        "broker": REDIS_URL,
    }