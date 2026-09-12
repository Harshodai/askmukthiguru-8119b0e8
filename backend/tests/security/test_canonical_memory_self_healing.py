"""Tests for canonical memory self-healing — Phase 21."""
import pytest

from services.canonical_memory.self_healing import (
    DriftDetector,
    RepairAction,
    RepairOutcome,
    RepairRecord,
    SelfHealer,
    get_self_healer,
)


class TestDriftDetectorDefaultState:
    def test_default_detector_has_no_clients(self):
        detector = DriftDetector()
        assert detector.db is None
        assert detector.vector is None

    def test_detector_with_clients(self):
        detector = DriftDetector(db_client="db", vector_client="vec")
        assert detector.db == "db"
        assert detector.vector == "vec"


class TestDriftDetectorCanonicalVector:
    def test_canonical_vector_consistent(self):
        detector = DriftDetector()
        result = detector.detect_canonical_vector_drift("user1")
        assert result["drift_count"] == 0
        assert result["consistent"] is True


class TestDriftDetectorStale:
    def test_no_stale_memories(self):
        detector = DriftDetector()
        stale = detector.detect_stale_memories("user1")
        assert stale == []

    def test_stale_with_custom_max_age(self):
        detector = DriftDetector()
        stale = detector.detect_stale_memories("user1", max_age_days=30)
        assert stale == []


class TestDriftDetectorDuplicates:
    def test_no_duplicates(self):
        detector = DriftDetector()
        dupes = detector.detect_duplicates("user1")
        assert dupes == []

    def test_returns_empty_list(self):
        detector = DriftDetector()
        result = detector.detect_duplicates("user1")
        assert isinstance(result, list)


class TestDriftDetectorOrphans:
    def test_no_orphan_vectors(self):
        detector = DriftDetector()
        orphans = detector.detect_orphan_vectors("user1")
        assert orphans == []

    def test_returns_empty_list(self):
        detector = DriftDetector()
        result = detector.detect_orphan_vectors("user1")
        assert isinstance(result, list)


class TestFullDriftReport:
    def test_report_structure(self):
        detector = DriftDetector()
        report = detector.full_drift_report("user1")
        assert report["user_id"] == "user1"
        assert "canonical_vector_drift" in report
        assert "stale_count" in report
        assert "duplicate_groups" in report
        assert "orphan_vectors" in report
        assert "timestamp" in report

    def test_report_defaults_clean(self):
        detector = DriftDetector()
        report = detector.full_drift_report("user1")
        assert report["stale_count"] == 0
        assert report["duplicate_groups"] == 0
        assert report["orphan_vectors"] == 0
        assert report["canonical_vector_drift"]["consistent"] is True

    def test_report_has_timestamp(self):
        detector = DriftDetector()
        report = detector.full_drift_report("user1")
        assert isinstance(report["timestamp"], str)
        assert "T" in report["timestamp"]


class TestRepairRecord:
    def test_record_auto_timestamps(self):
        record = RepairRecord(action=RepairAction.UPDATE_METADATA, outcome=RepairOutcome.SUCCESS)
        assert record.timestamp != ""
        assert "T" in record.timestamp

    def test_record_with_items(self):
        record = RepairRecord(
            action=RepairAction.DELETE_ORPHANS,
            outcome=RepairOutcome.PARTIAL,
            items_affected=5,
            details="some details",
        )
        assert record.items_affected == 5
        assert record.details == "some details"

    def test_repair_action_values(self):
        assert RepairAction.RESYNC_CANONICAL.value == "resync_canonical"
        assert RepairAction.REBUILD_VECTORS.value == "rebuild_vectors"
        assert RepairAction.DELETE_ORPHANS.value == "delete_orphans"
        assert RepairAction.UPDATE_METADATA.value == "update_metadata"
        assert RepairAction.CONSOLIDATE_DUPLICATES.value == "consolidate_duplicates"

    def test_repair_outcome_values(self):
        assert RepairOutcome.SUCCESS.value == "success"
        assert RepairOutcome.PARTIAL.value == "partial"
        assert RepairOutcome.FAILED.value == "failed"
        assert RepairOutcome.SKIPPED.value == "skipped"


class TestSelfHealerStale:
    def test_repair_stale_returns_success(self):
        healer = get_self_healer()
        record = healer.repair_stale_memories("user1")
        assert record.outcome == RepairOutcome.SUCCESS
        assert record.action == RepairAction.UPDATE_METADATA

    def test_repair_stale_custom_age(self):
        healer = get_self_healer()
        record = healer.repair_stale_memories("user1", max_age_days=30)
        assert record.outcome == RepairOutcome.SUCCESS


class TestSelfHealerDuplicates:
    def test_repair_duplicates_returns_success(self):
        healer = get_self_healer()
        record = healer.repair_duplicates("user1")
        assert record.outcome == RepairOutcome.SUCCESS
        assert record.action == RepairAction.CONSOLIDATE_DUPLICATES


class TestSelfHealerOrphans:
    def test_repair_orphans_returns_success(self):
        healer = get_self_healer()
        record = healer.repair_orphan_vectors("user1")
        assert record.outcome == RepairOutcome.SUCCESS
        assert record.action == RepairAction.DELETE_ORPHANS


class TestFullRepair:
    def test_full_repair_returns_all_records(self):
        healer = get_self_healer()
        result = healer.full_repair("user1")
        assert result["user_id"] == "user1"
        assert len(result["repairs"]) == 3

    def test_full_repair_all_successful(self):
        healer = get_self_healer()
        result = healer.full_repair("user1")
        assert result["all_successful"] is True

    def test_full_repair_total_affected(self):
        healer = get_self_healer()
        result = healer.full_repair("user1")
        assert result["total_affected"] == 0

    def test_full_repair_has_timestamp(self):
        healer = get_self_healer()
        result = healer.full_repair("user1")
        assert "timestamp" in result
        assert "T" in result["timestamp"]

    def test_full_repair_repair_structure(self):
        healer = get_self_healer()
        result = healer.full_repair("user1")
        for repair in result["repairs"]:
            assert "action" in repair
            assert "outcome" in repair
            assert "affected" in repair


class TestHealthCheckHealthy:
    def test_healthy_report(self):
        healer = get_self_healer()
        report = healer.health_check("user1")
        assert report["healthy"] is True
        assert report["issues_found"] == 0
        assert report["recommendation"] == "no_action_needed"

    def test_healthy_has_user_id(self):
        healer = get_self_healer()
        report = healer.health_check("user1")
        assert report["user_id"] == "user1"

    def test_healthy_has_report(self):
        healer = get_self_healer()
        report = healer.health_check("user1")
        assert "report" in report
        assert isinstance(report["report"], dict)


class TestHealthCheckIssues:
    def test_issues_found_zero(self):
        healer = get_self_healer()
        report = healer.health_check("user1")
        assert report["issues_found"] == 0

    def test_report_subcounts(self):
        healer = get_self_healer()
        report = healer.health_check("user1")
        assert report["report"]["stale_count"] == 0
        assert report["report"]["duplicate_groups"] == 0
        assert report["report"]["orphan_vectors"] == 0


class TestGetSelfHealer:
    def test_factory_returns_healer(self):
        healer = get_self_healer()
        assert isinstance(healer, SelfHealer)

    def test_factory_with_clients(self):
        healer = get_self_healer(db_client="db", vector_client="vec", monitor="mon")
        assert healer.db == "db"
        assert healer.vector == "vec"
        assert healer.monitor == "mon"

    def test_healer_has_detector(self):
        healer = get_self_healer()
        assert isinstance(healer.detector, DriftDetector)
