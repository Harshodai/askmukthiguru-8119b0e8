"""Worker-side Celery metrics (NEW-OPS-7, OPS-006).

The worker serves only /api/healthz, and Prometheus scrapes only the backend. So
the worker writes its facts to Redis (the broker's database) and the backend
re-exports them at scrape time (app/ops_gauges.py):

- `RESULT_HASH`: field `<task>|<success|failure|retry>` -> count;
- `BEAT_KEY`: time the `beat_heartbeat` task last ran. Beat dispatches it every
  30 s, so the value proves beat AND a worker are both alive.

Every write is best effort. A Redis outage must never fail or slow a task.
"""

from __future__ import annotations

import logging
import time

import redis
from celery.signals import task_failure, task_retry, task_success

import celery_config
from celery_config import celery_app

logger = logging.getLogger(__name__)

RESULT_HASH = "mukthi:celery:task_result"
BEAT_KEY = "mukthi:celery:beat_last_tick"
RESULTS = ("success", "failure", "retry")

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            celery_config.CELERY_BROKER_URL, socket_timeout=1, socket_connect_timeout=1
        )
    return _client


def record_result(task_name: str, result: str, *, client=None) -> None:
    if result not in RESULTS:
        raise ValueError(f"unknown task result: {result!r}")
    try:
        (client or _get_client()).hincrby(RESULT_HASH, f"{task_name}|{result}", 1)
    except redis.RedisError as exc:
        logger.debug("celery result metric not recorded: %s", exc)


def write_heartbeat(*, client=None, now: float | None = None) -> None:
    try:
        (client or _get_client()).set(BEAT_KEY, time.time() if now is None else now)
    except redis.RedisError as exc:
        logger.debug("celery heartbeat not recorded: %s", exc)


def _name(sender) -> str:
    return str(getattr(sender, "name", None) or "unknown")


@task_success.connect(weak=False)
def _on_success(sender=None, **_kw) -> None:
    record_result(_name(sender), "success")


@task_failure.connect(weak=False)
def _on_failure(sender=None, **_kw) -> None:
    record_result(_name(sender), "failure")


@task_retry.connect(weak=False)
def _on_retry(sender=None, **_kw) -> None:
    record_result(_name(sender), "retry")


@celery_app.task(name="tasks.celery_metrics.beat_heartbeat", ignore_result=True)
def beat_heartbeat() -> None:
    write_heartbeat()
