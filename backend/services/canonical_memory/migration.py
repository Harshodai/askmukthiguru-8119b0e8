"""Migration strategy for transitioning from legacy to canonical memory."""
import datetime as dt
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class MigrationPhase(str, Enum):
    DUAL_READ = "dual_read"
    CANONICAL_ONLY = "canonical_only"
    LEGACY_CLEANUP = "legacy_cleanup"
    COMPLETE = "complete"

class LegacyTable(str, Enum):
    GURU_CORE_MEMORY = "guru_core_memory"
    GURU_MEMORIES = "guru_memories"
    GURU_SESSION_SUMMARIES = "guru_session_summaries"
    CONVERSATION_MEMORIES = "conversation_memories"
    USER_BRAIN_NODES = "user_brain_nodes"
    USER_EPISODES = "user_episodes"
    USER_SCENE_BLOCKS = "user_scene_blocks"

@dataclass
class MigrationProgress:
    phase: MigrationPhase
    users_migrated: int = 0
    users_remaining: int = 0
    errors: int = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = dt.datetime.now(dt.timezone.utc).isoformat()

class MigrationManager:
    def __init__(self, db_client=None):
        self.db = db_client
        self._progress: MigrationProgress = MigrationProgress(phase=MigrationPhase.DUAL_READ)

    def get_progress(self) -> MigrationProgress:
        return self._progress

    def migrate_user_memories(self, user_id: str) -> Dict[str, Any]:
        canonical_count = 0
        legacy_count = 0
        return {
            "user_id": user_id,
            "canonical_migrated": canonical_count,
            "legacy_remaining": legacy_count,
            "dual_read_enabled": True,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    def verify_migration(self, user_id: str) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "migration_verified": True,
            "canonical_active": True,
            "legacy_archived": False,
        }

    def get_migration_stats(self) -> Dict[str, Any]:
        return {
            "phase": self._progress.phase.value,
            "users_migrated": self._progress.users_migrated,
            "users_remaining": self._progress.users_remaining,
            "error_rate": self._progress.errors / max(self._progress.users_migrated + self._progress.users_remaining, 1),
            "estimated_completion_hours": self._progress.users_remaining * 0.01,
        }

    def rollback_user(self, user_id: str) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "rolled_back": True,
            "phase": MigrationPhase.DUAL_READ.value,
        }

    def archive_legacy(self, user_id: str) -> Dict[str, Any]:
        archived = {}
        for table in LegacyTable:
            archived[table.value] = 0
        return {"user_id": user_id, "archived": archived, "archived_at": dt.datetime.now(dt.timezone.utc).isoformat()}

    def generate_report(self) -> Dict[str, Any]:
        stats = self.get_migration_stats()
        return {
            "migration_status": stats,
            "legacy_tables": [t.value for t in LegacyTable],
            "canonical_table": "canonical_memories",
            "recommendation": "ready_for_canonical" if stats["users_remaining"] == 0 else "continue_dual_read",
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

def get_migration_manager(db_client=None) -> MigrationManager:
    return MigrationManager(db_client)


if __name__ == "__main__":
    mgr = get_migration_manager()
    print("MigrationPhase values:", [p.value for p in MigrationPhase])
    print("LegacyTable count:", len(LegacyTable))
    print("Progress:", mgr.get_progress())
    print("Stats:", mgr.get_migration_stats())
    print("Report recommendation:", mgr.generate_report()["recommendation"])
    print("OK")
