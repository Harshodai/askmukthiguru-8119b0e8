#!/usr/bin/env python3
"""
Mukthi Guru — Monitoring Dashboard CLI

Queries the /metrics endpoint and renders a formatted table with:
- Latency p50/p95
- Cache hit percentage
- Token usage
- Error rate

Usage:
    python scripts/monitoring_dashboard.py [--url http://localhost:8000/metrics]
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Optional

try:
    import httpx
except ImportError:
    print("[ERROR] httpx required. Install with: pip install httpx")
    sys.exit(1)


@dataclass
class MetricsSnapshot:
    latency_p50_ms: Optional[float] = None
    latency_p95_ms: Optional[float] = None
    cache_hit_rate: Optional[float] = None
    tokens_per_request: Optional[float] = None
    error_rate: Optional[float] = None


def parse_prometheus(text: str) -> MetricsSnapshot:
    """Parse Prometheus exposition format into a MetricsSnapshot."""
    snap = MetricsSnapshot()
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.rsplit(None, 1)
        if len(parts) != 2:
            continue
        metric_line, value_str = parts
        try:
            value = float(value_str)
        except ValueError:
            continue

        if "latency" in metric_line and "0.5" in metric_line:
            snap.latency_p50_ms = value
        elif "latency" in metric_line and "0.95" in metric_line:
            snap.latency_p95_ms = value
        elif "cache_hit" in metric_line:
            snap.cache_hit_rate = value
        elif "tokens_per_request" in metric_line:
            snap.tokens_per_request = value
        elif "error_rate" in metric_line:
            snap.error_rate = value
    return snap


def format_table(metrics: MetricsSnapshot) -> str:
    """Return a human-readable metrics table."""
    lines = [
        "+--------------------------------+-----------+
",
        f"| {'Metric':<30} | {'Value':<9} |",
        "+--------------------------------+-----------+
",
        f"| {'Latency p50':<30} | {metrics.latency_p50_ms or 'N/A':<9} |",
        f"| {'Latency p95':<30} | {metrics.latency_p95_ms or 'N/A':<9} |",
        f"| {'Cache Hit Rate':<30} | {metrics.cache_hit_rate or 'N/A':<9} |",
        f"| {'Tokens / Request':<30} | {metrics.tokens_per_request or 'N/A':<9} |",
        f"| {'Error Rate':<30} | {metrics.error_rate or 'N/A':<9} |",
        "+--------------------------------+-----------+
",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mukthi Guru Monitoring Dashboard")
    parser.add_argument("--url", default="http://localhost:8000/metrics", help="Prometheus endpoint URL")
    args = parser.parse_args()

    try:
        resp = httpx.get(args.url, timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"[ERROR] Could not fetch metrics: {exc}")
        return 1

    snap = parse_prometheus(resp.text)
    print("\nMukthi Guru Metrics Dashboard")
    print("=" * 40)
    print(format_table(snap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
