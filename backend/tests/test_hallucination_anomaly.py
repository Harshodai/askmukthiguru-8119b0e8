"""Tests for hallucination anomaly detector.

Covers:
  - Metric computation on empty / populated rows.
  - Threshold-based anomaly detection (rate spike + faithfulness p50 drop).
  - CLI output shape and exit codes.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from scripts.ops.hallucination_anomaly import (
    _compute_metrics,
    _fetch_responses,
    _iso,
    _utc_now,
    main,
    run_anomaly_check,
)


def test_compute_metrics_empty() -> None:
    metrics = _compute_metrics([])
    assert metrics["total_responses"] == 0
    assert metrics["flagged_count"] == 0
    assert metrics["hallucination_rate"] == 0.0
    assert metrics["faithfulness_p50"] == 0.0
    assert metrics["faithfulness_mean"] == 0.0


def test_compute_metrics_sample() -> None:
    rows = [
        {"hallucination_flag": True, "faithfulness": 0.4},
        {"hallucination_flag": False, "faithfulness": 0.8},
        {"hallucination_flag": False, "faithfulness": 0.95},
    ]
    metrics = _compute_metrics(rows)
    assert metrics["total_responses"] == 3
    assert metrics["flagged_count"] == 1
    assert metrics["hallucination_rate"] == pytest.approx(1 / 3)
    assert metrics["faithfulness_p50"] == pytest.approx(0.8)
    assert metrics["faithfulness_mean"] == pytest.approx((0.4 + 0.8 + 0.95) / 3)


def test_iso_format_utc() -> None:
    dt = datetime(2026, 7, 22, 6, 0, 0, tzinfo=timezone.utc)
    assert _iso(dt) == "2026-07-22T06:00:00Z"


def test_run_anomaly_check_no_anomaly() -> None:
    rows = [
        {"hallucination_flag": False, "faithfulness": 0.9},
        {"hallucination_flag": False, "faithfulness": 0.85},
    ]
    with patch(
        "scripts.ops.hallucination_anomaly._fetch_responses", return_value=rows
    ):
        result = run_anomaly_check(lookback_days=1)

    assert result["anomaly"] is False
    assert result["alerts"]["hallucination_rate_spike"] is False
    assert result["alerts"]["faithfulness_p50_drop"] is False
    assert result["metrics"]["faithfulness_p50"] == pytest.approx(0.875)


def test_run_anomaly_check_rate_spike() -> None:
    rows = [
        {"hallucination_flag": True, "faithfulness": 0.4},
        {"hallucination_flag": True, "faithfulness": 0.5},
        {"hallucination_flag": False, "faithfulness": 0.9},
    ]
    with patch(
        "scripts.ops.hallucination_anomaly._fetch_responses", return_value=rows
    ):
        result = run_anomaly_check(lookback_days=1)

    assert result["metrics"]["hallucination_rate"] == pytest.approx(2 / 3)
    assert result["alerts"]["hallucination_rate_spike"] is True
    assert result["anomaly"] is True


def test_run_anomaly_check_faithfulness_drop() -> None:
    rows = [
        {"hallucination_flag": False, "faithfulness": 0.4},
        {"hallucination_flag": False, "faithfulness": 0.5},
    ]
    with patch(
        "scripts.ops.hallucination_anomaly._fetch_responses", return_value=rows
    ):
        result = run_anomaly_check(lookback_days=1)

    assert result["alerts"]["faithfulness_p50_drop"] is True
    assert result["anomaly"] is True


def test_main_cli_no_anomaly(tmp_path) -> None:
    out_path = tmp_path / "anomaly.json"
    rows = [{"hallucination_flag": False, "faithfulness": 0.9}]
    with patch(
        "scripts.ops.hallucination_anomaly._fetch_responses", return_value=rows
    ):
        rc = main(["--out", str(out_path), "--lookback-days", "1"])

    assert rc == 0
    data = json.loads(out_path.read_text())
    assert data["anomaly"] is False
    assert data["metrics"]["total_responses"] == 1


def test_main_cli_anomaly(tmp_path) -> None:
    out_path = tmp_path / "anomaly.json"
    rows = [
        {"hallucination_flag": True, "faithfulness": 0.4},
        {"hallucination_flag": True, "faithfulness": 0.5},
    ]
    with patch(
        "scripts.ops.hallucination_anomaly._fetch_responses", return_value=rows
    ):
        rc = main(["--out", str(out_path), "--lookback-days", "1"])

    assert rc == 1
    data = json.loads(out_path.read_text())
    assert data["anomaly"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
