"""DELETE /api/memory/all must erase every store that holds what we know about a seeker.

Regression for the 2026-09-23 finding: the endpoint wiped the legacy memory
tables but left canonical_memories, the audit tables that snapshot memory
statements, user_profiles, conversation_memories, and the canonical Qdrant index.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_container
from app.main import app, get_current_user_from_supabase

USER_ID = "00000000-0000-0000-0000-00000000abcd"

MUST_ERASE = {
    "canonical_memories",
    "canonical_memory_events",
    "memory_audit_events",
    "conversation_memories",
    "user_profiles",
}


class _Supabase:
    """Records which tables were deleted for which user."""

    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def table(self, name: str):
        outer = self

        class _Q:
            def delete(self):
                return self

            def eq(self, column, value):
                assert column == "user_id"
                outer.deleted.append((name, value))
                return self

            def execute(self):
                return SimpleNamespace(data=[{"id": 1}])

        return _Q()


class _CanonicalIndex:
    def __init__(self) -> None:
        self.users: list[str] = []

    async def delete_all_user(self, user_id: str) -> int:
        self.users.append(user_id)
        return 3


def test_delete_all_erases_canonical_memory_and_profiles():
    supabase, index = _Supabase(), _CanonicalIndex()
    container = SimpleNamespace(
        supabase_client=supabase,
        canonical_memory_integration=SimpleNamespace(
            memory_retriever=SimpleNamespace(_vector_index=index)
        ),
    )
    app.dependency_overrides[get_current_user_from_supabase] = lambda: {"id": USER_ID}
    app.dependency_overrides[get_container] = lambda: container
    try:
        resp = TestClient(app).delete("/api/memory/all")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    erased = {table for table, uid in supabase.deleted if uid == USER_ID}
    assert MUST_ERASE <= erased, f"not erased: {MUST_ERASE - erased}"
    assert index.users == [USER_ID]
    assert body["deleted"]["qdrant_canonical_memory"] == 3
    assert body["status"] == "completed" and body["failures"] == []


def test_delete_all_reports_partial_failure_when_a_store_fails():
    supabase = MagicMock()
    supabase.table.side_effect = RuntimeError("db down")
    container = SimpleNamespace(supabase_client=supabase)
    app.dependency_overrides[get_current_user_from_supabase] = lambda: {"id": USER_ID}
    app.dependency_overrides[get_container] = lambda: container
    try:
        resp = TestClient(app).delete("/api/memory/all")
    finally:
        app.dependency_overrides.clear()

    body = resp.json()
    assert body["status"] == "partial_failure"
    assert any(f.startswith("canonical_memories") for f in body["failures"])
