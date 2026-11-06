"""Scrape-time gauges for Qdrant and Celery (NEW-OPS-3, NEW-OPS-7).

Prometheus scrapes only the backend. Qdrant point counts, Celery queue lengths,
the beat heartbeat and the worker's task results live elsewhere, so the backend
reads them when `/internal/metrics` is scraped. The read sits behind a TTL, a
hard timeout, and a broad-free failure path: a dependency that is down removes
its series (an absent series, not a stale value) and never fails the scrape.

Qdrant uses the read-only key. Snapshot age is NOT read here: listing snapshots
needs the write key, which the backend never holds. Backup freshness comes from
`backup_last_success_timestamp_seconds` (scripts/ops/backup_metrics.py).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import redis
from prometheus_client import REGISTRY
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.metrics import (
    CELERY_QUEUE_LENGTH,
    QDRANT_COLLECTION_POINTS_COUNT,
)

logger = logging.getLogger(__name__)

TTL_S = 30.0
FETCH_TIMEOUT_S = 3.0
# Same set as start_railway._CELERY_ALLOWED_QUEUES (a test pins both).
CELERY_QUEUES = ("ingestion", "embedding", "indexing", "okf", "memory")

RESULT_HASH = "mukthi:celery:task_result"
BEAT_KEY = "mukthi:celery:beat_last_tick"


@dataclass
class OpsSnapshot:
    points: dict[str, int | None] = field(default_factory=dict)
    queues: dict[str, int] | None = None
    beat_ts: float | None = None
    task_results: dict[tuple[str, str], int] = field(default_factory=dict)


_state: dict[str, Any] = {"at": None, "results": {}, "beat_ts": None}
_lock: asyncio.Lock | None = None


def reset_for_tests() -> None:
    _state["at"] = None
    _state["results"] = {}
    _state["beat_ts"] = None
    QDRANT_COLLECTION_POINTS_COUNT.clear()
    CELERY_QUEUE_LENGTH.clear()


def collections_to_watch(cfg) -> list[str]:
    names: list[str] = []
    for attr in ("first_person_collection", "first_person_context_collection", "qdrant_collection"):
        name = str(getattr(cfg, attr, "") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def read_points(cfg, names: list[str], *, reader: Callable | None = None) -> dict[str, int | None]:
    """Point count per collection, None when it cannot be read."""
    if getattr(cfg, "qdrant_local_path", ""):
        return {}
    if reader is not None:
        return reader(cfg, names)
    from qdrant_client import QdrantClient

    key = getattr(cfg, "qdrant_read_only_api_key", "") or getattr(cfg, "qdrant_api_key", "")
    client = QdrantClient(
        url=cfg.qdrant_url, api_key=key or None, timeout=2, check_compatibility=False
    )
    out: dict[str, int | None] = {}
    for name in names:
        try:
            out[name] = int(client.get_collection(name).points_count or 0)
        except (UnexpectedResponse, ResponseHandlingException, OSError, ValueError) as exc:
            logger.debug("qdrant point count unavailable for %s: %s", name, exc)
            out[name] = None
    return out


def _fetch_snapshot(cfg) -> OpsSnapshot:
    snap = OpsSnapshot(points=read_points(cfg, collections_to_watch(cfg)))
    from celery_config import CELERY_BROKER_URL

    try:
        client = redis.Redis.from_url(CELERY_BROKER_URL, socket_timeout=1, socket_connect_timeout=1)
        snap.queues = {q: int(client.llen(q)) for q in CELERY_QUEUES}
        raw = client.get(BEAT_KEY)
        snap.beat_ts = float(raw) if raw else None
        for field_name, count in (client.hgetall(RESULT_HASH) or {}).items():
            task, _, result = field_name.decode().rpartition("|")
            snap.task_results[(task, result)] = int(count)
    except (redis.RedisError, ValueError) as exc:
        logger.debug("celery metrics unavailable: %s", exc)
        snap.queues = None
    return snap


def _apply(snap: OpsSnapshot) -> None:
    for name, count in snap.points.items():
        if count is None:
            _drop(QDRANT_COLLECTION_POINTS_COUNT, name)
        else:
            QDRANT_COLLECTION_POINTS_COUNT.labels(collection=name).set(count)
    if snap.queues is None:
        CELERY_QUEUE_LENGTH.clear()
    else:
        for queue, length in snap.queues.items():
            CELERY_QUEUE_LENGTH.labels(queue=queue).set(length)
    # Beat tick and task results are exposed by the collector below, so an
    # unknown tick is an absent series, never a stale or NaN sample.
    _state["beat_ts"] = snap.beat_ts
    _state["results"] = dict(snap.task_results)


def _drop(gauge, *labels: str) -> None:
    try:
        gauge.remove(*labels)
    except KeyError:
        pass


async def refresh_ops_gauges(
    cfg=None, *, fetch: Callable[[Any], OpsSnapshot] | None = None, now: float | None = None
) -> bool:
    """Refresh the gauges unless the TTL holds. Returns True when it read fresh data."""
    global _lock
    if cfg is None:
        from app.config import settings as cfg
    clock = time.monotonic() if now is None else now
    last = _state["at"]
    if last is not None and 0 <= clock - last < TTL_S:
        return False
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        last = _state["at"]
        if last is not None and 0 <= clock - last < TTL_S:
            return False
        _state["at"] = clock  # set first: a failing dependency is retried after the TTL
        try:
            snap = await asyncio.wait_for(
                asyncio.to_thread(fetch or _fetch_snapshot, cfg), FETCH_TIMEOUT_S
            )
        except (TimeoutError, OSError, ValueError, RuntimeError) as exc:
            logger.warning("ops gauges not refreshed: %s", exc or type(exc).__name__)
            return False
        _apply(snap)
        return True


class _TaskResultCollector:
    """Exposes `celery_task_result_total` and `celery_beat_last_tick_timestamp_seconds`."""

    def collect(self):
        if _state["beat_ts"] is not None:
            beat = GaugeMetricFamily(
                "celery_beat_last_tick_timestamp_seconds",
                "Unix time the beat_heartbeat task last ran: beat dispatched it and a worker ran it",
            )
            beat.add_metric([], _state["beat_ts"])
            yield beat
        family = CounterMetricFamily(
            "celery_task_result",
            "Celery task outcomes counted by the worker (success, failure, retry)",
            labels=["task", "result"],
        )
        for (task, result), count in sorted(_state["results"].items()):
            family.add_metric([task, result], count)
        yield family


try:
    REGISTRY.register(_TaskResultCollector())
except ValueError:  # already registered (module reloaded in a test run)
    pass
