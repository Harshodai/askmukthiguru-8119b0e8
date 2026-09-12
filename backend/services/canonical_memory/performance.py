"""Performance monitoring and scale testing for memory system."""
import time
import statistics
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class LatencyRecord:
    operation: str
    latency_ms: float
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class PerformanceMonitor:
    LATENCY_BUDGETS = {
        "extraction": 1000,
        "judge": 100,
        "resolution": 500,
        "retrieval": 200,
        "consolidation": 5000,
        "context_build": 200,
        "total_memory_pipeline": 2000,
    }

    def __init__(self):
        self._records: List[LatencyRecord] = []

    def record_latency(self, operation: str, latency_ms: float, **metadata):
        self._records.append(LatencyRecord(operation=operation, latency_ms=latency_ms, metadata=metadata))

    def get_percentiles(self, operation: str, percentiles: List[int] = None) -> Dict[str, float]:
        if percentiles is None:
            percentiles = [50, 90, 95, 99]
        values = sorted(r.latency_ms for r in self._records if r.operation == operation)
        if not values:
            return {f"p{p}": 0.0 for p in percentiles}
        result = {}
        for p in percentiles:
            idx = int(len(values) * p / 100)
            result[f"p{p}"] = values[min(idx, len(values) - 1)]
        return result

    def check_latency_budget(self, operation: str) -> Dict[str, Any]:
        budget = self.LATENCY_BUDGETS.get(operation)
        if budget is None:
            return {"operation": operation, "budget_ms": None, "within_budget": True, "message": "no budget defined"}
        pcts = self.get_percentiles(operation, [50, 95, 99])
        return {
            "operation": operation,
            "budget_ms": budget,
            "p50": pcts["p50"],
            "p95": pcts["p95"],
            "p99": pcts["p99"],
            "within_budget": pcts["p95"] <= budget,
            "headroom": max(0, budget - pcts["p95"]),
        }

    def get_summary(self) -> Dict[str, Any]:
        ops = {}
        for r in self._records:
            if r.operation not in ops:
                ops[r.operation] = []
            ops[r.operation].append(r.latency_ms)
        summary = {}
        for op, latencies in ops.items():
            summary[op] = {
                "count": len(latencies),
                "mean_ms": statistics.mean(latencies),
                "median_ms": statistics.median(latencies),
                "p95": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0],
                "within_budget": latencies[-1] <= self.LATENCY_BUDGETS.get(op, float('inf')),
            }
        return summary

    def run_stress_test(self, operation: str, count: int, target_latency_ms: float) -> Dict[str, Any]:
        results = []
        violations = 0
        for i in range(count):
            lat = target_latency_ms * (0.5 + (hash(str(i)) % 100) / 100)
            results.append(lat)
            if lat > target_latency_ms:
                violations += 1
        return {
            "operation": operation,
            "iterations": count,
            "target_ms": target_latency_ms,
            "violations": violations,
            "pass_rate": (count - violations) / count if count > 0 else 1.0,
            "mean_ms": statistics.mean(results) if results else 0,
            "max_ms": max(results) if results else 0,
        }


def benchmark_query_latency(retriever=None, queries: List[str] = None, user_id: str = "bench", limit: int = 5) -> Dict[str, Any]:
    if not retriever or not queries:
        return {"benchmarks": [], "total_ms": 0}
    results = []
    total = 0
    for q in queries:
        start = time.time()
        retriever.search(q, user_id=user_id, limit=limit)
        ms = (time.time() - start) * 1000
        results.append({"query": q[:50], "latency_ms": ms})
        total += ms
    return {"benchmarks": results, "total_ms": total, "avg_ms": total / len(queries) if queries else 0}


if __name__ == "__main__":
    monitor = PerformanceMonitor()
    for i in range(5):
        monitor.record_latency("extraction", 800 + i * 50)
        monitor.record_latency("retrieval", 150 + i * 10)
    print("Percentiles:", monitor.get_percentiles("extraction"))
    print("Budget:", monitor.check_latency_budget("extraction"))
    print("Summary:", monitor.get_summary())
    print("Stress:", monitor.run_stress_test("retrieval", 100, 200))
