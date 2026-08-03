"""Qdrant observability: metrics collection and Prometheus exposure.

Tracks search latency, upsert latency, collection health, and index fragmentation.
Integrates with app/metrics.py for /api/metrics endpoint.
"""

import logging
import time
from dataclasses import dataclass
from functools import wraps
from typing import Callable, Optional

try:
    from prometheus_client import Counter, Histogram, Gauge
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class QdrantSearchMetrics:
    """Qdrant search performance snapshot."""
    search_latency_p50_ms: float
    search_latency_p95_ms: float
    search_latency_p99_ms: float
    upsert_latency_avg_ms: float
    collection_size_vectors: int
    collection_size_mb: float
    index_fragmentation_pct: float
    index_segment_count: int
    search_error_rate: float


class QdrantMetricsCollector:
    """Collects and exposes Qdrant metrics to Prometheus."""

    def __init__(self):
        self._search_latencies: list[float] = []
        self._upsert_latencies: list[float] = []
        self._search_errors: int = 0
        self._search_total: int = 0

        if PROMETHEUS_AVAILABLE:
            # Histograms: latency distribution
            self.search_latency_histogram = Histogram(
                "qdrant_search_latency_ms",
                "Qdrant search latency in milliseconds",
                buckets=[10, 50, 100, 250, 500, 1000],
            )
            self.upsert_latency_histogram = Histogram(
                "qdrant_upsert_latency_ms",
                "Qdrant upsert latency in milliseconds",
                buckets=[10, 50, 100, 500, 1000, 5000],
            )

            # Gauges: point-in-time values
            self.collection_size_gauge = Gauge(
                "qdrant_collection_size_vectors",
                "Total vectors in collection",
            )
            self.index_fragmentation_gauge = Gauge(
                "qdrant_index_fragmentation_pct",
                "Percentage of index fragmentation (0-100)",
            )
            self.index_segment_count_gauge = Gauge(
                "qdrant_index_segment_count",
                "Number of index segments",
            )

            # Counters: cumulative
            self.search_errors_counter = Counter(
                "qdrant_search_errors_total",
                "Total search errors",
            )
            self.searches_counter = Counter(
                "qdrant_searches_total",
                "Total search operations",
            )

    def record_search_latency(self, latency_ms: float):
        """Record a search operation latency."""
        self._search_latencies.append(latency_ms)
        self._search_total += 1
        if PROMETHEUS_AVAILABLE:
            self.search_latency_histogram.observe(latency_ms)
            self.searches_counter.inc()

    def record_search_error(self):
        """Record a search error."""
        self._search_errors += 1
        if PROMETHEUS_AVAILABLE:
            self.search_errors_counter.inc()

    def record_upsert_latency(self, latency_ms: float):
        """Record an upsert operation latency."""
        self._upsert_latencies.append(latency_ms)
        if PROMETHEUS_AVAILABLE:
            self.upsert_latency_histogram.observe(latency_ms)

    def update_collection_stats(self, size_vectors: int, size_mb: float, fragmentation_pct: float, segment_count: int):
        """Update collection-level metrics from health check."""
        if PROMETHEUS_AVAILABLE:
            self.collection_size_gauge.set(size_vectors)
            self.index_fragmentation_gauge.set(fragmentation_pct)
            self.index_segment_count_gauge.set(segment_count)

    def get_snapshot(self) -> QdrantSearchMetrics:
        """Get current metrics snapshot."""
        # Percentiles (keep last 1000 samples)
        recent_latencies = self._search_latencies[-1000:] if self._search_latencies else [0]
        recent_latencies.sort()

        p50 = recent_latencies[int(len(recent_latencies) * 0.50)]
        p95 = recent_latencies[int(len(recent_latencies) * 0.95)]
        p99 = recent_latencies[int(len(recent_latencies) * 0.99)]

        avg_upsert = sum(self._upsert_latencies) / len(self._upsert_latencies) if self._upsert_latencies else 0

        return QdrantSearchMetrics(
            search_latency_p50_ms=p50,
            search_latency_p95_ms=p95,
            search_latency_p99_ms=p99,
            upsert_latency_avg_ms=avg_upsert,
            collection_size_vectors=0,  # Updated via update_collection_stats
            collection_size_mb=0,
            index_fragmentation_pct=0,
            index_segment_count=0,
            search_error_rate=self._search_errors / max(1, self._search_total),
        )


# Global singleton
_metrics_collector: Optional[QdrantMetricsCollector] = None


def get_metrics_collector() -> QdrantMetricsCollector:
    """Get or create global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = QdrantMetricsCollector()
    return _metrics_collector


def track_search_latency(func: Callable) -> Callable:
    """Decorator to track search operation latency."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            latency_ms = (time.time() - start) * 1000
            get_metrics_collector().record_search_latency(latency_ms)
            return result
        except Exception as e:
            get_metrics_collector().record_search_error()
            raise
    return wrapper


def track_upsert_latency(func: Callable) -> Callable:
    """Decorator to track upsert operation latency."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        latency_ms = (time.time() - start) * 1000
        get_metrics_collector().record_upsert_latency(latency_ms)
        return result
    return wrapper


if __name__ == "__main__":
    # Self-check
    collector = get_metrics_collector()
    collector.record_search_latency(100.5)
    collector.record_upsert_latency(250.0)
    snapshot = collector.get_snapshot()
    print(f"✓ Metrics collector initialized: {snapshot}")
