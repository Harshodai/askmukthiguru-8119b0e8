"""Low-overhead, privacy-safe runtime capacity instrumentation."""

from __future__ import annotations

import os
import resource
import sys
from collections.abc import Mapping

from app.metrics import (
    OPENROUTER_CACHE_WRITE_TOKENS_TOTAL,
    OPENROUTER_CACHED_TOKENS_TOTAL,
    OPENROUTER_COST_UNKNOWN_TOTAL,
    OPENROUTER_ESTIMATED_COST_USD,
    PROCESS_CPU_SECONDS,
    PROCESS_RSS_BYTES,
    PROVIDER_REPORTED_COST_USD,
    QUEUE_DEPTH,
    REQUEST_CPU_SECONDS,
)


def process_snapshot() -> dict[str, float | int]:
    """Return only process-level CPU/RSS values; no request or user data."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    cpu_seconds = max(0.0, usage.ru_utime + usage.ru_stime)
    rss_bytes = 0
    try:
        # Linux exposes current RSS in pages. Railway production uses Linux.
        with open("/proc/self/statm", encoding="ascii") as statm:
            rss_pages = int(statm.read().split()[1])
        rss_bytes = rss_pages * os.sysconf("SC_PAGE_SIZE")
    except (FileNotFoundError, IndexError, OSError, ValueError):
        # ru_maxrss is bytes on macOS and KiB on Linux/BSD. It is a safe fallback.
        multiplier = 1 if sys.platform == "darwin" else 1024
        rss_bytes = max(0, int(usage.ru_maxrss) * multiplier)
    return {"rss_bytes": rss_bytes, "cpu_seconds": cpu_seconds}


def observe_request_resources(cpu_seconds: float) -> dict[str, float | int]:
    """Sample process capacity after a request and observe bounded metrics."""
    snapshot = process_snapshot()
    PROCESS_RSS_BYTES.set(snapshot["rss_bytes"])
    PROCESS_CPU_SECONDS.set(snapshot["cpu_seconds"])
    REQUEST_CPU_SECONDS.observe(max(0.0, float(cpu_seconds)))
    return snapshot


def observe_queue_depths(depths: Mapping[str, int | float]) -> None:
    """Publish bounded queue depths; unknown or negative readings stay hidden."""
    for priority, depth in depths.items():
        try:
            value = int(depth)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            QUEUE_DEPTH.labels(priority=str(priority)).set(value)


def observe_provider_actual_cost(provider: str, cost_usd: float) -> None:
    """Count actual provider-reported cost, never an estimate or user payload."""
    try:
        cost = float(cost_usd)
    except (TypeError, ValueError):
        return
    if cost > 0:
        PROVIDER_REPORTED_COST_USD.labels(provider=provider).inc(cost)


def observe_openrouter_accounting(
    *,
    model: str,
    operation: str,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
    cost_known: bool = False,
    fallback_cost_known: bool = False,
) -> None:
    """Publish bounded provider-accounting signals without request content.

    Model and operation are controlled server-side values. Unknown cost is
    counted separately so dashboards never mistake missing provider metadata
    for a free request.
    """
    safe_model = str(model or "unknown")[:120]
    safe_operation = str(operation or "unknown")[:80]
    try:
        cached = max(0, int(cached_tokens or 0))
    except (TypeError, ValueError):
        cached = 0
    try:
        written = max(0, int(cache_write_tokens or 0))
    except (TypeError, ValueError):
        written = 0
    if cached:
        OPENROUTER_CACHED_TOKENS_TOTAL.labels(
            model=safe_model, operation=safe_operation
        ).inc(cached)
    if written:
        OPENROUTER_CACHE_WRITE_TOKENS_TOTAL.labels(
            model=safe_model, operation=safe_operation
        ).inc(written)
    try:
        estimated = float(estimated_cost_usd or 0.0)
    except (TypeError, ValueError):
        estimated = 0.0
    if estimated > 0:
        OPENROUTER_ESTIMATED_COST_USD.labels(
            model=safe_model, operation=safe_operation
        ).inc(estimated)
    if not cost_known and not fallback_cost_known:
        OPENROUTER_COST_UNKNOWN_TOTAL.labels(
            model=safe_model, operation=safe_operation
        ).inc()
