"""Privacy and data governance for canonical memory system.

Phase 14 of the Adaptive Memory System. Enforces consent management,
data minimization, retention policies, export (GDPR/DSAR), and purge.

Sensitive interpretation must not be persisted automatically merely because
an LLM inferred it. Explicit deletion must propagate across every derived
system.
"""
import datetime as dt
from typing import Any, Dict, List, Optional
from enum import Enum


class ConsentScope(str, Enum):
    """Scopes for memory consent management."""
    EXTRACTION = "extraction"
    RETRIEVAL = "retrieval"
    SHARING = "sharing"
    ANALYTICS = "analytics"


class MemoryPrivacyManager:
    """Privacy and data governance layer for canonical memory.

    Manages consent receipts, GDPR data export, data purge, and retention
    enforcement. All operations are user-scoped and produce audit-ready
    results.
    """

    def __init__(self, db_client: Any) -> None:
        self.db = db_client

    # ── Consent ──────────────────────────────────────────────────────

    def check_consent(self, user_id: str, scope: ConsentScope) -> bool:
        """Check whether a user has granted consent for *scope*.

        Rules:
        - No receipt stored → EXTRACTION is denied (opt-in required),
          all other scopes are allowed (opt-out model).
        - Receipt exists → return the ``granted`` flag.
        """
        result = (
            self.db.table("memory_consent_receipts")
            .select("*")
            .eq("user_id", user_id)
            .eq("scope", scope.value)
            .limit(1)
            .execute()
        )
        if not result.data:
            return scope != ConsentScope.EXTRACTION
        record = result.data[0]
        return record.get("granted", True)

    def record_consent(
        self, user_id: str, scope: ConsentScope, granted: bool
    ) -> None:
        """Persist a consent decision (upsert by user + scope)."""
        self.db.table("memory_consent_receipts").upsert(
            {
                "user_id": user_id,
                "scope": scope.value,
                "granted": granted,
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        ).execute()

    # ── Export (GDPR / DSAR) ────────────────────────────────────────

    def export_user_data(self, user_id: str) -> Dict[str, Any]:
        """Export all canonical memories and consent history for *user_id*.

        Returns a dict ready for serialisation as a GDPR/DSAR response.
        """
        mems = (
            self.db.table("canonical_memories")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        consent = (
            self.db.table("memory_consent_receipts")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        return {
            "canonical_memories": mems.data,
            "consent_history": consent.data,
            "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    # ── Purge ────────────────────────────────────────────────────────

    def purge_user_data(self, user_id: str) -> Dict[str, Any]:
        """Hard-delete all canonical memories and consent receipts for *user_id*.

        Returns a summary of rows removed.
        """
        deleted: Dict[str, Any] = {
            "canonical_memories": 0,
            "consent_receipts": 0,
        }
        r1 = (
            self.db.table("canonical_memories")
            .delete()
            .eq("user_id", user_id)
            .execute()
        )
        deleted["canonical_memories"] = len(r1.data) if r1.data else 0

        r2 = (
            self.db.table("memory_consent_receipts")
            .delete()
            .eq("user_id", user_id)
            .execute()
        )
        deleted["consent_receipts"] = len(r2.data) if r2.data else 0

        deleted["purged_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        return deleted

    # ── Retention ────────────────────────────────────────────────────

    def get_retention_status(
        self, user_id: str, max_age_days: int = 365
    ) -> Dict[str, int]:
        """Return counts of active memories and those eligible for cleanup.

        A memory is eligible when its ``last_used_at`` (or ``created_at``
        as fallback) is older than *max_age_days*.
        """
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
            days=max_age_days
        )
        result = (
            self.db.table("canonical_memories")
            .select("id, created_at, last_used_at")
            .eq("user_id", user_id)
            .execute()
        )
        active = [r for r in result.data if not r.get("deleted_at")]
        expired = [
            r
            for r in active
            if (r.get("last_used_at") or r.get("created_at", ""))
            < cutoff.isoformat()
        ]
        return {
            "total_active": len(active),
            "eligible_for_cleanup": len(expired),
        }


if __name__ == "__main__":
    # Quick self-check
    class _Result:
        def __init__(self, data): self.data = data

    class _StubTable:
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def limit(self, *_a): return self
        def execute(self): return _Result([])

    class _StubClient:
        def table(self, *_a): return _StubTable()

    mgr = MemoryPrivacyManager(_StubClient())
    assert mgr.check_consent("u1", ConsentScope.EXTRACTION) is False
    assert mgr.check_consent("u1", ConsentScope.RETRIEVAL) is True
    print("privacy.py self-check passed")
