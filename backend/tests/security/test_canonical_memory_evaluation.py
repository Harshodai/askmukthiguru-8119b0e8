"""Tests for canonical memory evaluation harness (Phase 16)."""
import datetime as dt
import unittest
from unittest.mock import MagicMock, patch

from services.canonical_memory.evaluation import (
    EvalResult,
    EvalSuite,
    EvalVerdict,
    MemoryEvaluator,
)


class _FakeTable:
    def __init__(self, rows):
        self._rows = rows
        self._filters = {}

    def select(self, _cols):
        return self

    def eq(self, _col, val):
        self._filters[_col] = val
        return self

    def execute(self):
        uid = self._filters.get("user_id")
        data = [r for r in self._rows if r.get("user_id") == uid] if uid else self._rows
        result = MagicMock()
        result.data = data
        return result


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _FakeTable(self._rows)


class _FakeRetriever:
    def __init__(self, results):
        self._results = results

    def search(self, query, user_id=None, limit=20):
        return self._results


class TestEvalResultTimestamp(unittest.TestCase):
    def test_timestamp_auto_populated(self):
        r = EvalResult("t", EvalVerdict.PASS, 1.0, "ok")
        self.assertIn("T", r.timestamp)

    def test_timestamp_preserved(self):
        ts = "2026-01-01T00:00:00+00:00"
        r = EvalResult("t", EvalVerdict.PASS, 1.0, "ok", timestamp=ts)
        self.assertEqual(r.timestamp, ts)


class TestEvalSuiteDefaults(unittest.TestCase):
    def test_default_fields(self):
        s = EvalSuite(name="test")
        self.assertIsNone(s.results)
        self.assertEqual(s.overall_score, 0.0)
        self.assertEqual(s.overall_verdict, EvalVerdict.SKIP)


class TestHealthNoMemories(unittest.TestCase):
    def test_empty_canonical(self):
        db = _FakeDB([])
        ev = MemoryEvaluator(db)
        suite = ev.evaluate_memory_health("u1")
        self.assertEqual(suite.name, "memory_health")
        self.assertEqual(len(suite.results), 3)
        self.assertEqual(suite.results[0].verdict, EvalVerdict.WARNING)
        self.assertEqual(suite.results[0].score, 0.0)
        self.assertIn("0/0", suite.results[0].details)


class TestHealthWithActiveMemories(unittest.TestCase):
    def test_active_memories(self):
        rows = [
            {"user_id": "u1", "status": "active", "fact_key": "fk1", "created_at": dt.datetime.now(dt.timezone.utc).isoformat()},
            {"user_id": "u1", "status": "active", "fact_key": "fk2", "created_at": dt.datetime.now(dt.timezone.utc).isoformat()},
        ]
        db = _FakeDB(rows)
        ev = MemoryEvaluator(db)
        suite = ev.evaluate_memory_health("u1")
        self.assertEqual(suite.results[0].verdict, EvalVerdict.PASS)
        self.assertEqual(suite.results[0].score, 1.0)
        self.assertEqual(suite.overall_verdict, EvalVerdict.PASS)


class TestDeduplicationNoDuplicates(unittest.TestCase):
    def test_unique_fact_keys(self):
        rows = [
            {"user_id": "u1", "status": "active", "fact_key": "fk1", "created_at": dt.datetime.now(dt.timezone.utc).isoformat()},
            {"user_id": "u1", "status": "active", "fact_key": "fk2", "created_at": dt.datetime.now(dt.timezone.utc).isoformat()},
        ]
        db = _FakeDB(rows)
        ev = MemoryEvaluator(db)
        suite = ev.evaluate_memory_health("u1")
        dedup = [r for r in suite.results if r.test_name == "deduplication_quality"][0]
        self.assertEqual(dedup.verdict, EvalVerdict.PASS)
        self.assertEqual(dedup.score, 1.0)


class TestDeduplicationWithDuplicates(unittest.TestCase):
    def test_duplicate_fact_keys(self):
        rows = [
            {"user_id": "u1", "status": "active", "fact_key": "fk1", "created_at": dt.datetime.now(dt.timezone.utc).isoformat()},
            {"user_id": "u1", "status": "active", "fact_key": "fk1", "created_at": dt.datetime.now(dt.timezone.utc).isoformat()},
            {"user_id": "u1", "status": "active", "fact_key": "fk2", "created_at": dt.datetime.now(dt.timezone.utc).isoformat()},
        ]
        db = _FakeDB(rows)
        ev = MemoryEvaluator(db)
        suite = ev.evaluate_memory_health("u1")
        dedup = [r for r in suite.results if r.test_name == "deduplication_quality"][0]
        self.assertEqual(dedup.verdict, EvalVerdict.FAIL)
        self.assertLess(dedup.score, 1.0)


class TestFreshnessAllRecent(unittest.TestCase):
    def test_no_stale(self):
        rows = [
            {"user_id": "u1", "status": "active", "fact_key": "fk1",
             "last_used_at": dt.datetime.now(dt.timezone.utc).isoformat(),
             "created_at": dt.datetime.now(dt.timezone.utc).isoformat()},
        ]
        db = _FakeDB(rows)
        ev = MemoryEvaluator(db)
        suite = ev.evaluate_memory_health("u1")
        fresh = [r for r in suite.results if r.test_name == "freshness"][0]
        self.assertEqual(fresh.verdict, EvalVerdict.PASS)
        self.assertEqual(fresh.score, 1.0)


class TestFreshnessSomeStale(unittest.TestCase):
    def test_stale_memories(self):
        stale_time = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=120)).isoformat()
        recent_time = dt.datetime.now(dt.timezone.utc).isoformat()
        rows = [
            {"user_id": "u1", "status": "active", "fact_key": "fk1", "last_used_at": stale_time, "created_at": stale_time},
            {"user_id": "u1", "status": "active", "fact_key": "fk2", "last_used_at": recent_time, "created_at": recent_time},
        ]
        db = _FakeDB(rows)
        ev = MemoryEvaluator(db)
        suite = ev.evaluate_memory_health("u1")
        fresh = [r for r in suite.results if r.test_name == "freshness"][0]
        self.assertEqual(fresh.verdict, EvalVerdict.WARNING)
        self.assertLess(fresh.score, 1.0)


class TestRetrievalNoRetriever(unittest.TestCase):
    def test_skip_when_no_retriever(self):
        db = _FakeDB([])
        ev = MemoryEvaluator(db, retriever=None)
        suite = ev.evaluate_retrieval("u1", "test", ["fk1"])
        self.assertEqual(suite.results[0].verdict, EvalVerdict.SKIP)


class TestRetrievalWithResults(unittest.TestCase):
    def test_good_recall(self):
        retriever = _FakeRetriever([{"fact_key": "fk1"}, {"fact_key": "fk2"}, {"fact_key": "fk3"}])
        db = _FakeDB([])
        ev = MemoryEvaluator(db, retriever=retriever)
        suite = ev.evaluate_retrieval("u1", "test", ["fk1", "fk2", "fk3"])
        self.assertEqual(suite.results[0].verdict, EvalVerdict.PASS)
        self.assertEqual(suite.results[0].score, 1.0)
        self.assertEqual(suite.overall_verdict, EvalVerdict.PASS)


class TestRetrievalPoorRecall(unittest.TestCase):
    def test_low_recall(self):
        retriever = _FakeRetriever([{"fact_key": "fk1"}])
        db = _FakeDB([])
        ev = MemoryEvaluator(db, retriever=retriever)
        suite = ev.evaluate_retrieval("u1", "test", ["fk1", "fk2", "fk3"])
        self.assertEqual(suite.results[0].verdict, EvalVerdict.FAIL)
        self.assertLess(suite.results[0].score, 1.0)


class TestRunFullEvalNoQueries(unittest.TestCase):
    def test_no_queries(self):
        db = _FakeDB([])
        ev = MemoryEvaluator(db)
        result = ev.run_full_eval("u1")
        self.assertIn("health_score", result)
        self.assertIn("retrieval_score", result)
        self.assertIn("overall_score", result)
        self.assertIn("timestamp", result)
        self.assertEqual(result["retrieval_score"], 1.0)


class TestOverallScoreCalculation(unittest.TestCase):
    def test_score_averaging(self):
        rows = [
            {"user_id": "u1", "status": "active", "fact_key": "fk1",
             "last_used_at": dt.datetime.now(dt.timezone.utc).isoformat(),
             "created_at": dt.datetime.now(dt.timezone.utc).isoformat()},
        ]
        db = _FakeDB(rows)
        ev = MemoryEvaluator(db)
        result = ev.run_full_eval("u1")
        self.assertGreaterEqual(result["overall_score"], 0.0)
        self.assertLessEqual(result["overall_score"], 1.0)
        self.assertIsInstance(result["health_details"]["tests"], list)


if __name__ == "__main__":
    unittest.main()
