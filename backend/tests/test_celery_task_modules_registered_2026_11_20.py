"""Every tasks/ module that defines a Celery task must be in celery_app's include list.

A @shared_task in a module the worker never imports is "unregistered": the
producer (e.g. app/api/admin.py -> tasks.web_ingest_tasks.ingest_url_task)
enqueues it and the worker rejects it. Found by the 2026-11-20 wiring audit.
"""

from pathlib import Path

import celery_config

_TASK_DECORATORS = ("@shared_task", "@celery_app.task")


def test_every_task_module_is_included():
    tasks_dir = Path(__file__).resolve().parents[1] / "tasks"
    defining = {
        f"tasks.{p.stem}"
        for p in tasks_dir.glob("*.py")
        if any(d in p.read_text(encoding="utf-8") for d in _TASK_DECORATORS)
    }
    missing = defining - set(celery_config.celery_app.conf.include)
    assert not missing, f"task modules the worker never imports: {sorted(missing)}"
