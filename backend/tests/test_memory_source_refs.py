"""Per-memory provenance ("source_ref") on the memory API and the personal graph.

In-memory fakes only: no Supabase, Neo4j or Qdrant is contacted.

Rules under test:
- a source exists only when the stored row proves one (valid id), else None;
- the API returns kind + id, never a URL;
- a database without the source column still lists memories (no link);
- reads stay scoped to the authenticated user and tenant.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import memory as memory_api
from app.api.kg import router as kg_router
from app.dependencies import get_container
from services.auth_service import get_current_user_from_supabase
from services.memory_service import _LIST_MEMORY_COLUMN_TIERS, MemoryService
from services.memory_service_v2 import MemoryServiceV2
from services.memory_source import (
    is_missing_column_error,
    memory_source_ref,
    notebook_source_ref,
)
from services.tenant_context import TenantContext

USER_ID = "a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6"
CONVERSATION_ID = "3f2b8c1e-9a4d-4e6f-8a1b-2c3d4e5f6a7b"


# ── Pure helper ──────────────────────────────────────────────────────────────


def test_source_ref_only_for_a_valid_conversation_id():
    assert memory_source_ref({"source_conversation_id": CONVERSATION_ID}) == {
        "kind": "conversation",
        "id": CONVERSATION_ID,
    }
    assert memory_source_ref({"source_conversation_id": f"  {CONVERSATION_ID}  "})["id"] == (
        CONVERSATION_ID
    )


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "   ",
        5,
        ["x"],
        "has space",
        "../etc/passwd",
        "a/b",
        "<script>",
        "x" * 201,
        "-lead",
    ],
)
def test_source_ref_is_none_for_missing_or_malformed_ids(bad):
    assert memory_source_ref({"source_conversation_id": bad}) is None


def test_source_ref_is_none_for_legacy_rows_without_the_column():
    assert memory_source_ref({"id": "m1", "content": "I meditate"}) is None


def test_notebook_source_ref():
    assert notebook_source_ref("item-1") == {"kind": "notebook", "id": "item-1"}
    assert notebook_source_ref(None) is None
    assert notebook_source_ref("bad id") is None


def test_missing_column_detection_does_not_swallow_other_errors():
    assert is_missing_column_error(Exception("column guru_memories.x does not exist (42703)"))
    assert is_missing_column_error(Exception("PGRST204 Could not find the 'x' column"))
    assert not is_missing_column_error(Exception("connection reset by peer"))


# ── list_memories: schema fallback ───────────────────────────────────────────


class _Query:
    def __init__(self, table, log, fail_with):
        self.table_name = table
        self.log = log
        self.fail_with = fail_with
        self.filters: dict[str, str] = {}
        self.columns = ""

    def select(self, columns, **kwargs):
        self.columns = columns
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def is_(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def range(self, *args, **kwargs):
        return self

    def execute(self):
        self.log.append((self.columns, dict(self.filters)))
        if self.columns == "id":
            return SimpleNamespace(data=[], count=2)
        if self.fail_with and "source_conversation_id" in self.columns:
            raise self.fail_with
        return SimpleNamespace(
            data=[{"id": "m1", "content": "I walk daily", "source": "extracted"}], count=None
        )


class _Supabase:
    def __init__(self, fail_with=None):
        self.log: list[tuple[str, dict]] = []
        self.fail_with = fail_with

    def table(self, name):
        return _Query(name, self.log, self.fail_with)


@pytest.mark.asyncio
async def test_list_memories_selects_the_source_column_first():
    supabase = _Supabase()
    service = MemoryService(supabase_client=supabase)
    with TenantContext.scope("tenant-a", user_id=USER_ID):
        result = await service.list_memories(USER_ID)

    page_selects = [cols for cols, _ in supabase.log if "content" in cols]
    assert page_selects == [_LIST_MEMORY_COLUMN_TIERS[0]]
    assert "source_conversation_id" in page_selects[0]
    assert result["total"] == 2


@pytest.mark.asyncio
async def test_list_memories_falls_back_when_the_source_column_is_not_migrated_yet():
    supabase = _Supabase(
        fail_with=Exception("column guru_memories.source_conversation_id does not exist 42703")
    )
    service = MemoryService(supabase_client=supabase)
    with TenantContext.scope("tenant-a", user_id=USER_ID):
        result = await service.list_memories(USER_ID)

    assert result["memories"] == [{"id": "m1", "content": "I walk daily", "source": "extracted"}]
    page_selects = [cols for cols, _ in supabase.log if "content" in cols]
    # Without the source column the only tiers that can work are the ones without it.
    assert page_selects == list(_LIST_MEMORY_COLUMN_TIERS[:3])
    assert memory_source_ref(result["memories"][0]) is None


@pytest.mark.asyncio
async def test_missing_metadata_column_still_returns_the_source_link():
    """Local Supabase: guru_memories has source_conversation_id but no metadata column."""

    class _NoMetadata(_Query):
        def execute(self):
            if "metadata" in self.columns.split(", "):
                self.log.append((self.columns, dict(self.filters)))
                raise Exception("column guru_memories.metadata does not exist 42703")
            if "source_conversation_id" in self.columns and "content" in self.columns:
                self.log.append((self.columns, dict(self.filters)))
                return SimpleNamespace(
                    data=[
                        {
                            "id": "m1",
                            "content": "I walk daily",
                            "source": "extracted",
                            "source_conversation_id": "11111111-1111-1111-1111-111111111111",
                        }
                    ],
                    count=None,
                )
            return super().execute()

    class _SupabaseNoMetadata(_Supabase):
        def table(self, name):
            return _NoMetadata(name, self.log, self.fail_with)

    supabase = _SupabaseNoMetadata()
    service = MemoryService(supabase_client=supabase)
    with TenantContext.scope("tenant-a", user_id=USER_ID):
        result = await service.list_memories(USER_ID)

    page_selects = [cols for cols, _ in supabase.log if "content" in cols]
    assert page_selects == list(_LIST_MEMORY_COLUMN_TIERS[:2])
    assert memory_source_ref(result["memories"][0]) is not None


@pytest.mark.asyncio
async def test_list_memories_does_not_retry_unrelated_errors():
    supabase = _Supabase(fail_with=Exception("connection reset by peer"))
    service = MemoryService(supabase_client=supabase)
    with TenantContext.scope("tenant-a", user_id=USER_ID):
        result = await service.list_memories(USER_ID)

    assert result == {"memories": [], "total": 0}
    assert len([cols for cols, _ in supabase.log if "content" in cols]) == 1


@pytest.mark.asyncio
async def test_list_memories_reads_are_scoped_to_user_and_tenant():
    supabase = _Supabase()
    service = MemoryService(supabase_client=supabase)
    with TenantContext.scope("tenant-a", user_id=USER_ID):
        await service.list_memories(USER_ID)

    assert supabase.log
    for _, filters in supabase.log:
        assert filters == {"user_id": USER_ID, "tenant_id": "tenant-a"}


# ── /api/memory/list ─────────────────────────────────────────────────────────


def _memory_client(rows):
    app = FastAPI()
    app.include_router(memory_api.router, prefix="/api")
    container = MagicMock()
    container.memory_service = MagicMock()
    container.memory_service.list_memories = AsyncMock(
        return_value={"memories": rows, "total": len(rows)}
    )
    app.dependency_overrides[get_current_user_from_supabase] = lambda: {"id": USER_ID}
    app.dependency_overrides[get_container] = lambda: container
    return TestClient(app), container


def test_memory_list_returns_source_ref_or_null_never_a_url():
    rows = [
        {
            "id": "m-linked",
            "content": "I practise breathing",
            "source": "extracted",
            "created_at": "2026-10-30T10:00:00+00:00",
            "source_conversation_id": CONVERSATION_ID,
        },
        {
            "id": "m-legacy",
            "content": "I live in Pune",
            "source": "extracted",
            "created_at": "2026-10-01T10:00:00+00:00",
        },
        {
            "id": "m-bad",
            "content": "I like tea",
            "source": "extracted",
            "created_at": "2026-10-02T10:00:00+00:00",
            "source_conversation_id": "../../admin",
        },
    ]
    client, container = _memory_client(rows)

    resp = client.get("/api/memory/list")
    assert resp.status_code == 200
    by_id = {m["id"]: m for m in resp.json()["memories"]}

    assert by_id["m-linked"]["source_ref"] == {"kind": "conversation", "id": CONVERSATION_ID}
    assert by_id["m-legacy"]["source_ref"] is None
    assert by_id["m-bad"]["source_ref"] is None
    assert "http" not in str(by_id["m-linked"]["source_ref"])
    # The listing is requested for the authenticated user only.
    assert container.memory_service.list_memories.await_args.args[0] == USER_ID


# ── Personal graph ───────────────────────────────────────────────────────────


class _GraphQuery:
    def __init__(self, table):
        self.table_name = table
        self.filters: dict[str, str] = {}

    def select(self, *args, **kwargs):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def in_(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def execute(self):
        if self.table_name == "study_notebooks":
            return SimpleNamespace(data=[{"id": "nb-1"}])
        if self.table_name == "study_notebook_items":
            return SimpleNamespace(
                data=[{"id": "item-1", "query": "What is stillness?", "answer": "A quiet mind."}]
            )
        return SimpleNamespace(data=[])


class _GraphSupabase:
    def table(self, name):
        return _GraphQuery(name)


@pytest.mark.asyncio
async def test_personal_graph_nodes_carry_source_ref_only_when_proven(monkeypatch):
    service = MemoryServiceV2(_GraphSupabase())
    service._get_neo4j = lambda: None
    service.list_memories = AsyncMock(
        return_value={
            "memories": [
                {
                    "id": "m-linked",
                    "content": "I practise breathing",
                    "claim": "breathing",
                    "source_conversation_id": CONVERSATION_ID,
                },
                {"id": "m-legacy", "content": "I live in Pune", "claim": "Pune"},
            ]
        }
    )
    monkeypatch.setattr(
        "services.memory_service_v2.kg_analytics.enrich_graph", lambda graph, enabled: graph
    )
    MemoryServiceV2._KG_CACHE.clear()

    with TenantContext.scope("tenant-a", user_id=USER_ID):
        graph = await service.build_personal_knowledge_graph(USER_ID)

    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes["memory:m-linked"]["source_ref"] == {"kind": "conversation", "id": CONVERSATION_ID}
    assert nodes["memory:m-legacy"]["source_ref"] is None
    assert nodes["notebook:item-1"]["source_ref"] == {"kind": "notebook", "id": "item-1"}
    assert nodes[f"user:{USER_ID}"]["source_ref"] is None


def test_kg_endpoint_passes_through_well_formed_source_ref_only():
    app = FastAPI()
    app.include_router(kg_router, prefix="/api")
    app.dependency_overrides[get_current_user_from_supabase] = lambda: {
        "id": "user-123",
        "email": "seeker@example.com",
    }
    fake_result = {
        "nodes": [
            {
                "id": "memory:m1",
                "label": "breathing",
                "type": "Memory",
                "source_ref": {"kind": "conversation", "id": CONVERSATION_ID},
            },
            {"id": "memory:m2", "label": "Pune", "type": "Memory", "source_ref": None},
            {"id": "memory:m3", "label": "odd", "type": "Memory", "source_ref": {"kind": "x"}},
            {"id": "concept:Stillness", "label": "Stillness", "type": "Concept"},
        ],
        "edges": [],
    }
    svc = MagicMock()
    svc.build_personal_knowledge_graph = AsyncMock(return_value=fake_result)

    with patch("app.api.kg.get_container") as mock_get:
        container = MagicMock()
        container.memory_service = svc
        mock_get.return_value = container
        resp = TestClient(app).get("/api/kg/personal-subgraph")

    assert resp.status_code == 200
    by_id = {n["id"]: n for n in resp.json()["nodes"]}
    assert by_id["memory:m1"]["source_ref"] == {"kind": "conversation", "id": CONVERSATION_ID}
    assert by_id["memory:m2"]["source_ref"] is None
    assert by_id["memory:m3"]["source_ref"] is None
    assert by_id["concept:Stillness"]["source_ref"] is None
