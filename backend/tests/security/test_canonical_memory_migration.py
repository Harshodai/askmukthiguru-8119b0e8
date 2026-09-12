"""Tests for canonical memory migration strategy (Phase 22)."""
import datetime as dt
import pytest
from services.canonical_memory.migration import (
    MigrationPhase,
    LegacyTable,
    MigrationProgress,
    MigrationManager,
    get_migration_manager,
)


class TestMigrationPhaseEnum:
    def test_all_phases_exist(self):
        phases = [p.value for p in MigrationPhase]
        assert "dual_read" in phases
        assert "canonical_only" in phases
        assert "legacy_cleanup" in phases
        assert "complete" in phases

    def test_phase_count(self):
        assert len(MigrationPhase) == 4

    def test_phase_string_values(self):
        assert MigrationPhase.DUAL_READ.value == "dual_read"
        assert MigrationPhase.CANONICAL_ONLY.value == "canonical_only"
        assert MigrationPhase.LEGACY_CLEANUP.value == "legacy_cleanup"
        assert MigrationPhase.COMPLETE.value == "complete"


class TestLegacyTableEnum:
    def test_all_tables_exist(self):
        tables = [t.value for t in LegacyTable]
        expected = [
            "guru_core_memory",
            "guru_memories",
            "guru_session_summaries",
            "conversation_memories",
            "user_brain_nodes",
            "user_episodes",
            "user_scene_blocks",
        ]
        for e in expected:
            assert e in tables

    def test_table_count(self):
        assert len(LegacyTable) == 7


class TestGetProgress:
    def test_default_phase(self):
        mgr = MigrationManager()
        progress = mgr.get_progress()
        assert progress.phase == MigrationPhase.DUAL_READ

    def test_default_counts(self):
        mgr = MigrationManager()
        progress = mgr.get_progress()
        assert progress.users_migrated == 0
        assert progress.users_remaining == 0
        assert progress.errors == 0

    def test_timestamp_set(self):
        mgr = MigrationManager()
        progress = mgr.get_progress()
        assert progress.timestamp != ""

    def test_returns_same_object(self):
        mgr = MigrationManager()
        p1 = mgr.get_progress()
        p2 = mgr.get_progress()
        assert p1 is p2


class TestMigrateUser:
    def test_returns_user_id(self):
        mgr = MigrationManager()
        result = mgr.migrate_user_memories("user-123")
        assert result["user_id"] == "user-123"

    def test_dual_read_enabled(self):
        mgr = MigrationManager()
        result = mgr.migrate_user_memories("user-123")
        assert result["dual_read_enabled"] is True

    def test_has_timestamp(self):
        mgr = MigrationManager()
        result = mgr.migrate_user_memories("user-123")
        assert "timestamp" in result

    def test_canonical_migrated_zero(self):
        mgr = MigrationManager()
        result = mgr.migrate_user_memories("user-123")
        assert result["canonical_migrated"] == 0


class TestVerifyMigration:
    def test_returns_user_id(self):
        mgr = MigrationManager()
        result = mgr.verify_migration("user-456")
        assert result["user_id"] == "user-456"

    def test_migration_verified(self):
        mgr = MigrationManager()
        result = mgr.verify_migration("user-456")
        assert result["migration_verified"] is True

    def test_canonical_active(self):
        mgr = MigrationManager()
        result = mgr.verify_migration("user-456")
        assert result["canonical_active"] is True

    def test_legacy_not_archived_by_default(self):
        mgr = MigrationManager()
        result = mgr.verify_migration("user-456")
        assert result["legacy_archived"] is False


class TestGetMigrationStats:
    def test_phase_in_stats(self):
        mgr = MigrationManager()
        stats = mgr.get_migration_stats()
        assert stats["phase"] == "dual_read"

    def test_error_rate_zero(self):
        mgr = MigrationManager()
        stats = mgr.get_migration_stats()
        assert stats["error_rate"] == 0.0

    def test_estimated_completion_zero(self):
        mgr = MigrationManager()
        stats = mgr.get_migration_stats()
        assert stats["estimated_completion_hours"] == 0.0

    def test_division_by_zero_safe(self):
        mgr = MigrationManager()
        stats = mgr.get_migration_stats()
        assert isinstance(stats["error_rate"], float)


class TestRollbackUser:
    def test_returns_user_id(self):
        mgr = MigrationManager()
        result = mgr.rollback_user("user-789")
        assert result["user_id"] == "user-789"

    def test_rolled_back_flag(self):
        mgr = MigrationManager()
        result = mgr.rollback_user("user-789")
        assert result["rolled_back"] is True

    def test_rollback_sets_dual_read(self):
        mgr = MigrationManager()
        result = mgr.rollback_user("user-789")
        assert result["phase"] == MigrationPhase.DUAL_READ.value


class TestArchiveLegacy:
    def test_returns_user_id(self):
        mgr = MigrationManager()
        result = mgr.archive_legacy("user-abc")
        assert result["user_id"] == "user-abc"

    def test_all_tables_archived(self):
        mgr = MigrationManager()
        result = mgr.archive_legacy("user-abc")
        for table in LegacyTable:
            assert table.value in result["archived"]

    def test_archive_has_timestamp(self):
        mgr = MigrationManager()
        result = mgr.archive_legacy("user-abc")
        assert "archived_at" in result

    def test_archive_counts_zero(self):
        mgr = MigrationManager()
        result = mgr.archive_legacy("user-abc")
        for count in result["archived"].values():
            assert count == 0


class TestGenerateReport:
    def test_report_has_status(self):
        mgr = MigrationManager()
        report = mgr.generate_report()
        assert "migration_status" in report

    def test_report_has_legacy_tables(self):
        mgr = MigrationManager()
        report = mgr.generate_report()
        assert len(report["legacy_tables"]) == 7

    def test_report_canonical_table(self):
        mgr = MigrationManager()
        report = mgr.generate_report()
        assert report["canonical_table"] == "canonical_memories"

    def test_report_recommendation_default(self):
        mgr = MigrationManager()
        report = mgr.generate_report()
        assert report["recommendation"] == "ready_for_canonical"

    def test_report_has_timestamp(self):
        mgr = MigrationManager()
        report = mgr.generate_report()
        assert "timestamp" in report


class TestMigrationCompletePhase:
    def test_complete_phase_recommendation(self):
        mgr = MigrationManager()
        mgr._progress.users_remaining = 0
        report = mgr.generate_report()
        assert report["recommendation"] == "ready_for_canonical"

    def test_dual_read_phase_recommendation(self):
        mgr = MigrationManager()
        mgr._progress.users_remaining = 50
        report = mgr.generate_report()
        assert report["recommendation"] == "continue_dual_read"

    def test_error_rate_with_errors(self):
        mgr = MigrationManager()
        mgr._progress.users_migrated = 10
        mgr._progress.users_remaining = 5
        mgr._progress.errors = 2
        stats = mgr.get_migration_stats()
        assert stats["error_rate"] == pytest.approx(2 / 15)

    def test_estimated_completion_with_remaining(self):
        mgr = MigrationManager()
        mgr._progress.users_remaining = 1000
        stats = mgr.get_migration_stats()
        assert stats["estimated_completion_hours"] == 10.0


class TestGetMigrationManager:
    def test_factory_returns_manager(self):
        mgr = get_migration_manager()
        assert isinstance(mgr, MigrationManager)

    def test_factory_with_db(self):
        mgr = get_migration_manager(db_client="fake_db")
        assert mgr.db == "fake_db"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
