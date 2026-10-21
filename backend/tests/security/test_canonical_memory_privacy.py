"""Regression tests for tenant-scoped, append-only canonical-memory consent."""

import datetime as dt
from typing import Any

from services.canonical_memory.privacy import ConsentScope, MemoryPrivacyManager
from services.tenant_context import TenantContext


class _Result:
    def __init__(self, data=None):
        self.data = data or []


class _Query:
    def __init__(self, store, table_name):
        self.store = store
        self.table_name = table_name
        self.filters: dict[str, Any] = {}
        self.operation = "select"
        self.payload = None
        self.ordering: list[tuple[str, bool]] = []
        self.row_limit: int | None = None

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def order(self, key, desc=False):
        self.ordering.append((key, desc))
        return self

    def limit(self, size):
        self.row_limit = size
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = dict(payload)
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def execute(self):
        rows = self.store.setdefault(self.table_name, [])
        if self.operation == "insert":
            item = dict(self.payload or {})
            item.setdefault("id", f"receipt-{len(rows) + 1}")
            item.setdefault("event_sequence", max([r.get("event_sequence", 0) for r in rows] + [0]) + 1)
            item.setdefault("created_at", dt.datetime.now(dt.UTC).isoformat())
            rows.append(item)
            return _Result([item])
        matches = [row for row in rows if all(row.get(k) == v for k, v in self.filters.items())]
        if self.operation == "delete":
            matching_ids = {id(row) for row in matches}
            self.store[self.table_name] = [row for row in rows if id(row) not in matching_ids]
            return _Result(matches)
        for key, descending in reversed(self.ordering):
            matches.sort(key=lambda row: row.get(key, 0), reverse=descending)
        if self.row_limit is not None:
            matches = matches[: self.row_limit]
        return _Result(matches)


class _FakeDB:
    def __init__(self):
        self._stores: dict[str, list[dict]] = {}

    def table(self, name):
        return _Query(self._stores, name)


def _manager(db=None):
    db = db or _FakeDB()
    return MemoryPrivacyManager(db), db


def _receipt(user="user-a", tenant="oneness", granted=True, sequence=1, version="memory-v1"):
    now = dt.datetime.now(dt.UTC).isoformat()
    return {
        "id": f"receipt-{sequence}",
        "user_id": user,
        "tenant_id": tenant,
        "consent_version": version,
        "granted": granted,
        "revoked_at": None if granted else now,
        "created_at": now,
        "event_sequence": sequence,
    }


class TestConsent:
    def test_no_receipt_denies_every_memory_scope(self):
        manager, _ = _manager()
        for scope in ConsentScope:
            assert manager.check_consent("user-a", scope, tenant_id="oneness") is False

    def test_latest_active_grant_allows_memory(self):
        manager, db = _manager()
        db._stores["memory_consent_receipts"] = [_receipt()]
        for scope in ConsentScope:
            assert manager.check_consent("user-a", scope, tenant_id="oneness") is True

    def test_latest_revocation_does_not_resurrect_older_grant(self):
        manager, db = _manager()
        db._stores["memory_consent_receipts"] = [
            _receipt(granted=True, sequence=1),
            _receipt(granted=False, sequence=2),
        ]
        assert manager.check_consent("user-a", ConsentScope.RETRIEVAL, tenant_id="oneness") is False

    def test_consent_is_isolated_by_tenant_and_policy_version(self):
        manager, db = _manager()
        db._stores["memory_consent_receipts"] = [
            _receipt(tenant="tenant-a", granted=True, sequence=1),
            _receipt(tenant="tenant-b", granted=False, sequence=2),
            _receipt(tenant="tenant-a", granted=True, sequence=3, version="future-policy"),
        ]
        assert manager.check_consent("user-a", ConsentScope.EXTRACTION, tenant_id="tenant-a") is True
        assert manager.check_consent("user-a", ConsentScope.EXTRACTION, tenant_id="tenant-b") is False


class TestRecordConsent:
    def test_grant_then_revoke_preserves_both_events(self):
        manager, db = _manager()
        with TenantContext.scope("tenant-a"):
            manager.record_consent("user-a", ConsentScope.EXTRACTION, True)
            manager.record_consent("user-a", ConsentScope.EXTRACTION, False)
            assert manager.check_consent("user-a", ConsentScope.EXTRACTION) is False
        rows = db._stores["memory_consent_receipts"]
        assert len(rows) == 2
        assert [row["event_sequence"] for row in rows] == [1, 2]
        assert rows[0]["granted"] is True
        assert rows[1]["granted"] is False
        assert all(row["tenant_id"] == "tenant-a" for row in rows)


class TestExportAndPurge:
    def test_export_is_tenant_scoped_and_contains_consent_history(self):
        manager, db = _manager()
        db._stores["canonical_memories"] = [
            {"id": "a1", "user_id": "user-a", "tenant_id": "tenant-a", "statement": "tea"},
            {"id": "b1", "user_id": "user-a", "tenant_id": "tenant-b", "statement": "coffee"},
        ]
        db._stores["memory_consent_receipts"] = [
            _receipt(tenant="tenant-a"),
            _receipt(tenant="tenant-b", granted=False, sequence=2),
        ]
        exported = manager.export_user_data("user-a", tenant_id="tenant-a")
        assert [row["id"] for row in exported["canonical_memories"]] == ["a1"]
        assert len(exported["consent_history"]) == 1
        assert exported["consent_history"][0]["tenant_id"] == "tenant-a"
        assert "exported_at" in exported

    def test_purge_reports_actual_deleted_rows_only_for_target_tenant(self):
        manager, db = _manager()
        db._stores["canonical_memories"] = [
            {"id": "a1", "user_id": "user-a", "tenant_id": "tenant-a"},
            {"id": "b1", "user_id": "user-a", "tenant_id": "tenant-b"},
        ]
        db._stores["memory_consent_receipts"] = [
            _receipt(tenant="tenant-a"),
            _receipt(tenant="tenant-b", sequence=2),
        ]
        removed = manager.purge_user_data("user-a", tenant_id="tenant-a")
        assert removed["canonical_memories"] == 1
        assert removed["consent_receipts"] == 1
        assert [row["tenant_id"] for row in db._stores["canonical_memories"]] == ["tenant-b"]
        assert [row["tenant_id"] for row in db._stores["memory_consent_receipts"]] == ["tenant-b"]


class TestRetention:
    def test_retention_counts_active_rows_and_excludes_deleted(self):
        manager, db = _manager()
        old = (dt.datetime.now(dt.UTC) - dt.timedelta(days=400)).isoformat()
        fresh = dt.datetime.now(dt.UTC).isoformat()
        db._stores["canonical_memories"] = [
            {"id": "old", "user_id": "user-a", "tenant_id": "oneness", "status": "active", "created_at": old, "last_used_at": old},
            {"id": "fresh", "user_id": "user-a", "tenant_id": "oneness", "status": "active", "created_at": fresh, "last_used_at": fresh},
            {"id": "deleted", "user_id": "user-a", "tenant_id": "oneness", "status": "deleted", "created_at": old, "last_used_at": old},
        ]
        status = manager.get_retention_status("user-a", max_age_days=365)
        assert status == {"total_active": 2, "eligible_for_cleanup": 1}
