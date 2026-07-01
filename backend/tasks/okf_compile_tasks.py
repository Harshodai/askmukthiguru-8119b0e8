"""Celery task: recompile the OKF compiled index from memory/okf/ markdown.

Routed to the `okf` queue. Reuses services.memory.compiler.compile_okf — no
re-implementation. Triggered by the admin UI (POST /api/admin/okf/compile) or
by a watchdog watcher (future)."""

from __future__ import annotations

import logging

from celery_config import celery_app
from services.memory.compiler import compile_okf

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.okf_compile_tasks.compile_okf_index")
def compile_okf_index(self) -> dict:
    """Rebuild memory/okf/compiled.json from the OKF markdown entries.

    Returns the compiled index path. Idempotent — safe to re-run on change.
    """
    try:
        path = compile_okf()
        logger.info("OKF compiled via Celery: %s", path)
        return {"status": "ok", "path": str(path)}
    except Exception as exc:  # ponytail: surface error to caller, no silent swallow
        logger.exception("OKF compile failed")
        self.retry(exc=exc, countdown=10, max_retries=2)