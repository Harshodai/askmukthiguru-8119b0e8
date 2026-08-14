"""Regression tests for recurring-work safety and cost containment."""

import pytest


def test_scheduled_youtube_sync_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_SCHEDULED_YOUTUBE_SYNC", raising=False)
    from app.config import Settings

    assert Settings().enable_scheduled_youtube_sync is False


@pytest.mark.asyncio
async def test_disabled_weekly_sync_does_not_initialize_ingestion(monkeypatch):
    from infrastructure import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module.settings, "enable_scheduled_youtube_sync", False)

    monkeypatch.setattr(scheduler_module, "logger", type("Logger", (), {"info": lambda *a, **k: None})())
    await scheduler_module.sync_youtube_playlist()



def test_weekly_sync_is_single_instance_and_coalesced(monkeypatch):
    from infrastructure import scheduler as scheduler_module

    calls = []
    monkeypatch.setattr(scheduler_module.scheduler, "add_job", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(scheduler_module.scheduler, "start", lambda: None)

    scheduler_module.start_scheduler()

    assert len(calls) == 1
    kwargs = calls[0][1]
    assert kwargs["id"] == "weekly_youtube_sync"
    assert kwargs["coalesce"] is True
    assert kwargs["max_instances"] == 1
    assert kwargs["misfire_grace_time"] == 3600
