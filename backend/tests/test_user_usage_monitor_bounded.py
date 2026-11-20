import logging

from app.core import user_usage_monitor as m


def test_keys_evicted_and_bounded(monkeypatch):
    t = [0.0]
    monkeypatch.setattr(m.time, "monotonic", lambda: t[0])
    mon = m.UserUsageMonitor(window_seconds=60.0, warn_threshold=30)
    for i in range(m.MAX_TRACKED_KEYS * 3):
        t[0] += 0.001
        mon.record(f"anon:{i}")
        assert len(mon._calls) <= m.MAX_TRACKED_KEYS
    # expired keys dropped when their window empties
    t[0] += 1000
    stale = next(iter(mon._calls))
    assert mon.count(stale) == 0 and stale not in mon._calls


def test_hot_key_still_warns(monkeypatch, caplog):
    mon = m.UserUsageMonitor(window_seconds=60.0, warn_threshold=5)
    with caplog.at_level(logging.WARNING, logger=m.logger.name):
        for _ in range(5):
            mon.record("hot-user-1234567")
    assert "possible abuse probe" in caplog.text
