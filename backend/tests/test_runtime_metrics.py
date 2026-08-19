from __future__ import annotations

from unittest.mock import MagicMock

from app import runtime_metrics


def test_process_snapshot_exposes_non_negative_process_only_values():
    snapshot = runtime_metrics.process_snapshot()
    assert snapshot["rss_bytes"] >= 0
    assert snapshot["cpu_seconds"] >= 0
    assert set(snapshot) == {"rss_bytes", "cpu_seconds"}


def test_request_resource_observation_records_metrics_without_request_content(monkeypatch):
    rss = MagicMock()
    cpu = MagicMock()
    request_cpu = MagicMock()
    monkeypatch.setattr(runtime_metrics, "PROCESS_RSS_BYTES", rss)
    monkeypatch.setattr(runtime_metrics, "PROCESS_CPU_SECONDS", cpu)
    monkeypatch.setattr(runtime_metrics, "REQUEST_CPU_SECONDS", request_cpu)
    monkeypatch.setattr(
        runtime_metrics, "process_snapshot", lambda: {"rss_bytes": 1024, "cpu_seconds": 4.5}
    )

    assert runtime_metrics.observe_request_resources(-2) == {"rss_bytes": 1024, "cpu_seconds": 4.5}
    rss.set.assert_called_once_with(1024)
    cpu.set.assert_called_once_with(4.5)
    request_cpu.observe.assert_called_once_with(0.0)


def test_queue_and_provider_observation_reject_invalid_values(monkeypatch):
    queue = MagicMock()
    provider = MagicMock()
    monkeypatch.setattr(runtime_metrics, "QUEUE_DEPTH", queue)
    monkeypatch.setattr(runtime_metrics, "PROVIDER_REPORTED_COST_USD", provider)

    runtime_metrics.observe_queue_depths({"standard": 3, "bad": -1, "unknown": "x"})
    queue.labels.assert_called_once_with(priority="standard")
    queue.labels.return_value.set.assert_called_once_with(3)
    runtime_metrics.observe_provider_actual_cost("openrouter", 0.004)
    runtime_metrics.observe_provider_actual_cost("openrouter", -1)
    provider.labels.assert_called_once_with(provider="openrouter")
    provider.labels.return_value.inc.assert_called_once_with(0.004)
