"""Cost mode: the on-demand worker starts only when Celery work is queued."""

import start_railway


class _FakeRedis:
    def __init__(self, lists: dict[str, int], unacked: int = 0) -> None:
        self._lists, self._unacked = lists, unacked

    def llen(self, name: str) -> int:
        return self._lists.get(name, 0)

    def hlen(self, name: str) -> int:
        assert name == "unacked"
        return self._unacked


def test_backlog_zero_when_idle() -> None:
    assert start_railway.celery_backlog(_FakeRedis({}), ["ingestion", "celery"]) == 0


def test_backlog_counts_queued_and_in_flight() -> None:
    client = _FakeRedis({"ingestion": 2, "celery": 1, "other": 9}, unacked=1)
    assert start_railway.celery_backlog(client, ["ingestion", "celery"]) == 4


def test_on_demand_queues_do_not_change_gauge_set() -> None:
    assert "celery" not in start_railway._CELERY_ALLOWED_QUEUES
    assert "celery" in start_railway._ON_DEMAND_EXTRA_QUEUES


def test_scheduled_tasks_cover_all_beat_entries() -> None:
    from celery_config import celery_app

    beat_tasks = {e["task"] for e in celery_app.conf.beat_schedule.values()}
    # beat-heartbeat only proves beat is running; there is no beat in cron mode.
    beat_tasks.discard("tasks.celery_metrics.beat_heartbeat")
    assert beat_tasks == set(start_railway._SCHEDULED_TASKS)
