"""Tests for canonical memory privacy and data governance (Phase 14)."""
import datetime as dt
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from services.canonical_memory.privacy import ConsentScope, MemoryPrivacyManager


# ── Helpers ──────────────────────────────────────────────────────────


class _FakeResult:
    """Mimics Supabase query result with a ``data`` attribute."""

    def __init__(self, data: Optional[List[Dict]] = None) -> None:
        self.data = data or []


class _FakeTable:
    """In-memory fake for a single Supabase table."""

    def __init__(self, store: Dict[str, List[Dict]], table_name: str) -> None:
        self._store = store
        self._table_name = table_name
        self._filters: Dict[str, Any] = {}

    # ── chaining ─────────────────────────────────────────────────────
    def select(self, *_a: str) -> "_FakeTable":
        return self

    def eq(self, key: str, value: Any) -> "_FakeTable":
        self._filters[key] = value
        return self

    def limit(self, _n: int) -> "_FakeTable":
        return self

    def execute(self) -> _FakeResult:
        rows = self._store.get(self._table_name, [])
        filtered = [
            r for r in rows if all(r.get(k) == v for k, v in self._filters.items())
        ]
        self._filters = {}
        return _FakeResult(filtered)

    def upsert(self, record: Dict) -> "_FakeTable":
        rows = self._store.setdefault(self._table_name, [])
        for i, r in enumerate(rows):
            if r.get("user_id") == record["user_id"] and r.get("scope") == record.get("scope"):
                rows[i] = record
                return self
        rows.append(record)
        return self

    def delete(self) -> "_FakeTable":
        return self


class _FakeDB:
    """In-memory fake for the Supabase client."""

    def __init__(self) -> None:
        self._stores: Dict[str, List[Dict]] = {}

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self._stores, name)


def _make_manager(db: Optional[_FakeDB] = None) -> tuple:
    db = db or _FakeDB()
    return MemoryPrivacyManager(db), db


# ── Consent tests ────────────────────────────────────────────────────


class TestConsentCheckNoRecord:
    """No consent receipt → EXTRACTION denied, all others allowed."""

    def test_extraction_denied_without_record(self):
        mgr, _ = _make_manager()
        assert mgr.check_consent("user-a", ConsentScope.EXTRACTION) is False

    def test_retrieval_allowed_without_record(self):
        mgr, _ = _make_manager()
        assert mgr.check_consent("user-a", ConsentScope.RETRIEVAL) is True

    def test_sharing_allowed_without_record(self):
        mgr, _ = _make_manager()
        assert mgr.check_consent("user-a", ConsentScope.SHARING) is True

    def test_analytics_allowed_without_record(self):
        mgr, _ = _make_manager()
        assert mgr.check_consent("user-a", ConsentScope.ANALYTICS) is True


class TestConsentCheckGranted:
    """Record with granted=True returns True."""

    def test_granted_returns_true(self):
        mgr, db = _make_manager()
        db._stores["memory_consent_receipts"] = [
            {"user_id": "u1", "scope": "extraction", "granted": True}
        ]
        assert mgr.check_consent("u1", ConsentScope.EXTRACTION) is True


class TestConsentCheckDenied:
    """Record with granted=False returns False."""

    def test_denied_returns_false(self):
        mgr, db = _make_manager()
        db._stores["memory_consent_receipts"] = [
            {"user_id": "u1", "scope": "retrieval", "granted": False}
        ]
        assert mgr.check_consent("u1", ConsentScope.RETRIEVAL) is False


class TestRecordConsent:
    """record_consent persists and upserts."""

    def test_record_persisted(self):
        mgr, db = _make_manager()
        mgr.record_consent("u1", ConsentScope.EXTRACTION, True)
        rows = db._stores.get("memory_consent_receipts", [])
        assert len(rows) == 1
        assert rows[0]["user_id"] == "u1"
        assert rows[0]["scope"] == "extraction"
        assert rows[0]["granted"] is True
        assert "updated_at" in rows[0]

    def test_upsert_replaces_existing(self):
        mgr, db = _make_manager()
        mgr.record_consent("u1", ConsentScope.EXTRACTION, True)
        mgr.record_consent("u1", ConsentScope.EXTRACTION, False)
        rows = db._stores["memory_consent_receipts"]
        assert len(rows) == 1
        assert rows[0]["granted"] is False


class TestExportData:
    """export_user_data returns memories and consent history."""

    def test_export_includes_memories_and_consent(self):
        mgr, db = _make_manager()
        db._stores["canonical_memories"] = [
            {"id": "m1", "user_id": "u1", "statement": "prefers tea"}
        ]
        db._stores["memory_consent_receipts"] = [
            {"user_id": "u1", "scope": "extraction", "granted": True}
        ]
        export = mgr.export_user_data("u1")
        assert len(export["canonical_memories"]) == 1
        assert export["canonical_memories"][0]["statement"] == "prefers tea"
        assert len(export["consent_history"]) == 1
        assert "exported_at" in export

    def test_export_empty_for_unknown_user(self):
        mgr, _ = _make_manager()
        export = mgr.export_user_data("nonexistent")
        assert export["canonical_memories"] == []
        assert export["consent_history"] == []


class TestPurgeData:
    """purge_user_data removes all user rows."""

    def test_purge_clears_canonical_and_consent(self):
        mgr, db = _make_manager()
        db._stores["canonical_memories"] = [
            {"user_id": "u1", "id": "m1"},
            {"user_id": "u2", "id": "m2"},
        ]
        db._stores["memory_consent_receipts"] = [
            {"user_id": "u1", "scope": "extraction"},
            {"user_id": "u2", "scope": "retrieval"},
        ]
        result = mgr.purge_user_data("u1")
        assert result["canonical_memories"] == 1
        assert result["consent_receipts"] == 1
        assert "purged_at" in result
        # u2 data still present
        remaining_mems = [r for r in db._stores["canonical_memories"] if r["user_id"] == "u2"]
        assert len(remaining_mems) == 1

    def test_purge_no_data_returns_zeros(self):
        mgr, _ = _make_manager()
        result = mgr.purge_user_data("ghost")
        assert result["canonical_memories"] == 0
        assert result["consent_receipts"] == 0


class TestRetentionStatus:
    """get_retention_status identifies expired memories."""

    def test_retention_finds_expired(self):
        mgr, db = _make_manager()
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=400)).isoformat()
        fresh = dt.datetime.now(dt.timezone.utc).isoformat()
        db._stores["canonical_memories"] = [
            {"id": "m1", "user_id": "u1", "created_at": old, "last_used_at": old},
            {"id": "m2", "user_id": "u1", "created_at": fresh, "last_used_at": fresh},
            {"id": "m3", "user_id": "u1", "created_at": old, "last_used_at": fresh},
            {"id": "m4", "user_id": "u1", "created_at": fresh, "last_used_at": None},
        ]
        status = mgr.get_retention_status("u1", max_age_days=365)
        assert status["total_active"] == 4
        assert status["eligible_for_cleanup"] == 1  # only m1

    def test_retention_excludes_deleted(self):
        mgr, db = _make_manager()
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=500)).isoformat()
        db._stores["canonical_memories"] = [
            {"id": "m1", "user_id": "u1", "created_at": old, "last_used_at": old, "deleted_at": old},
        ]
        status = mgr.get_retention_status("u1")
        assert status["total_active"] == 0
        assert status["eligible_for_cleanup"] == 0


class TestUnknownScopeDefaults:
    """Unknown scope behaves like non-extraCTION (allowed)."""

    def test_unknown_scope_defaults_allowed(self):
        mgr, _ = _make_manager()
        # ConsentScope doesn't have a "nonexistent" member, but the check
        # should still work via the fallback path if someone passes a raw
        # string — except the type hint prevents that. Verify the enum
        # members we have all work.
        for scope in ConsentScope:
            result = mgr.check_consent("u1", scope)
            if scope == ConsentScope.EXTRACTION:
                assert result is False
            else:
                assert result is True
