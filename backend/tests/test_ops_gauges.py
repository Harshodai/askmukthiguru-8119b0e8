"""NEW-OPS-3 and NEW-OPS-7 (OPS-005, OPS-006): gauges the backend exports at scrape time.

The Prometheus job scrapes only the backend (`/internal/metrics`). Celery worker
and beat expose no metrics path, and `scripts/ops/export_qdrant_health.py` sets
gauges in a process nobody scrapes. So the backend reads the facts at scrape
time, behind a short TTL:

- `qdrant_collection_points_count{collection}` from the Qdrant read key;
- `celery_queue_length{queue}` from the broker (LLEN);
- `celery_beat_last_tick_timestamp_seconds`, written by the `beat_heartbeat`
  task (it proves beat dispatched AND a worker ran it);
- `celery_task_result_total{task,result}`, counted by the worker through Celery
  signals into a Redis hash and re-exported here.

Fakes only. A live scrape against real Qdrant, Redis and a worker is UNPROVEN.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from prometheus_client import REGISTRY, generate_latest

from app import ops_gauges
from tasks import celery_metrics

CFG = SimpleNamespace(
    first_person_collection="first_person_v10",
    first_person_context_collection="first_person_v10",
    qdrant_collection="spiritual_wisdom_contextual",
    qdrant_url="http://qdrant:6333",
    qdrant_local_path="",
    qdrant_read_only_api_key="ro",
    qdrant_api_key="",
)


def _text() -> str:
    return generate_latest(REGISTRY).decode()


def _snapshot(**kw) -> ops_gauges.OpsSnapshot:
    base = dict(
        points={"first_person_v10": 4224, "spiritual_wisdom_contextual": 12904},
        queues={"ingestion": 2, "memory": 0},
        beat_ts=1_800_000_000.0,
        task_results={("tasks.x", "success"): 5, ("tasks.x", "failure"): 1},
    )
    base.update(kw)
    return ops_gauges.OpsSnapshot(**base)


@pytest.fixture(autouse=True)
def _reset():
    ops_gauges.reset_for_tests()
    yield
    ops_gauges.reset_for_tests()


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_collections_are_the_served_ones_plus_the_main_corpus():
    assert ops_gauges.collections_to_watch(CFG) == [
        "first_person_v10",
        "spiritual_wisdom_contextual",
    ]


def test_refresh_publishes_all_four_metrics():
    assert run(ops_gauges.refresh_ops_gauges(CFG, fetch=lambda cfg: _snapshot(), now=1000.0))
    text = _text()
    assert 'qdrant_collection_points_count{collection="first_person_v10"} 4224.0' in text
    assert 'celery_queue_length{queue="ingestion"} 2.0' in text
    assert "celery_beat_last_tick_timestamp_seconds 1.8e+09" in text
    assert 'celery_task_result_total{result="failure",task="tasks.x"} 1.0' in text


def test_second_refresh_inside_the_ttl_does_not_fetch_again():
    calls = []

    def fetch(cfg):
        calls.append(1)
        return _snapshot()

    run(ops_gauges.refresh_ops_gauges(CFG, fetch=fetch, now=1000.0))
    run(ops_gauges.refresh_ops_gauges(CFG, fetch=fetch, now=1000.0 + ops_gauges.TTL_S - 1))
    assert len(calls) == 1
    run(ops_gauges.refresh_ops_gauges(CFG, fetch=fetch, now=1000.0 + ops_gauges.TTL_S + 1))
    assert len(calls) == 2


def test_unreadable_collection_loses_its_series_instead_of_keeping_a_stale_value():
    run(ops_gauges.refresh_ops_gauges(CFG, fetch=lambda c: _snapshot(), now=1000.0))
    gone = _snapshot(points={"first_person_v10": None, "spiritual_wisdom_contextual": 12904})
    run(ops_gauges.refresh_ops_gauges(CFG, fetch=lambda c: gone, now=2000.0))
    text = _text()
    assert 'collection="first_person_v10"' not in text
    assert 'collection="spiritual_wisdom_contextual"' in text


def test_a_fetch_that_raises_never_breaks_the_scrape():
    def boom(cfg):
        raise OSError("redis down")

    assert run(ops_gauges.refresh_ops_gauges(CFG, fetch=boom, now=1000.0)) is False


def test_a_slow_fetch_is_cut_off(monkeypatch):
    import time

    monkeypatch.setattr(ops_gauges, "FETCH_TIMEOUT_S", 0.2)

    def slow(cfg):
        time.sleep(1.0)
        return _snapshot()

    started = time.monotonic()
    assert run(ops_gauges.refresh_ops_gauges(CFG, fetch=slow, now=1000.0)) is False
    assert time.monotonic() - started < 0.9


def test_local_qdrant_mode_skips_the_qdrant_read():
    local = SimpleNamespace(**{**CFG.__dict__, "qdrant_local_path": "/tmp/q"})
    seen = {}

    def fake_points(cfg, names):
        seen["called"] = True
        return {}

    assert ops_gauges.read_points(local, ["a"], reader=fake_points) == {}
    assert "called" not in seen


# --- worker side -------------------------------------------------------------


class FakeRedis:
    def __init__(self):
        self.hashes: dict[str, dict[str, int]] = {}
        self.values: dict[str, str] = {}

    def hincrby(self, key, field, amount=1):
        self.hashes.setdefault(key, {})
        self.hashes[key][field] = self.hashes[key].get(field, 0) + amount

    def set(self, key, value):
        self.values[key] = str(value)


def test_worker_signals_count_success_failure_and_retry():
    r = FakeRedis()
    celery_metrics.record_result("tasks.a", "success", client=r)
    celery_metrics.record_result("tasks.a", "success", client=r)
    celery_metrics.record_result("tasks.a", "retry", client=r)
    assert r.hashes[celery_metrics.RESULT_HASH] == {"tasks.a|success": 2, "tasks.a|retry": 1}
    with pytest.raises(ValueError):
        celery_metrics.record_result("tasks.a", "weird", client=r)


def test_heartbeat_writes_the_tick_time():
    r = FakeRedis()
    celery_metrics.write_heartbeat(client=r, now=1_800_000_123.0)
    assert r.values[celery_metrics.BEAT_KEY] == "1800000123.0"


def test_a_redis_outage_on_the_worker_never_fails_the_task():
    class Down:
        def hincrby(self, *a, **k):
            import redis

            raise redis.ConnectionError("down")

    celery_metrics.record_result("tasks.a", "success", client=Down())  # no raise


def test_heartbeat_is_scheduled_and_routed_to_a_queue_the_worker_consumes():
    import celery_config as cc

    entry = next(
        v for v in cc.celery_app.conf.beat_schedule.values() if v["task"].endswith("beat_heartbeat")
    )
    assert entry["schedule"] <= 60.0
    route = cc.celery_app.conf.task_routes[entry["task"]]
    assert route["queue"] in {"ingestion", "embedding", "indexing", "okf", "memory"}
    assert "tasks.celery_metrics" in cc.celery_app.conf.include


def test_unknown_beat_tick_is_an_absent_series_not_nan():
    run(ops_gauges.refresh_ops_gauges(CFG, fetch=lambda c: _snapshot(beat_ts=None), now=1000.0))
    assert "celery_beat_last_tick_timestamp_seconds" not in _text()


def test_queue_names_match_the_ones_the_worker_may_consume():
    import start_railway

    assert set(ops_gauges.CELERY_QUEUES) == set(start_railway._CELERY_ALLOWED_QUEUES)


def test_scrape_handlers_refresh_before_exposing():
    import inspect

    from app.api import health

    for fn in (health.scrape_metrics, health.get_metrics):
        src = inspect.getsource(fn)
        assert src.index("refresh_ops_gauges") < src.index("metrics_endpoint()"), fn.__name__
