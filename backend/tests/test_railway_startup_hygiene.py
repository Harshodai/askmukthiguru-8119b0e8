from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import start_railway


def test_startup_hygiene_removes_stale_tmp_files(tmp_path):
    """Verify that run_preflight_startup_hygiene cleans stale lock/pid files."""
    test_pid = "/tmp/test_railway_mock.pid"
    test_lock = "/tmp/test_railway_mock.lock"

    # Create dummy stale files in /tmp
    with open(test_pid, "w") as f:
        f.write("12345")
    with open(test_lock, "w") as f:
        f.write("locked")

    assert os.path.exists(test_pid)
    assert os.path.exists(test_lock)

    cleaned = start_railway.run_preflight_startup_hygiene()

    assert not os.path.exists(test_pid)
    assert not os.path.exists(test_lock)
    assert cleaned["temp_files"] >= 2


def test_startup_hygiene_redis_lock_clearance_when_flag_set(monkeypatch):
    """Verify that CLEANUP_ON_STARTUP triggers lock clearance in Redis."""
    monkeypatch.setenv("CLEANUP_ON_STARTUP", "true")
    monkeypatch.setenv("REDIS_URL", "redis://mock:6379/0")

    mock_redis = MagicMock()
    mock_redis_lib = MagicMock()
    mock_redis_lib.from_url.return_value = mock_redis
    mock_redis.scan_iter.return_value = iter(["mukthiguru:lock:stale_1"])

    with patch.dict("sys.modules", {"redis": mock_redis_lib}):
        cleaned = start_railway.run_preflight_startup_hygiene()
        assert cleaned["stale_locks"] >= 1
        mock_redis.delete.assert_called()


def test_post_warmup_gc_collect(monkeypatch):
    """Verify gc.collect can be invoked cleanly."""
    import gc

    collected = gc.collect()
    assert isinstance(collected, int)
