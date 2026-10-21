"""Privacy and data governance for canonical memory system.

Phase 14 of the Adaptive Memory System. Enforces consent management,
data minimization, retention policies, export (GDPR/DSAR), and purge.

Sensitive interpretation must not be persisted automatically merely because
an LLM inferred it. Explicit deletion must propagate across every derived
system.
"""

import datetime as dt
from enum import Enum
from typing import Any

from services.tenant_context import TenantContext


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

    def check_consent(
        self, user_id: str, scope: ConsentScope, tenant_id: str | None = None
    ) -> bool:
        """Check the latest append-only global memory-consent event.

        The receipt schema has a policy version, tenant, grant, and revocation
        timestamp—not a per-scope column. A missing/latest revoked receipt is
        denied for every memory scope; never resurrect an older grant.
        """
        resolved_tenant = tenant_id if tenant_id is not None else TenantContext.get()
        if not isinstance(resolved_tenant, str) or not resolved_tenant.strip():
            return False
        try:
            result = (
                self.db.table("memory_consent_receipts")
                .select("granted,revoked_at,event_sequence")
                .eq("user_id", user_id)
                .eq("tenant_id", resolved_tenant)
                .eq("consent_version", "memory-v1")
                .order("event_sequence", desc=True)
                .limit(1)
                .execute()
            )
        except Exception:
            return False
        rows = result.data or []
        if not rows:
            return False
        latest = rows[0]
        return latest.get("granted") is True and latest.get("revoked_at") is None

    def record_consent(
        self,
        user_id: str,
        scope: ConsentScope,
        granted: bool,
        tenant_id: str | None = None,
        consent_version: str = "memory-v1",
    ) -> None:
        """Append a receipt using the real schema; no overwrite/upsert."""
        resolved_tenant = tenant_id if tenant_id is not None else TenantContext.get()
        if not isinstance(resolved_tenant, str) or not resolved_tenant.strip():
            raise ValueError("A tenant_id is required to record memory consent")
        now = dt.datetime.now(dt.UTC).isoformat()
        result = self.db.table("memory_consent_receipts").insert(
            {
                "user_id": user_id,
                "tenant_id": resolved_tenant,
                "consent_version": consent_version,
                "granted": bool(granted),
                "created_at": now,
                "revoked_at": None if granted else now,
            }
        ).execute()
        if not getattr(result, "data", None):
            raise RuntimeError("Memory consent receipt was not persisted")

    # ── Export (GDPR / DSAR) ────────────────────────────────────────

    def export_user_data(
        self, user_id: str, tenant_id: str | None = None
    ) -> dict[str, Any]:
        """Export all canonical memories and consent history for *user_id*.

        Returns a dict ready for serialisation as a GDPR/DSAR response.
        """
        resolved_tenant = tenant_id if tenant_id is not None else TenantContext.get()
        mems = (
            self.db.table("canonical_memories")
            .select("*")
            .eq("user_id", user_id)
            .eq("tenant_id", resolved_tenant)
            .execute()
        )
        consent = (
            self.db.table("memory_consent_receipts")
            .select("*")
            .eq("user_id", user_id)
            .eq("tenant_id", resolved_tenant)
            .order("event_sequence", desc=True)
            .execute()
        )
        return {
            "canonical_memories": mems.data,
            "consent_history": consent.data,
            "exported_at": dt.datetime.now(dt.UTC).isoformat(),
        }

    # ── Purge ────────────────────────────────────────────────────────

    def purge_user_data(self, user_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        """Hard-delete all canonical memories and consent receipts for *user_id*.

        Returns a summary of rows removed.
        """
        deleted: dict[str, Any] = {
            "canonical_memories": 0,
            "consent_receipts": 0,
        }
        resolved_tenant = tenant_id if tenant_id is not None else TenantContext.get()
        r1 = (
            self.db.table("canonical_memories")
            .delete()
            .eq("user_id", user_id)
            .eq("tenant_id", resolved_tenant)
            .execute()
        )
        deleted["canonical_memories"] = len(r1.data) if r1.data else 0

        r2 = (
            self.db.table("memory_consent_receipts")
            .delete()
            .eq("user_id", user_id)
            .eq("tenant_id", resolved_tenant)
            .execute()
        )
        deleted["consent_receipts"] = len(r2.data) if r2.data else 0

        deleted["purged_at"] = dt.datetime.now(dt.UTC).isoformat()
        return deleted

    # ── Retention ────────────────────────────────────────────────────

    def get_retention_status(
        self, user_id: str, max_age_days: int = 365, tenant_id: str | None = None
    ) -> dict[str, int]:
        """Return counts of active memories and those eligible for cleanup.

        A memory is eligible when its ``last_used_at`` (or ``created_at``
        as fallback) is older than *max_age_days*.
        """
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=max_age_days)
        result = (
            self.db.table("canonical_memories")
            .select("id, created_at, last_used_at")
            .eq("user_id", user_id)
            .eq("tenant_id", tenant_id if tenant_id is not None else TenantContext.get())
            .execute()
        )
        active = [r for r in (result.data or []) if r.get("status") == "active"]
        expired = [
            r
            for r in active
            if (r.get("last_used_at") or r.get("created_at", "")) < cutoff.isoformat()
        ]
        return {
            "total_active": len(active),
            "eligible_for_cleanup": len(expired),
        }


if __name__ == "__main__":
    # Quick self-check
    class _Result:
        def __init__(self, data):
            self.data = data

    class _StubTable:
        def select(self, *_a):
            return self

        def eq(self, *_a):
            return self

        def limit(self, *_a):
            return self

        def execute(self):
            return _Result([])

    class _StubClient:
        def table(self, *_a):
            return _StubTable()

    mgr = MemoryPrivacyManager(_StubClient())
    assert mgr.check_consent("u1", ConsentScope.EXTRACTION) is False
    assert mgr.check_consent("u1", ConsentScope.RETRIEVAL) is True
    print("privacy.py self-check passed")
