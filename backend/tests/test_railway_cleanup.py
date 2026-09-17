import sys
from pathlib import Path
from unittest.mock import MagicMock

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ops.railway_cleanup import (
    BUDGET_HARD_LIMIT_USD,
    check_railway_budget,
    clear_stale_locks,
    configure_redis_memory_policy,
    flush_redis_query_caches,
    purge_celery_queues,
)


def test_flush_redis_query_caches_targeted_and_safe():
    """Verify that only query cache keys are purged and user data is never touched."""
    mock_client = MagicMock()

    # Mock scan_iter to return matching keys for each query pattern
    def mock_scan_iter(match=None, count=None):
        if match == "mukthiguru:cache:*":
            return iter(["mukthiguru:cache:abc", "mukthiguru:cache:def"])
        elif match == "mukthiguru:semcache:*":
            return iter(["mukthiguru:semcache:123"])
        return iter([])

    mock_client.scan_iter.side_effect = mock_scan_iter
    mock_pipe = MagicMock()
    mock_client.pipeline.return_value = mock_pipe

    results = flush_redis_query_caches(mock_client, dry_run=False)

    assert results["mukthiguru:cache:*"] == 2
    assert results["mukthiguru:semcache:*"] == 1
    # Verify pipeline delete was called with the matching keys
    deleted_keys = [call[0][0] for call in mock_pipe.delete.call_args_list]
    assert "mukthiguru:cache:abc" in deleted_keys
    assert "mukthiguru:semcache:123" in deleted_keys
    mock_pipe.execute.assert_called()


def test_flush_redis_query_caches_dry_run():
    """Verify that dry_run mode does not issue any delete commands."""
    mock_client = MagicMock()
    mock_client.scan_iter.return_value = iter(["mukthiguru:cache:abc"])
    mock_pipe = MagicMock()
    mock_client.pipeline.return_value = mock_pipe

    results = flush_redis_query_caches(mock_client, dry_run=True)

    assert "dry-run" in str(results["mukthiguru:cache:*"])
    mock_pipe.delete.assert_not_called()
    mock_pipe.execute.assert_not_called()


def test_clear_stale_locks_clears_distributed_locks():
    """Verify distributed lock clearance removes orphaned locks."""
    mock_client = MagicMock()

    def mock_scan_iter(match=None, count=None):
        if match == "mukthiguru:lock:*":
            return iter(["mukthiguru:lock:active_run"])
        elif match == "maintenance_lock:*":
            return iter(["maintenance_lock:qdrant"])
        return iter([])

    mock_client.scan_iter.side_effect = mock_scan_iter

    results = clear_stale_locks(mock_client, dry_run=False)

    assert results["mukthiguru:lock:*"] == 1
    assert results["maintenance_lock:*"] == 1
    assert mock_client.delete.call_count >= 2


def test_clear_stale_locks_dry_run():
    """Verify dry-run mode for lock clearance does not delete locks."""
    mock_client = MagicMock()
    mock_client.scan_iter.return_value = iter(["mukthiguru:lock:active_run"])

    results = clear_stale_locks(mock_client, dry_run=True)

    assert "dry-run" in str(results["mukthiguru:lock:*"])
    mock_client.delete.assert_not_called()


def test_purge_celery_queues():
    """Verify that Celery backlog queues are purged when requested."""
    mock_client = MagicMock()
    mock_client.llen.side_effect = lambda q: 5 if q == "ingestion" else 0

    results = purge_celery_queues(mock_client, queues=("ingestion", "embedding"), dry_run=False)

    assert results["ingestion"] == 5
    assert results["embedding"] == 0
    mock_client.delete.assert_called_once_with("ingestion")


def test_configure_redis_memory_policy():
    """Verify maxmemory and volatile-lru eviction configuration."""
    mock_client = MagicMock()

    success = configure_redis_memory_policy(mock_client, maxmemory="256mb", policy="volatile-lru")

    assert success is True
    mock_client.config_set.assert_any_call("maxmemory", "256mb")
    mock_client.config_set.assert_any_call("maxmemory-policy", "volatile-lru")


def test_check_railway_budget_calculations():
    """Verify budget burn-rate calculations against $25 ceiling."""
    # Test safe scenario with paused worker and 0.5 duty cycle
    report_safe = check_railway_budget(
        backend_ram_gb=4.3,
        backend_avg_vcpu=0.25,
        worker_running=False,
        duty_cycle=0.5,
    )
    assert report_safe["budget_limit_usd"] == BUDGET_HARD_LIMIT_USD
    assert report_safe["safe_under_budget"] is True
    assert report_safe["headroom_usd"] > 0

    # Test high duty cycle with worker running to verify critical warning
    report_heavy = check_railway_budget(
        backend_ram_gb=4.3,
        backend_avg_vcpu=0.5,
        worker_running=True,
        worker_ram_gb=1.0,
        worker_avg_vcpu=0.2,
        duty_cycle=1.0,
    )
    assert report_heavy["safe_under_budget"] is False
    assert report_heavy["headroom_usd"] < 0
