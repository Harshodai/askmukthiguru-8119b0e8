"""Tests for canonical memory observability (Phase 15)."""
from unittest.mock import MagicMock

from services.canonical_memory.observability import (
    MemoryMetrics,
    MemoryMonitor,
    get_monitor,
)


def test_monitor_default_metrics():
    m = MemoryMonitor()
    assert m.metrics.extraction_count == 0
    assert m.metrics.extraction_rejected == 0
    assert m.metrics.resolution_created == 0
    assert m.metrics.resolution_superseded == 0
    assert m.metrics.resolution_merged == 0
    assert m.metrics.resolution_deleted == 0
    assert m.metrics.consolidation_runs == 0
    assert m.metrics.consolidation_applied == 0
    assert m.metrics.consolidation_errors == 0
    assert m.metrics.retrieval_queries == 0
    assert m.metrics.retrieval_total_results == 0
    assert m.metrics.retrieval_latency_ms == 0.0
    assert m.metrics.retrieval_over_limit == 0
    assert m.metrics.query_injection_blocked == 0
    assert m.metrics.consent_denied == 0
    assert m.metrics.vector_index_size == 0
    assert m.metrics.vector_dimension == 1024
    assert m.metrics.orphan_count == 0


def test_record_event():
    m = MemoryMonitor()
    m.record("extraction_started", {"user_id": "u1"})
    m.record("resolution_created", {"memory_id": "m1"})
    assert len(m._event_log) == 2
    assert m._event_log[0]["event"] == "extraction_started"
    assert m._event_log[0]["details"] == {"user_id": "u1"}
    assert m._event_log[1]["event"] == "resolution_created"


def test_record_event_default_details():
    m = MemoryMonitor()
    m.record("test_event")
    assert m._event_log[0]["details"] == {}


def test_health_returns_healthy():
    m = MemoryMonitor()
    health = m.get_health()
    assert health["status"] == "healthy"
    assert "uptime_seconds" in health
    assert health["uptime_seconds"] >= 0
    assert health["total_events"] == 0
    assert "resolution_breakdown" in health
    assert "consolidation" in health
    assert "vector_index" in health


def test_extraction_rejection_rate_calc():
    m = MemoryMonitor()
    m.metrics.extraction_count = 100
    m.metrics.extraction_rejected = 25
    health = m.get_health()
    assert health["extraction_rejection_rate"] == 0.25


def test_extraction_rejection_rate_zero_count():
    m = MemoryMonitor()
    m.metrics.extraction_count = 0
    m.metrics.extraction_rejected = 0
    health = m.get_health()
    assert health["extraction_rejection_rate"] == 0.0


def test_drift_report_consistent():
    m = MemoryMonitor()
    m.metrics.vector_index_size = 10
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}, {"id": "e"},
        {"id": "f"}, {"id": "g"}, {"id": "h"}, {"id": "i"}, {"id": "j"},
    ]
    report = m.get_drift_report("user-1", mock_db)
    assert report["canonical_count"] == 10
    assert report["vector_count"] == 10
    assert report["drift"] == 0
    assert report["consistent"] is True


def test_drift_report_inconsistent():
    m = MemoryMonitor()
    m.metrics.vector_index_size = 15
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "a"}, {"id": "b"}, {"id": "c"},
    ]
    report = m.get_drift_report("user-1", mock_db)
    assert report["canonical_count"] == 3
    assert report["vector_count"] == 15
    assert report["drift"] == 12
    assert report["consistent"] is False


def test_recent_events_limit():
    m = MemoryMonitor()
    for i in range(10):
        m.record(f"event_{i}")
    assert len(m.get_recent_events(5)) == 5
    assert m.get_recent_events(5)[0]["event"] == "event_5"
    assert m.get_recent_events(5)[-1]["event"] == "event_9"
    assert len(m.get_recent_events(100)) == 10


def test_singleton_returns_same():
    m1 = get_monitor()
    m2 = get_monitor()
    assert m1 is m2


def test_consolidation_error_rate():
    m = MemoryMonitor()
    m.metrics.consolidation_runs = 10
    m.metrics.consolidation_applied = 8
    m.metrics.consolidation_errors = 2
    health = m.get_health()
    assert health["consolidation"]["runs"] == 10
    assert health["consolidation"]["applied"] == 8
    assert health["consolidation"]["errors"] == 2


def test_metrics_to_dict():
    m = MemoryMetrics()
    d = m.to_dict()
    assert isinstance(d, dict)
    assert "extraction_count" in d
    assert "vector_dimension" in d
    assert d["vector_dimension"] == 1024


def test_health_resolution_breakdown():
    m = MemoryMonitor()
    m.metrics.resolution_created = 5
    m.metrics.resolution_superseded = 3
    m.metrics.resolution_merged = 2
    m.metrics.resolution_deleted = 1
    health = m.get_health()
    rb = health["resolution_breakdown"]
    assert rb["created"] == 5
    assert rb["superseded"] == 3
    assert rb["merged"] == 2
    assert rb["deleted"] == 1
