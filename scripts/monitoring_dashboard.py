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
import re
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


_LE_LABEL_RE = re.compile(r'le="([^"]+)"')


def _histogram_percentile(buckets: dict[float, float], pct: float) -> Optional[float]:
    """Approximate a percentile from cumulative Histogram bucket counts.

    ``buckets`` maps each bucket's ``le`` upper bound (in seconds) to its
    cumulative count, aggregated across all label combinations. Returns the
    smallest bucket boundary whose cumulative count covers ``pct`` of the
    total -- the standard low-cost approximation for a Histogram (which,
    unlike a Summary, never exposes exact quantiles). The ``+Inf`` bucket
    holds the total and is never a meaningful latency, so when no finite
    boundary covers ``pct`` (a heavy-tail distribution), the largest finite
    boundary is returned instead.
    """
    if not buckets:
        return None
    total = buckets.get(float("inf"))
    if not total:
        return None
    threshold = pct * total
    for le in sorted(buckets):
        if le == float("inf"):
            break
        if buckets[le] >= threshold:
            return le
    finite = [le for le in buckets if le != float("inf")]
    return max(finite) if finite else None


def parse_prometheus(text: str) -> MetricsSnapshot:
    """Parse Prometheus exposition format into a MetricsSnapshot.

    guru_request_latency_seconds is a Histogram, not a Summary -- it exposes
    cumulative ``_bucket{le="..."}`` lines, never a ``quantile="0.5"`` label.
    Bucket counts are aggregated across all label combinations (e.g. "stage")
    and p50/p95 are approximated from the cumulative distribution.
    """
    snap = MetricsSnapshot()
    latency_buckets: dict[float, float] = {}
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

        if metric_line.startswith("guru_request_latency_seconds_bucket"):
            le_match = _LE_LABEL_RE.search(metric_line)
            if le_match:
                le = float(le_match.group(1))
                latency_buckets[le] = latency_buckets.get(le, 0.0) + value
        elif "cache_hit" in metric_line:
            snap.cache_hit_rate = value
        elif "tokens_per_request" in metric_line:
            snap.tokens_per_request = value
        elif "error_rate" in metric_line:
            snap.error_rate = value

    p50 = _histogram_percentile(latency_buckets, 0.50)
    p95 = _histogram_percentile(latency_buckets, 0.95)
    snap.latency_p50_ms = p50 * 1000 if p50 is not None else None
    snap.latency_p95_ms = p95 * 1000 if p95 is not None else None
    return snap


def format_table(metrics: MetricsSnapshot) -> str:
    """Return a human-readable metrics table."""
    lines = [
        "+--------------------------------+-----------+",
        f"| {'Metric':<30} | {'Value':<9} |",
        "+--------------------------------+-----------+",
        f"| {'Latency p50':<30} | {('N/A' if metrics.latency_p50_ms is None else metrics.latency_p50_ms):<9} |",
        f"| {'Latency p95':<30} | {('N/A' if metrics.latency_p95_ms is None else metrics.latency_p95_ms):<9} |",
        f"| {'Cache Hit Rate':<30} | {('N/A' if metrics.cache_hit_rate is None else metrics.cache_hit_rate):<9} |",
        f"| {'Tokens / Request':<30} | {('N/A' if metrics.tokens_per_request is None else metrics.tokens_per_request):<9} |",
        f"| {'Error Rate':<30} | {('N/A' if metrics.error_rate is None else metrics.error_rate):<9} |",
        "+--------------------------------+-----------+",
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
