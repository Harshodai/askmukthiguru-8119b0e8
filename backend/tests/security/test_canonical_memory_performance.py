"""Tests for canonical memory performance monitoring and scale testing."""
import pytest
from services.canonical_memory.performance import (
    PerformanceMonitor,
    LatencyRecord,
    benchmark_query_latency,
)


class TestLatencyRecord:
    def test_record_creation(self):
        rec = LatencyRecord(operation="test", latency_ms=10.0)
        assert rec.operation == "test"
        assert rec.latency_ms == 10.0
        assert rec.timestamp > 0

    def test_record_with_metadata(self):
        rec = LatencyRecord(operation="test", latency_ms=5.0, metadata={"user": "u1"})
        assert rec.metadata["user"] == "u1"


class TestRecordLatency:
    def test_record_single(self):
        m = PerformanceMonitor()
        m.record_latency("extraction", 100.0)
        assert len(m._records) == 1
        assert m._records[0].latency_ms == 100.0

    def test_record_multiple_same_operation(self):
        m = PerformanceMonitor()
        m.record_latency("extraction", 100.0)
        m.record_latency("extraction", 200.0)
        assert len(m._records) == 2

    def test_record_different_operations(self):
        m = PerformanceMonitor()
        m.record_latency("extraction", 100.0)
        m.record_latency("retrieval", 50.0)
        assert len(m._records) == 2

    def test_record_with_metadata(self):
        m = PerformanceMonitor()
        m.record_latency("judge", 10.0, user_id="u1", model="fast")
        assert m._records[0].metadata == {"user_id": "u1", "model": "fast"}


class TestGetPercentiles:
    def test_get_percentiles_empty(self):
        m = PerformanceMonitor()
        pcts = m.get_percentiles("nonexistent")
        assert pcts == {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}

    def test_get_percentiles_custom(self):
        m = PerformanceMonitor()
        pcts = m.get_percentiles("nonexistent", [50, 99])
        assert "p50" in pcts
        assert "p99" in pcts
        assert len(pcts) == 2

    def test_get_percentiles_data(self):
        m = PerformanceMonitor()
        for i in range(100):
            m.record_latency("test", float(i))
        pcts = m.get_percentiles("test")
        assert pcts["p50"] > 0
        assert pcts["p95"] > pcts["p50"]

    def test_get_percentiles_single_value(self):
        m = PerformanceMonitor()
        m.record_latency("test", 42.0)
        pcts = m.get_percentiles("test")
        assert all(v == 42.0 for v in pcts.values())

    def test_get_percentiles_multiple_operations(self):
        m = PerformanceMonitor()
        m.record_latency("op_a", 100.0)
        m.record_latency("op_b", 50.0)
        pcts_a = m.get_percentiles("op_a")
        pcts_b = m.get_percentiles("op_b")
        assert pcts_a["p50"] == 100.0
        assert pcts_b["p50"] == 50.0


class TestCheckLatencyBudget:
    def test_check_within_budget(self):
        m = PerformanceMonitor()
        for i in range(10):
            m.record_latency("retrieval", 100.0 + i)
        result = m.check_latency_budget("retrieval")
        assert result["budget_ms"] == 200
        assert result["within_budget"] is True

    def test_check_over_budget(self):
        m = PerformanceMonitor()
        for i in range(10):
            m.record_latency("retrieval", 300.0 + i * 10)
        result = m.check_latency_budget("retrieval")
        assert result["within_budget"] is False
        assert result["headroom"] == 0

    def test_check_no_budget_defined(self):
        m = PerformanceMonitor()
        m.record_latency("custom_op", 50.0)
        result = m.check_latency_budget("custom_op")
        assert result["budget_ms"] is None
        assert result["within_budget"] is True

    def test_check_empty_records(self):
        m = PerformanceMonitor()
        result = m.check_latency_budget("extraction")
        assert result["p50"] == 0.0
        assert result["within_budget"] is True

    def test_check_headroom(self):
        m = PerformanceMonitor()
        for i in range(10):
            m.record_latency("resolution", 100.0)
        result = m.check_latency_budget("resolution")
        assert result["headroom"] == 400.0


class TestGetSummary:
    def test_summary_empty(self):
        m = PerformanceMonitor()
        assert m.get_summary() == {}

    def test_summary_single_operation(self):
        m = PerformanceMonitor()
        for i in range(5):
            m.record_latency("extraction", 100.0 + i)
        summary = m.get_summary()
        assert "extraction" in summary
        assert summary["extraction"]["count"] == 5
        assert summary["extraction"]["mean_ms"] > 0

    def test_summary_multiple_operations(self):
        m = PerformanceMonitor()
        m.record_latency("extraction", 100.0)
        m.record_latency("retrieval", 50.0)
        summary = m.get_summary()
        assert "extraction" in summary
        assert "retrieval" in summary

    def test_summary_within_budget_field(self):
        m = PerformanceMonitor()
        m.record_latency("retrieval", 50.0)
        summary = m.get_summary()
        assert "within_budget" in summary["retrieval"]

    def test_summary_has_median(self):
        m = PerformanceMonitor()
        for v in [10, 20, 30, 40, 50]:
            m.record_latency("test", float(v))
        summary = m.get_summary()
        assert summary["test"]["median_ms"] == 30.0


class TestStressTest:
    def test_stress_test(self):
        m = PerformanceMonitor()
        result = m.run_stress_test("retrieval", 100, 200.0)
        assert result["operation"] == "retrieval"
        assert result["iterations"] == 100
        assert result["violations"] >= 0
        assert result["pass_rate"] >= 0
        assert result["pass_rate"] <= 1.0

    def test_stress_test_violations(self):
        m = PerformanceMonitor()
        result = m.run_stress_test("retrieval", 100, 1.0)
        assert result["violations"] > 0

    def test_stress_test_high_target(self):
        m = PerformanceMonitor()
        result = m.run_stress_test("retrieval", 100, 100000.0)
        assert result["iterations"] == 100
        assert result["mean_ms"] > 0
        assert result["max_ms"] > 0

    def test_stress_test_empty(self):
        m = PerformanceMonitor()
        result = m.run_stress_test("test", 0, 100.0)
        assert result["iterations"] == 0
        assert result["pass_rate"] == 1.0


class TestBenchmark:
    def test_benchmark_no_retriever(self):
        result = benchmark_query_latency()
        assert result["benchmarks"] == []
        assert result["total_ms"] == 0

    def test_benchmark_no_queries(self):
        result = benchmark_query_latency(retriever="fake")
        assert result["benchmarks"] == []
        assert result["total_ms"] == 0

    def test_benchmark_with_mock_retriever(self):
        class MockRetriever:
            def search(self, query, user_id="", limit=5):
                return []

        result = benchmark_query_latency(
            retriever=MockRetriever(),
            queries=["hello", "world"],
            user_id="test",
        )
        assert len(result["benchmarks"]) == 2
        assert result["total_ms"] >= 0
        assert result["avg_ms"] >= 0

    def test_benchmark_truncates_long_query(self):
        class MockRetriever:
            def search(self, query, user_id="", limit=5):
                return []

        result = benchmark_query_latency(
            retriever=MockRetriever(),
            queries=["a" * 100],
        )
        assert result["benchmarks"][0]["query"] == "a" * 50
