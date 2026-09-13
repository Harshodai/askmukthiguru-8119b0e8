"""Unit and contract tests for Gate 1 load test harness (scripts/ops/gate1_load_test.py)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.ops.gate1_load_test import (
    QUERY_STRATA,
    compute_percentiles,
    run_gate1_load_test,
)


def test_query_strata_coverage():
    """Verify QUERY_STRATA contains Fast, Standard, and Deep tiers."""
    tiers = {item["tier"] for item in QUERY_STRATA}
    assert "fast" in tiers
    assert "standard" in tiers
    assert "deep" in tiers

    for item in QUERY_STRATA:
        assert "query" in item
        assert "tier" in item
        assert "category" in item
        assert len(item["query"].strip()) > 0


def test_percentile_computation():
    """Verify compute_percentiles accurately calculates percentiles, mean, and stddev."""
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    res = compute_percentiles(latencies)

    assert res.min == 10.0
    assert res.max == 100.0
    assert res.mean == 55.0
    assert res.p50 == 55.0  # Median of 10..100 is 55.0
    assert 90.0 <= res.p95 <= 100.0
    assert res.stddev > 0.0


def test_percentile_empty():
    """Verify empty list handles gracefully without crashing."""
    res = compute_percentiles([])
    assert res.min == 0.0
    assert res.p50 == 0.0
    assert res.max == 0.0


@pytest.mark.asyncio
async def test_gate1_harness_mock_execution(tmp_path, monkeypatch):
    """Verify harness worker orchestration and report generation with mock HTTP client."""
    # Patch the module OBJECT, not a dotted string. There are two `scripts/`
    # trees in this repo (repo-root and backend/), so by the time the full suite
    # reaches this test another module may have bound `scripts.ops` in
    # sys.modules to the other tree — which has no `gate1_load_test` attribute,
    # and monkeypatch's string form then raises AttributeError. Passing the
    # already-imported module sidesteps the ambiguity entirely.
    import scripts.ops.gate1_load_test as gate1_mod

    monkeypatch.setattr(gate1_mod, "REPORT_DIR", tmp_path)

    # Mock response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "intent": "QUERY",
        "grounding_state": "grounded",
        "lane": "standard",
        "citations": ["https://youtube.com/watch?v=123"],
        "verification": {"faithfulness_score": 0.95},
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: mock_client)

    summary = await run_gate1_load_test(
        concurrency=4,
        total_requests=8,
        base_url="http://mockserver",
        test_key="mock-key",
        chaos="none",
    )

    assert summary["gate1_verdict"] == "PASS"
    assert summary["concurrency"] == 4
    assert summary["total_requests"] == 8
    assert summary["overall_pass_rate_pct"] == 100.0
    assert summary["error_rate_pct"] == 0.0
    assert summary["status_code_distribution"] == {200: 8}
    assert (tmp_path / "gate1_load_test_report.json").exists()
    assert (tmp_path / "gate1_load_test_report.md").exists()
