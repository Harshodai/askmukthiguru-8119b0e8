from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import services.cost_tracker as cost_tracker
from services.cost_tracker import CostTracker, _calculate_cost


class _Table:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.projection: str | None = None
        self.filters: list[tuple[str, str, object]] = []
        self.inserted: dict | None = None

    def select(self, projection: str):
        self.projection = projection
        return self

    def gte(self, field: str, value: object):
        self.filters.append(("gte", field, value))
        return self

    def eq(self, field: str, value: object):
        self.filters.append(("eq", field, value))
        return self

    def insert(self, payload: dict):
        self.inserted = payload
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class _Client:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.table_instance = _Table(rows)

    def table(self, name: str):
        assert name == "token_usage"
        return self.table_instance


def test_calculate_cost_is_normalized_and_decimal_stable():
    assert _calculate_cost("100", "50", "SARVAM") == pytest.approx(0.0003)
    assert _calculate_cost(-10, "not-a-number", "sarvam") == 0.0
    assert _calculate_cost(150, 80, "ollama") == 0.0


def test_record_normalizes_payload_and_preserves_provider_reported_cost(monkeypatch):
    client = _Client()
    tracker = CostTracker()
    monkeypatch.setattr(cost_tracker, "_get_client", lambda: client)
    budget_check = MagicMock()
    monkeypatch.setattr(tracker, "_maybe_check_budget", budget_check)

    tracker.record(
        tenant_id="",
        user_id="user-1",
        session_id="session-1",
        model="model-a",
        provider="openrouter",
        tokens_in=-4,
        tokens_out="12",
        endpoint="",
        cost_override="0.0123456789",
    )

    assert client.table_instance.inserted == {
        "tenant_id": "default",
        "user_id": "user-1",
        "session_id": "session-1",
        "model": "model-a",
        "provider": "openrouter",
        "tokens_in": 0,
        "tokens_out": 12,
        "cost_usd": pytest.approx(0.01234568),
        "endpoint": "/api/chat",
    }
    budget_check.assert_called_once_with("default")


def test_usage_report_uses_minimal_projection_and_preserves_aggregates(monkeypatch):
    client = _Client(
        [
            {
                "user_id": "u1",
                "session_id": "s1",
                "model": "m1",
                "provider": "p1",
                "tokens_in": "10",
                "tokens_out": 5,
                "cost_usd": "0.1000004",
            },
            {
                "user_id": "u1",
                "session_id": "s2",
                "model": "m1",
                "provider": "p1",
                "tokens_in": 20,
                "tokens_out": 10,
                "cost_usd": "0.2000004",
            },
            {
                "user_id": "u2",
                "session_id": "s3",
                "model": "m2",
                "provider": "p2",
                "tokens_in": -100,
                "tokens_out": "invalid",
                "cost_usd": "-3.00",
            },
        ]
    )
    monkeypatch.setattr(cost_tracker, "_get_client", lambda: client)

    report = CostTracker().get_usage_report(tenant_id="tenant-a", user_id="u1", days=7)

    assert client.table_instance.projection == (
        "user_id,session_id,model,provider,tokens_in,tokens_out,cost_usd"
    )
    assert ("eq", "tenant_id", "tenant-a") in client.table_instance.filters
    assert ("eq", "user_id", "u1") in client.table_instance.filters
    assert report.total_tokens_in == 30
    assert report.total_tokens_out == 15
    assert report.total_tokens == 45
    assert report.total_cost_usd == pytest.approx(0.300001)
    assert report.unique_users == 2
    assert report.unique_sessions == 3
    assert report.by_model["m1"]["tokens_in"] == 30
    assert report.by_model["m1"]["tokens_out"] == 15
    assert report.by_model["m1"]["cost_usd"] == pytest.approx(0.300001)
    assert report.by_model["m1"]["calls"] == 2
    assert report.by_provider["p2"]["cost_usd"] == 0.0


def test_daily_usage_uses_minimal_projection_and_sorts_days(monkeypatch):
    client = _Client(
        [
            {
                "created_at": "2026-08-13T12:00:00+00:00",
                "tokens_in": 2,
                "tokens_out": 3,
                "cost_usd": "0.000002",
            },
            {
                "created_at": "2026-08-14T12:00:00+00:00",
                "tokens_in": 4,
                "tokens_out": 5,
                "cost_usd": "0.000004",
            },
        ]
    )
    monkeypatch.setattr(cost_tracker, "_get_client", lambda: client)

    daily = CostTracker().get_daily_usage("tenant-a", days=2)

    assert client.table_instance.projection == ("created_at,tokens_in,tokens_out,cost_usd")
    assert daily == [
        {
            "date": "2026-08-14",
            "total_tokens": 9,
            "cost_usd": 0.000004,
            "calls": 1,
        },
        {
            "date": "2026-08-13",
            "total_tokens": 5,
            "cost_usd": 0.000002,
            "calls": 1,
        },
    ]


def test_budget_checks_are_throttled_per_tenant_not_globally(monkeypatch):
    cost_tracker._LAST_BUDGET_CHECK.clear()
    tracker = CostTracker()
    daily_usage = MagicMock(return_value=[{"cost_usd": 0.01}])
    monkeypatch.setattr(tracker, "get_daily_usage", daily_usage)
    monotonic_values = iter([100.0, 101.0, 102.0])
    monkeypatch.setattr(cost_tracker.time, "monotonic", lambda: next(monotonic_values))

    tracker._maybe_check_budget("tenant-a")
    tracker._maybe_check_budget("tenant-a")
    tracker._maybe_check_budget("tenant-b")

    assert daily_usage.call_count == 2
    assert [call.args[0] for call in daily_usage.call_args_list] == [
        "tenant-a",
        "tenant-b",
    ]


def test_failed_budget_check_can_retry(monkeypatch):
    cost_tracker._LAST_BUDGET_CHECK.clear()
    tracker = CostTracker()
    daily_usage = MagicMock(side_effect=RuntimeError("temporary failure"))
    monkeypatch.setattr(tracker, "get_daily_usage", daily_usage)
    monotonic_values = iter([200.0, 201.0])
    monkeypatch.setattr(cost_tracker.time, "monotonic", lambda: next(monotonic_values))

    tracker._maybe_check_budget("tenant-a")
    tracker._maybe_check_budget("tenant-a")

    assert daily_usage.call_count == 2
