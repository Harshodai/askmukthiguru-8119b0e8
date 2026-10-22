"""DELETE /api/memory/all must erase every store that holds what we know about a seeker.

Regression for the 2026-09-23 finding: the endpoint wiped the legacy memory
tables but left canonical_memories, the audit tables that snapshot memory
statements, user_profiles, conversation_memories, and the canonical Qdrant index.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_container
from app.main import app, get_current_user_from_supabase
from services.memory_service_v2 import MemoryServiceV2

USER_ID = "00000000-0000-0000-0000-00000000abcd"

MUST_ERASE = {
    "canonical_memories",
    "canonical_memory_events",
    "memory_audit_events",
    "canonical_memory_compaction_snapshots",
    "conversation_memories",
    "user_profiles",
    "study_notebooks",
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

            def select(self, *_args, **_kwargs):
                return self

            def eq(self, column, value):
                if column == "user_id":
                    outer.deleted.append((name, value))
                return self

            def in_(self, column, values):
                assert column == "notebook_id"
                for value in values:
                    outer.deleted.append((name, str(value)))
                return self

            def execute(self):
                return SimpleNamespace(data=[{"id": 1}])

        return _Q()


class _ExactCache:
    def invalidate_user(self, user_id: str, *, all_tenants: bool = False) -> int:
        assert user_id == USER_ID
        assert all_tenants is True
        return 5


class _CanonicalIndex:
    def __init__(self) -> None:
        self.users: list[str] = []
        self.all_tenants_flags: list[bool] = []

    async def delete_all_user(
        self, user_id: str, *, tenant_id: str | None = None, all_tenants: bool = False
    ) -> int:
        self.users.append(user_id)
        self.all_tenants_flags.append(all_tenants)
        return 3


def test_delete_all_erases_canonical_memory_and_profiles():
    """A completed receipt requires every configured memory store to confirm."""
    supabase, index = _Supabase(), _CanonicalIndex()
    MemoryServiceV2._KG_CACHE.clear()
    MemoryServiceV2._KG_CACHE[("tenant-a", USER_ID, "personal", 50, "digest")] = (
        {"nodes": [{"id": f"memory:{USER_ID}", "content": "private memory"}]},
        9999999999.0,
    )

    outbox = AsyncMock()
    outbox.delete_user_rows.return_value = 4
    outbox.write_deletion_receipt.return_value = {"id": "delete-receipt-1"}

    qdrant = MagicMock()
    qdrant.get_collections.return_value = SimpleNamespace(
        collections=[SimpleNamespace(name="global_memory")]
    )
    qdrant.count.return_value = SimpleNamespace(count=7)

    graph_driver = MagicMock()
    graph_driver.session.return_value.__enter__.return_value.run.return_value.single.return_value = {
        "deleted": 2
    }

    memory_service = SimpleNamespace(
        clear_ephemeral=AsyncMock(return_value=True),
        _get_qdrant_v2=lambda: qdrant,
        _get_memory_collection=lambda: "global_memory",
        _get_neo4j=lambda: graph_driver,
    )
    second_brain = SimpleNamespace(
        crypto_shred=AsyncMock(return_value={"shredded": True})
    )
    container = SimpleNamespace(
        supabase_client=supabase,
        exact_cache=_ExactCache(),
        memory_outbox=outbox,
        memory_service=memory_service,
        second_brain=second_brain,
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
    assert ("study_notebook_items", "1") in supabase.deleted
    assert body["deleted"]["study_notebook_items"] == 1
    assert body["deleted"]["study_notebooks"] == 1
    assert index.users == [USER_ID]
    assert index.all_tenants_flags == [True]
    assert body["deleted"]["qdrant_canonical_memory"] == 3
    assert body["deleted"]["qdrant_global_memory"] == 7
    assert body["deleted"]["personal_knowledge_graph_cache"] == 1
    assert not any(
        key[1] == USER_ID and key[2] == "personal"
        for key in MemoryServiceV2._KG_CACHE
    )
    assert body["deleted"]["neo4j_global_memory"] == 2
    graph_query = graph_driver.session.return_value.__enter__.return_value.run.call_args.args[0]
    assert "OPTIONAL MATCH (owned:GlobalMemory {user_id: $user_id})" in graph_query
    assert body["deleted"]["memory_outbox"] == 4
    assert body["deleted"]["exact_answer_cache"] == 5
    assert body["status"] == "completed" and body["failures"] == []
    qdrant.delete.assert_called_once()
    assert qdrant.delete.call_args.kwargs["wait"] is True
    second_brain.crypto_shred.assert_awaited_once_with(USER_ID)


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
