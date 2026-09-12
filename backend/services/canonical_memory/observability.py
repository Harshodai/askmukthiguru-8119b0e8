"""Observability for canonical memory system."""
import datetime as dt
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class MemoryMetrics:
    extraction_count: int = 0
    extraction_rejected: int = 0
    resolution_created: int = 0
    resolution_superseded: int = 0
    resolution_merged: int = 0
    resolution_deleted: int = 0
    consolidation_runs: int = 0
    consolidation_applied: int = 0
    consolidation_errors: int = 0
    retrieval_queries: int = 0
    retrieval_total_results: int = 0
    retrieval_latency_ms: float = 0.0
    retrieval_over_limit: int = 0
    query_injection_blocked: int = 0
    consent_denied: int = 0
    vector_index_size: int = 0
    vector_dimension: int = 1024
    orphan_count: int = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class MemoryMonitor:
    def __init__(self):
        self.metrics = MemoryMetrics()
        self._start_time = time.time()
        self._event_log: list = []

    def record(self, event_type: str, details: Optional[Dict[str, Any]] = None):
        self._event_log.append({
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "event": event_type,
            "details": details or {}
        })

    def get_health(self) -> Dict[str, Any]:
        uptime = time.time() - self._start_time
        return {
            "status": "healthy",
            "uptime_seconds": uptime,
            "total_events": len(self._event_log),
            "extraction_total": self.metrics.extraction_count,
            "extraction_rejection_rate": (
                self.metrics.extraction_rejected / self.metrics.extraction_count
                if self.metrics.extraction_count > 0 else 0.0
            ),
            "resolution_breakdown": {
                "created": self.metrics.resolution_created,
                "superseded": self.metrics.resolution_superseded,
                "merged": self.metrics.resolution_merged,
                "deleted": self.metrics.resolution_deleted
            },
            "consolidation": {
                "runs": self.metrics.consolidation_runs,
                "applied": self.metrics.consolidation_applied,
                "errors": self.metrics.consolidation_errors
            },
            "vector_index": {
                "size": self.metrics.vector_index_size,
                "orphan_count": self.metrics.orphan_count
            }
        }

    def get_recent_events(self, limit: int = 50) -> list:
        return self._event_log[-limit:]

    def get_drift_report(self, user_id: str, db_client) -> Dict[str, Any]:
        canonical = db_client.table("canonical_memories").select("id").eq(
            "user_id", user_id
        ).execute()
        vector_count = self.metrics.vector_index_size
        canonical_count = len(canonical.data) if canonical.data else 0
        return {
            "canonical_count": canonical_count,
            "vector_count": vector_count,
            "drift": abs(canonical_count - vector_count),
            "consistent": canonical_count == vector_count
        }


# Module-level singleton
_monitor: Optional[MemoryMonitor] = None


def get_monitor() -> MemoryMonitor:
    global _monitor
    if _monitor is None:
        _monitor = MemoryMonitor()
    return _monitor


if __name__ == "__main__":
    m = get_monitor()
    m.record("test_event", {"key": "value"})
    m.metrics.extraction_count = 10
    m.metrics.extraction_rejected = 2
    m.metrics.resolution_created = 5
    m.metrics.consolidation_runs = 3
    m.metrics.consolidation_applied = 2
    m.metrics.consolidation_errors = 1
    m.metrics.vector_index_size = 50
    m.metrics.orphan_count = 2
    health = m.get_health()
    assert health["status"] == "healthy"
    assert health["extraction_total"] == 10
    assert health["extraction_rejection_rate"] == 0.2
    assert health["resolution_breakdown"]["created"] == 5
    assert health["consolidation"]["runs"] == 3
    assert health["vector_index"]["size"] == 50
    recent = m.get_recent_events(5)
    assert len(recent) == 1
    assert recent[0]["event"] == "test_event"
    m2 = get_monitor()
    assert m is m2
    print("observability.py self-check passed")
