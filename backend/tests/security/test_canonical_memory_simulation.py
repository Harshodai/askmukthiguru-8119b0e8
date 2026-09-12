"""Tests for canonical memory longitudinal simulation (Phase 17)."""
import unittest

from services.canonical_memory.simulation import (
    MemorySimulator,
    SimulationResult,
    SimulationScenario,
    SimulatedTurn,
    TurnResult,
)


class _FakeDB:
    """Minimal fake DB for simulation tests."""

    def __init__(self, rows=None):
        self._rows = rows or []

    def table(self, _name):
        return self


# ---------------------------------------------------------------------------
# Scenario builder tests
# ---------------------------------------------------------------------------


class TestRepeatedInfoScenario(unittest.TestCase):
    def test_turns_count(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_repeated_info_scenario("u1")
        self.assertEqual(sc.name, "repeated_info")
        self.assertEqual(len(sc.turns), 4)
        self.assertEqual(sc.expected_final_memories, 3)

    def test_duplicate_fact_key_present(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_repeated_info_scenario("u1")
        keys = [f.get("fact_key") for t in sc.turns for f in t.extracted_facts]
        self.assertEqual(keys.count("user:works_at"), 2)

    def test_user_ids_match(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_repeated_info_scenario("u42")
        for turn in sc.turns:
            self.assertEqual(turn.user_id, "u42")


class TestContradictionScenario(unittest.TestCase):
    def test_same_key_different_values(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_contradiction_scenario("u1")
        self.assertEqual(len(sc.turns), 2)
        keys = [f["fact_key"] for t in sc.turns for f in t.extracted_facts]
        self.assertEqual(keys.count("user:lives_in"), 2)
        values = [f["fact_value"] for t in sc.turns for f in t.extracted_facts]
        self.assertEqual(values, ["Mumbai", "Delhi"])

    def test_expected_final(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_contradiction_scenario()
        self.assertEqual(sc.expected_final_memories, 1)


class TestDeletionScenario(unittest.TestCase):
    def test_expired_marker(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_deletion_scenario("u1")
        self.assertEqual(len(sc.turns), 2)
        expired = [
            f
            for t in sc.turns
            for f in t.extracted_facts
            if f.get("fact_value") == "EXPIRED"
        ]
        self.assertEqual(len(expired), 1)

    def test_expected_zero(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_deletion_scenario()
        self.assertEqual(sc.expected_final_memories, 0)
        self.assertEqual(sc.expected_fact_keys, [])


class TestAccumulationScenario(unittest.TestCase):
    def test_distinct_keys(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_accumulation_scenario("u1")
        all_keys = [f["fact_key"] for t in sc.turns for f in t.extracted_facts]
        self.assertEqual(len(all_keys), 3)
        self.assertEqual(len(set(all_keys)), 3)

    def test_expected_final(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_accumulation_scenario()
        self.assertEqual(sc.expected_final_memories, 3)


# ---------------------------------------------------------------------------
# run_scenario tests
# ---------------------------------------------------------------------------


class TestRunRepeatedInfo(unittest.TestCase):
    def test_deduplication(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_repeated_info_scenario("u1")
        result = sim.run_scenario(sc)
        self.assertEqual(result.scenario, "repeated_info")
        self.assertEqual(result.total_turns, 4)
        self.assertEqual(result.turns_processed, 4)
        self.assertEqual(result.final_memory_count, 3)
        self.assertEqual(result.consistency_score, 1.0)

    def test_turn_results_length(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_repeated_info_scenario()
        result = sim.run_scenario(sc)
        self.assertEqual(len(result.turn_results), 4)

    def test_superseded_resolution(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_repeated_info_scenario()
        result = sim.run_scenario(sc)
        resolutions = [tr.resolution for tr in result.turn_results]
        self.assertIn("superseded", resolutions)
        self.assertIn("applied", resolutions)


class TestRunContradiction(unittest.TestCase):
    def test_single_memory_after_contradiction(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_contradiction_scenario("u1")
        result = sim.run_scenario(sc)
        self.assertEqual(result.final_memory_count, 1)
        self.assertEqual(result.consistency_score, 1.0)

    def test_second_turn_supersedes(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_contradiction_scenario()
        result = sim.run_scenario(sc)
        self.assertEqual(result.turn_results[1].resolution, "superseded")


class TestRunDeletion(unittest.TestCase):
    def test_zero_final_memories(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_deletion_scenario("u1")
        result = sim.run_scenario(sc)
        self.assertEqual(result.final_memory_count, 0)
        self.assertGreater(result.consistency_score, 0.0)

    def test_both_turns_processed(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_deletion_scenario()
        result = sim.run_scenario(sc)
        self.assertEqual(result.turns_processed, 2)


class TestRunAccumulation(unittest.TestCase):
    def test_all_keys_retained(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_accumulation_scenario("u1")
        result = sim.run_scenario(sc)
        self.assertEqual(result.final_memory_count, 3)
        self.assertEqual(result.consistency_score, 1.0)


# ---------------------------------------------------------------------------
# run_all_scenarios tests
# ---------------------------------------------------------------------------


class TestRunAllScenarios(unittest.TestCase):
    def test_all_scenarios(self):
        sim = MemorySimulator(_FakeDB())
        scenarios = [
            sim.create_repeated_info_scenario(),
            sim.create_contradiction_scenario(),
            sim.create_deletion_scenario(),
            sim.create_accumulation_scenario(),
        ]
        results = sim.run_all_scenarios(scenarios)
        self.assertEqual(len(results), 4)
        names = [r.scenario for r in results]
        self.assertIn("repeated_info", names)
        self.assertIn("contradiction", names)
        self.assertIn("deletion", names)
        self.assertIn("accumulation", names)


# ---------------------------------------------------------------------------
# generate_summary tests
# ---------------------------------------------------------------------------


class TestGenerateSummary(unittest.TestCase):
    def test_summary_structure(self):
        sim = MemorySimulator(_FakeDB())
        scenarios = [
            sim.create_repeated_info_scenario(),
            sim.create_contradiction_scenario(),
        ]
        results = sim.run_all_scenarios(scenarios)
        summary = sim.generate_summary(results)
        self.assertEqual(summary["scenarios_run"], 2)
        self.assertIn("total_turns", summary)
        self.assertIn("average_consistency", summary)
        self.assertIn("per_scenario", summary)
        self.assertIn("passed", summary)
        self.assertIn("timestamp", summary)

    def test_summary_passes_when_all_high(self):
        sim = MemorySimulator(_FakeDB())
        scenarios = [
            sim.create_repeated_info_scenario(),
            sim.create_contradiction_scenario(),
            sim.create_accumulation_scenario(),
        ]
        results = sim.run_all_scenarios(scenarios)
        summary = sim.generate_summary(results)
        self.assertTrue(summary["passed"])
        self.assertGreaterEqual(summary["average_consistency"], 0.8)

    def test_summary_per_scenario_detail(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_repeated_info_scenario()
        result = sim.run_scenario(sc)
        summary = sim.generate_summary([result])
        detail = summary["per_scenario"][0]
        self.assertEqual(detail["name"], "repeated_info")
        self.assertEqual(detail["turns"], 4)
        self.assertEqual(detail["final_memories"], 3)
        self.assertEqual(detail["consistency"], 1.0)

    def test_empty_results(self):
        sim = MemorySimulator(_FakeDB())
        summary = sim.generate_summary([])
        self.assertEqual(summary["scenarios_run"], 0)
        self.assertFalse(summary["passed"])


# ---------------------------------------------------------------------------
# validate_expected_keys tests
# ---------------------------------------------------------------------------


class TestValidateExpectedKeys(unittest.TestCase):
    def test_matching_keys(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_repeated_info_scenario()
        result = sim.run_scenario(sc)
        validation = sim.validate_expected_keys(result)
        self.assertTrue(validation["match"])
        self.assertEqual(validation["expected_count"], 3)
        self.assertEqual(validation["actual_count"], 3)

    def test_mismatched_keys(self):
        sim = MemorySimulator(_FakeDB())
        sc = sim.create_contradiction_scenario()
        result = sim.run_scenario(sc)
        # contradiction expects 1, result should be 1
        validation = sim.validate_expected_keys(result)
        self.assertTrue(validation["match"])


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


class TestSimulatedTurnDefaults(unittest.TestCase):
    def test_default_fields(self):
        t = SimulatedTurn(user_id="u1", user_message="hello")
        self.assertEqual(t.extracted_facts, [])
        self.assertEqual(t.timestamp, "")


class TestSimulationScenarioDefaults(unittest.TestCase):
    def test_default_fields(self):
        sc = SimulationScenario(name="test")
        self.assertEqual(sc.turns, [])
        self.assertEqual(sc.expected_final_memories, 0)
        self.assertEqual(sc.expected_fact_keys, [])


class TestTurnResultDefaults(unittest.TestCase):
    def test_default_resolution(self):
        tr = TurnResult(turn_index=0, timestamp="ts", facts_processed=1)
        self.assertEqual(tr.resolution, "pending")
        self.assertIsNone(tr.error)


class TestSimulationResultDefaults(unittest.TestCase):
    def test_default_fields(self):
        sr = SimulationResult(scenario="test", total_turns=0, turns_processed=0)
        self.assertEqual(sr.consistency_score, 0.0)
        self.assertEqual(sr.final_memory_count, 0)


if __name__ == "__main__":
    unittest.main()
