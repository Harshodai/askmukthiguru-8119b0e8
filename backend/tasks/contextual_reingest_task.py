"""Celery task for contextual re-ingestion of spiritual_wisdom into _contextual."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from celery import Task

from celery_config import celery_app, update_job_progress

logger = logging.getLogger(__name__)


class AsyncTask(Task):
    """Async helper for Celery tasks — mirrors tasks.ingest_tasks.AsyncTask."""

    _loop: Optional[asyncio.AbstractEventLoop] = None

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = kwargs.get("job_id") if kwargs else None
        if job_id:
            update_job_progress(job_id, "failed", error_message=str(exc))
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
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
    retry_jitter=True,
    queue="ingestion",
)
def contextual_reingest(
    self,
    source_url: Optional[str] = None,
    limit: Optional[int] = None,
    skip_processed: bool = True,
    job_id: Optional[str] = None,
) -> dict[str, Any]:
    """Re-ingest existing source(s) into the contextual Qdrant collection."""
    self.update_state(state="STARTED", meta={"stage": "contextual_reingest"})
    if job_id:
        update_job_progress(job_id, "running", progress_pct=10)

    try:
        from ingest.contextual_reingest import ContextualReingestEngine

        engine = ContextualReingestEngine()
        result = self.run_async(
            engine.reingest(
                source_url=source_url,
                limit=limit,
                skip_processed=skip_processed,
            )
        )
        if job_id:
            update_job_progress(
                job_id,
                "completed",
                progress_pct=100,
                chunks_indexed=result.get("chunks_written", 0),
            )
        self.update_state(state="SUCCESS", meta=result)
        return result
    except Exception as exc:
        logger.exception("contextual_reingest task failed")
        if job_id:
            update_job_progress(job_id, "failed", error_message=str(exc))
        raise


@celery_app.task(
    base=AsyncTask,
    bind=True,
    queue="ingestion",
)
def contextual_reingest_dry_run(
    self,
    source_url: Optional[str] = None,
    limit: int = 1,
) -> dict[str, Any]:
    """Dry-run preview for contextual re-ingestion."""
    self.update_state(state="STARTED", meta={"stage": "contextual_reingest_dry_run"})
    try:
        from ingest.contextual_reingest import ContextualReingestEngine

        engine = ContextualReingestEngine()
        result = self.run_async(engine.dry_run(source_url=source_url, limit=limit))
        self.update_state(state="SUCCESS", meta=result)
        return result
    except Exception as exc:
        logger.exception("contextual_reingest_dry_run task failed")
        raise


if __name__ == "__main__":
    print("Contextual re-ingest Celery tasks registered")
