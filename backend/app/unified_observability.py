"""Unified Observability Aggregator (ponytail principle).

Single source of truth for all operational metrics.
Aggregates: Prometheus, Supabase telemetry, cost tracker, runtime, cache, circuit breaker.
One endpoint: GET /api/admin/observability/summary
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import psutil

from app.runtime_metrics import process_snapshot

logger = logging.getLogger(__name__)


@dataclass
class ObservabilitySummary:
    """Single response object for admin observability dashboard."""

    # System health
    timestamp: float = field(default_factory=time.time)
    uptime_s: float = 0.0
    process_rss_mb: float = 0.0
    process_cpu_pct: float = 0.0
    queue_depth: int = 0

    # Request metrics (from telemetry_db KPIs)
    total_queries: int = 0
    queries_last_hour: int = 0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    error_rate_pct: float = 0.0

    # Cost metrics
    total_cost_usd: float = 0.0
    cost_last_hour_usd: float = 0.0
    budget_remaining_usd: float = 0.0

    # Cache metrics
    cache_hit_rate: float = 0.0
    cache_entries: int = 0
    cache_memory_mb: float = 0.0

    # Circuit breaker
    circuit_breaker_state: str = "closed"
    circuit_breaker_failures: int = 0

    # Quality metrics
    avg_faithfulness: float = 0.0
    hallucination_rate_pct: float = 0.0

    # Dependency health
    qdrant_healthy: bool = False
    redis_healthy: bool = False
    neo4j_healthy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def get_observability_summary(
    cost_tracker: Any | None = None,
    container: Any | None = None,
) -> ObservabilitySummary:
    """Aggregate all observability sources into one summary.

    All sub-queries are fail-open: if a source is unavailable, its fields
    stay at their defaults. This endpoint must never 500.
    """
    proc = psutil.Process()
    rt = process_snapshot()

    summary = ObservabilitySummary(
        uptime_s=time.time() - proc.create_time(),
        process_rss_mb=rt["rss_bytes"] / (1024 * 1024),
        process_cpu_pct=proc.cpu_percent(interval=0.1),
        queue_depth=0,
    )

    # KPIs from Supabase telemetry
    try:
        from app.telemetry_db import get_kpis

        kpis = await get_kpis()
        if kpis:
            summary.total_queries = kpis.get("total_queries", 0)
            summary.p50_latency_ms = kpis.get("p50_latency_ms", 0)
            summary.p95_latency_ms = kpis.get("p95_latency_ms", 0)
            summary.error_rate_pct = kpis.get("error_rate", 0)
            summary.avg_faithfulness = kpis.get("faithfulness_p50", 0)
            summary.hallucination_rate_pct = kpis.get("hallucination_rate", 0) * 100
    except Exception:
        logger.debug("Telemetry KPIs unavailable", exc_info=True)

    # Cost from CostTracker
    if cost_tracker is not None:
        try:
            report = cost_tracker.get_usage_report(days=30)
            summary.total_cost_usd = report.total_cost_usd
        except Exception:
            logger.debug("Cost tracker unavailable", exc_info=True)

    # Circuit breaker state
    try:
        from services.circuit_breaker import get_circuit_breaker_registry

        registry = get_circuit_breaker_registry()
        all_stats = registry.get_all_stats()
        if all_stats:
            _severity = {"open": 2, "half_open": 1, "closed": 0}
            _worst = _severity[summary.circuit_breaker_state]
            for _name, stats in all_stats.items():
                state_val = stats.get("state", "closed")
                if state_val in ("open", "half_open"):
                    summary.circuit_breaker_failures += stats.get("consecutive_failures", 0)
                if _severity.get(state_val, 0) > _worst:
                    _worst = _severity[state_val]
                    summary.circuit_breaker_state = state_val
    except Exception:
        logger.debug("Circuit breaker registry unavailable", exc_info=True)

    # Dependency health (quick checks)
    if container is not None:
        try:
            summary.qdrant_healthy = await _check_qdrant(container)
            summary.redis_healthy = await _check_redis(container)
            summary.neo4j_healthy = await _check_neo4j(container)
        except Exception:
            logger.debug("Dependency health checks failed", exc_info=True)

    return summary


async def _check_qdrant(container: Any) -> bool:
    """Check Qdrant health via the container's qdrant service."""
    import asyncio

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(container.qdrant.health_check), timeout=3.0
        )
    except Exception:
        return False


async def _check_redis(container: Any) -> bool:
    """Check Redis health."""
    import asyncio

    from app.config import settings

    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await asyncio.wait_for(r.ping(), timeout=2.0)
        await r.close()
        return True
    except Exception:
        return False


async def _check_neo4j(container: Any) -> bool:
    """Check Neo4j health."""
    import asyncio

    def _run_check() -> bool:
        driver = container.neo4j_driver
        if driver is None:
            return False
        with driver.session() as session:
            session.run("RETURN 1")
        return True

    try:
        return await asyncio.wait_for(asyncio.to_thread(_run_check), timeout=3.0)
    except Exception:
        return False
