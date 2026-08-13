from benchmarks.readiness_gate import evaluate, summarise


def _report(requests=500, failures=0, p95=1200, rps=8.5):
    return {
        "stats": [
            {
                "name": "Total",
                "num_requests": requests,
                "num_failures": failures,
                "response_time_percentile_95": p95,
                "total_rps": rps,
            }
        ]
    }


def test_readiness_gate_accepts_declared_envelope():
    summary, failures = evaluate(
        _report(),
        expected_users=500,
        max_p95_ms=8000,
        max_failure_rate=0.01,
    )

    assert failures == []
    assert summary["p95_ms"] == 1200.0
    assert summary["failure_rate"] == 0.0


def test_readiness_gate_reports_all_threshold_violations():
    _, failures = evaluate(
        _report(requests=100, failures=5, p95=9000),
        expected_users=500,
        max_p95_ms=8000,
        max_failure_rate=0.01,
    )

    assert len(failures) == 3
    assert "only 100" in failures[0]
    assert "p95" in failures[1]
    assert "failure rate" in failures[2]


def test_readiness_gate_requires_total_locust_row():
    try:
        summarise({"stats": []})
    except ValueError as exc:
        assert "Total" in str(exc)
    else:
        raise AssertionError("missing Total statistics row must fail")
