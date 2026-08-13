"""Validate a Locust JSON report against a declared active-session envelope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def summarise(report: dict[str, Any]) -> dict[str, float | int]:
    stats = report.get("stats") or []
    total = next((item for item in stats if item.get("name") == "Total"), None)
    if total is None:
        total = next((item for item in stats if item.get("method") is None), None)
    if total is None:
        raise ValueError("Locust report has no Total statistics row")
    requests = int(total.get("num_requests") or 0)
    failures = int(total.get("num_failures") or 0)
    return {
        "requests": requests,
        "failures": failures,
        "failure_rate": failures / requests if requests else 1.0,
        "p95_ms": float(total.get("response_time_percentile_95") or 0.0),
        "rps": float(total.get("total_rps") or 0.0),
    }


def evaluate(
    report: dict[str, Any],
    *,
    expected_users: int,
    max_p95_ms: float,
    max_failure_rate: float,
) -> tuple[dict[str, float | int], list[str]]:
    summary = summarise(report)
    failures: list[str] = []
    if summary["requests"] < expected_users:
        failures.append(
            f"only {summary['requests']} requests completed for {expected_users} active users"
        )
    if summary["p95_ms"] > max_p95_ms:
        failures.append(f"p95 {summary['p95_ms']:.0f}ms exceeds {max_p95_ms:.0f}ms")
    if summary["failure_rate"] > max_failure_rate:
        failures.append(
            f"failure rate {summary['failure_rate']:.2%} exceeds {max_failure_rate:.2%}"
        )
    return summary, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--expected-users", required=True, type=int)
    parser.add_argument("--max-p95-ms", type=float, default=8000.0)
    parser.add_argument("--max-failure-rate", type=float, default=0.01)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    summary, failures = evaluate(
        report,
        expected_users=args.expected_users,
        max_p95_ms=args.max_p95_ms,
        max_failure_rate=args.max_failure_rate,
    )
    print(json.dumps({"expected_users": args.expected_users, **summary, "failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
