"""Tests for canonical memory red team adversarial testing (Phase 25)."""

import pytest

from services.canonical_memory.red_team import (
    AttackCategory,
    AttackLibrary,
    AttackResult,
    AttackVector,
    RedTeamTestRunner,
    get_red_team_runner,
)


class TestAttackCategoryEnum:
    def test_all_values(self):
        cats = [e.value for e in AttackCategory]
        assert "injection" in cats
        assert "extraction" in cats
        assert "manipulation" in cats
        assert "cross_user" in cats
        assert "denial_of_service" in cats

    def test_enum_count(self):
        assert len(AttackCategory) == 5


class TestAttackVectorDataclass:
    def test_basic_vector(self):
        v = AttackVector(
            category=AttackCategory.INJECTION,
            payload="test payload",
            description="test",
        )
        assert v.category == AttackCategory.INJECTION
        assert v.payload == "test payload"
        assert v.severity == "medium"

    def test_high_severity_vector(self):
        v = AttackVector(
            AttackCategory.EXTRACTION,
            "payload",
            "desc",
            severity="high",
        )
        assert v.severity == "high"


class TestAttackLibraryHasVectors:
    def test_injection_count(self):
        assert len(AttackLibrary.INJECTION_ATTACKS) >= 4

    def test_extraction_count(self):
        assert len(AttackLibrary.EXTRACTION_ATTACKS) >= 3

    def test_manipulation_count(self):
        assert len(AttackLibrary.MANIPULATION_ATTACKS) >= 3

    def test_cross_user_count(self):
        assert len(AttackLibrary.CROSS_USER_ATTACKS) >= 2

    def test_dos_count(self):
        assert len(AttackLibrary.DOS_ATTACKS) >= 1

    def test_all_vectors(self):
        all_vecs = AttackLibrary.all_vectors()
        assert len(all_vecs) >= 15

    def test_count_matches_all_vectors(self):
        assert AttackLibrary.count() == len(AttackLibrary.all_vectors())

    def test_by_category(self):
        injection = AttackLibrary.by_category(AttackCategory.INJECTION)
        assert len(injection) >= 4
        for v in injection:
            assert v.category == AttackCategory.INJECTION

    def test_by_category_empty(self):
        # No vectors for a category that has none — but all categories have vectors
        # just verify it returns list
        result = AttackLibrary.by_category(AttackCategory.INJECTION)
        assert isinstance(result, list)


class TestAttackResult:
    def test_result_fields(self):
        r = AttackResult(
            attack="injection",
            payload="test...",
            blocked=True,
            reason="safety_gate_blocked",
            severity="medium",
        )
        assert r.blocked is True
        assert r.latency_ms == 0.0
        assert r.metadata == {}

    def test_result_not_blocked(self):
        r = AttackResult(
            attack="extraction",
            payload="...",
            blocked=False,
            reason="missed",
            severity="high",
        )
        assert r.blocked is False


class TestInjectionAllBlocked:
    def test_injection_results_all_blocked(self):
        runner = get_red_team_runner()
        results = runner.test_injection_resistance()
        assert len(results) >= 4
        for r in results:
            assert r.blocked is True
            assert r.reason == "safety_gate_blocked"

    def test_injection_severity_present(self):
        runner = get_red_team_runner()
        results = runner.test_injection_resistance()
        severities = {r.severity for r in results}
        assert "medium" in severities or "high" in severities


class TestExtractionAllBlocked:
    def test_extraction_results_all_blocked(self):
        runner = get_red_team_runner()
        results = runner.test_extraction_resistance()
        assert len(results) >= 3
        for r in results:
            assert r.blocked is True
            assert r.reason == "access_control"


class TestCrossUserAllBlocked:
    def test_cross_user_results_all_blocked(self):
        runner = get_red_team_runner()
        results = runner.test_cross_user_isolation()
        assert len(results) >= 2
        for r in results:
            assert r.blocked is True
            assert r.reason == "user_isolation"


class TestManipulationAllBlocked:
    def test_manipulation_results_all_blocked(self):
        runner = get_red_team_runner()
        results = runner.test_manipulation_resistance()
        assert len(results) >= 3
        for r in results:
            assert r.blocked is True
            assert r.reason == "input_validation"


class TestDosAllBlocked:
    def test_dos_results_all_blocked(self):
        runner = get_red_team_runner()
        results = runner.test_dos_resistance()
        assert len(results) >= 1
        for r in results:
            assert r.blocked is True
            assert r.reason == "size_limit_enforced"


class TestFullRedTeamAllBlocked:
    def test_full_red_team_all_blocked(self):
        runner = get_red_team_runner()
        report = runner.run_full_red_team()
        assert report["all_blocked"] is True
        assert report["passed_through"] == 0
        assert report["pass_rate"] == 1.0

    def test_full_red_team_structure(self):
        runner = get_red_team_runner()
        report = runner.run_full_red_team()
        assert "total_attacks" in report
        assert "blocked" in report
        assert "by_category" in report
        assert "high_severity" in report
        assert "timestamp" in report

    def test_full_red_team_category_breakdown(self):
        runner = get_red_team_runner()
        report = runner.run_full_red_team()
        cats = report["by_category"]
        for cat_name in ("injection", "extraction", "cross_user", "manipulation", "denial_of_service"):
            assert cat_name in cats
            assert "total" in cats[cat_name]
            assert "blocked" in cats[cat_name]
            assert cats[cat_name]["total"] == cats[cat_name]["blocked"]

    def test_full_red_team_high_severity(self):
        runner = get_red_team_runner()
        report = runner.run_full_red_team()
        hs = report["high_severity"]
        assert hs["total"] >= 1
        assert hs["blocked"] == hs["total"]

    def test_full_red_team_timestamp(self):
        runner = get_red_team_runner()
        report = runner.run_full_red_team()
        assert "T" in report["timestamp"]


class TestRedTeamResultsTracked:
    def test_results_accumulated(self):
        runner = get_red_team_runner()
        runner.test_injection_resistance()
        runner.test_extraction_resistance()
        all_results = runner.get_all_results()
        assert len(all_results) >= 7

    def test_results_reset(self):
        runner = get_red_team_runner()
        runner.test_injection_resistance()
        assert len(runner.get_all_results()) > 0
        runner.reset()
        assert len(runner.get_all_results()) == 0


class TestGetRedTeamRunner:
    def test_factory_returns_runner(self):
        runner = get_red_team_runner()
        assert isinstance(runner, RedTeamTestRunner)

    def test_factory_with_dependencies(self):
        runner = get_red_team_runner(memory_system="mem", judge="j", resolver="r")
        assert runner.memory == "mem"
        assert runner.judge == "j"
        assert runner.resolver == "r"
