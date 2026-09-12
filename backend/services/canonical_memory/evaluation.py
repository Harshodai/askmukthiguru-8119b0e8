"""Evaluation harness for memory quality."""
import datetime as dt
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class EvalVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIP = "skip"


@dataclass
class EvalResult:
    test_name: str
    verdict: EvalVerdict
    score: float
    details: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass
class EvalSuite:
    name: str
    results: list = None
    overall_score: float = 0.0
    overall_verdict: EvalVerdict = EvalVerdict.SKIP


class MemoryEvaluator:
    def __init__(self, db_client, retriever=None, judge=None, resolver=None):
        self.db = db_client
        self.retriever = retriever
        self.judge = judge
        self.resolver = resolver

    def evaluate_memory_health(self, user_id: str) -> EvalSuite:
        suite = EvalSuite(name="memory_health")
        results = []
        canon = self.db.table("canonical_memories").select("*").eq("user_id", user_id).execute()
        total = len(canon.data) if canon.data else 0
        active = [m for m in (canon.data or []) if m.get("status") == "active"]
        result = EvalResult(
            test_name="extraction_quality",
            verdict=EvalVerdict.PASS if len(active) > 0 else EvalVerdict.WARNING,
            score=len(active) / total if total > 0 else 0.0,
            details=f"{len(active)}/{total} active memories"
        )
        results.append(result)
        duplicates = {}
        for m in active:
            fk = m.get("fact_key", "")
            duplicates[fk] = duplicates.get(fk, 0) + 1
        dup_count = sum(1 for c in duplicates.values() if c > 1)
        result = EvalResult(
            test_name="deduplication_quality",
            verdict=EvalVerdict.PASS if dup_count == 0 else EvalVerdict.FAIL,
            score=1.0 if dup_count == 0 else max(0.0, 1.0 - dup_count * 0.1),
            details=f"{dup_count} duplicate fact_keys"
        )
        results.append(result)
        stale_cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)).isoformat()
        stale = [m for m in active if (m.get("last_used_at") or m.get("created_at", "")) < stale_cutoff]
        result = EvalResult(
            test_name="freshness",
            verdict=EvalVerdict.PASS if len(stale) == 0 else EvalVerdict.WARNING,
            score=1.0 if len(stale) == 0 else max(0.0, 1.0 - len(stale) / max(total, 1)),
            details=f"{len(stale)}/{total} stale (>90d)"
        )
        results.append(result)
        suite.results = results
        scores = [r.score for r in results]
        suite.overall_score = sum(scores) / len(scores) if scores else 0.0
        suite.overall_verdict = (
            EvalVerdict.PASS if suite.overall_score >= 0.8
            else EvalVerdict.FAIL if suite.overall_score < 0.5
            else EvalVerdict.WARNING
        )
        return suite

    def evaluate_retrieval(self, user_id: str, query: str, expected_facts: List[str]) -> EvalSuite:
        suite = EvalSuite(name="retrieval_quality")
        if not self.retriever:
            suite.results = [EvalResult("retriever_available", EvalVerdict.SKIP, 0.0, "No retriever")]
            return suite
        results_found = self.retriever.search(query, user_id=user_id, limit=20)
        found_facts = [r.get("fact_key", "") for r in results_found] if results_found else []
        hits = sum(1 for f in expected_facts if f in found_facts)
        recall = hits / len(expected_facts) if expected_facts else 1.0
        suite.results = [
            EvalResult("retrieval_recall", EvalVerdict.PASS if recall >= 0.9 else EvalVerdict.FAIL, recall, f"{hits}/{len(expected_facts)} expected found"),
            EvalResult("retrieval_count", EvalVerdict.PASS if len(results_found) <= 20 else EvalVerdict.FAIL, 1.0 if len(results_found) <= 20 else 0.0, f"{len(results_found)} results")
        ]
        suite.overall_score = sum(r.score for r in suite.results) / len(suite.results)
        suite.overall_verdict = EvalVerdict.PASS if suite.overall_score >= 0.8 else EvalVerdict.FAIL
        return suite

    def run_full_eval(self, user_id: str, queries: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        health = self.evaluate_memory_health(user_id)
        retrieval_scores = []
        for q in (queries or []):
            r = self.evaluate_retrieval(user_id, q["query"], q.get("expected_facts", []))
            retrieval_scores.append(r.overall_score)
        avg_retrieval = sum(retrieval_scores) / len(retrieval_scores) if retrieval_scores else 1.0
        return {
            "health_score": health.overall_score,
            "retrieval_score": avg_retrieval,
            "overall_score": (health.overall_score + avg_retrieval) / 2,
            "health_details": {"tests": [(r.test_name, r.verdict.value, r.score) for r in health.results]},
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat()
        }


if __name__ == "__main__":
    print("Evaluation harness loaded successfully.")
    print(f"EvalVerdict members: {[v.value for v in EvalVerdict]}")
