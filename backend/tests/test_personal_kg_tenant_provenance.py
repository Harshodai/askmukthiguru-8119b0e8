"""Tenant and provenance regressions for the personal Knowledge Graph.

These tests use in-memory fakes only. They do not connect to or mutate Neo4j,
Qdrant, Supabase, or any other persistent service.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.memory_service_v2 import MemoryServiceV2
from services.tenant_context import TenantContext


class _Record(dict):
    def data(self):
        return dict(self)


class _FakeSession:
    def __init__(self, driver):
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self.driver.queries.append((query, dict(params)))
        if "MATCH (u:User" in query and self.driver.include_neo4j_memory:
            tenant = params["tenant_id"]
            return [
                _Record(
                    id=f"{tenant}-memory",
                    content=f"private content for {tenant}",
                    insight=f"remembered {tenant}",
                    state_category=None,
                    created_at="2026-10-01T00:00:00Z",
                )
            ]
        if "RETURN DISTINCT c.entity_id AS eid LIMIT 500" in query:
            return [_Record(eid="Stillness")] if self.driver.include_stillness else []
        return []


class _FakeDriver:
    def __init__(self, *, include_neo4j_memory=True, include_stillness=False):
        self.include_neo4j_memory = include_neo4j_memory
        self.include_stillness = include_stillness
        self.queries: list[tuple[str, dict]] = []

    def session(self):
        return _FakeSession(self)


class _FakeQuery:
    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class _FakeSupabase:
    def table(self, _name):
        return _FakeQuery()


def _service(monkeypatch, driver):
    service = MemoryServiceV2(_FakeSupabase())
    service._get_neo4j = lambda: driver
    service.list_memories = AsyncMock(return_value={"memories": []})
    monkeypatch.setattr(
        "services.memory_service_v2.kg_analytics.enrich_graph",
        lambda graph, enabled: graph,
    )
    MemoryServiceV2._KG_CACHE.clear()
    return service


def _node_contents(graph):
    return [str(node.get("content") or "") for node in graph["nodes"]]


@pytest.mark.asyncio
async def test_personal_graph_cache_and_neo4j_traversals_are_tenant_scoped(monkeypatch):
    driver = _FakeDriver()
    service = _service(monkeypatch, driver)
    user_id = "same-user-id-in-two-tenant-fixtures"

    with TenantContext.scope("tenant-a", user_id=user_id):
        graph_a = await service.build_personal_knowledge_graph(user_id)
        assert any("private content for tenant-a" in value for value in _node_contents(graph_a))

        # Returned graphs are copies; consumer mutations must not poison cache.
        next(node for node in graph_a["nodes"] if node.get("content"))["content"] = "tampered"
        cached_a = await service.build_personal_knowledge_graph(user_id)
        assert any("private content for tenant-a" in value for value in _node_contents(cached_a))
        assert all(value != "tampered" for value in _node_contents(cached_a))

    with TenantContext.scope("tenant-b", user_id=user_id):
        graph_b = await service.build_personal_knowledge_graph(user_id)
        assert any("private content for tenant-b" in value for value in _node_contents(graph_b))
        assert not any("private content for tenant-a" in value for value in _node_contents(graph_b))

    private_queries = [
        (query, params)
        for query, params in driver.queries
        if "MATCH (u:User" in query
        or "MATCH (m:GlobalMemory {tenant_id:" in query
        or "MATCH (m1:GlobalMemory {tenant_id:" in query
    ]
    assert private_queries, "expected private Neo4j reads"
    assert all("tenant_id" in query for query, _ in private_queries)
    assert all(params.get("tenant_id") in {"tenant-a", "tenant-b"} for _, params in private_queries)


@pytest.mark.asyncio
async def test_kg_cache_uses_full_query_not_only_first_200_characters(monkeypatch):
    driver = _FakeDriver(include_neo4j_memory=False)
    service = _service(monkeypatch, driver)
    prefix = "x" * 220

    await service.build_personal_knowledge_graph(None, view="ontology", query=prefix + " alpha")
    await service.build_personal_knowledge_graph(None, view="ontology", query=prefix + " beta")

    ontology_cache_keys = [key for key in MemoryServiceV2._KG_CACHE if key[2] == "ontology"]
    assert len(ontology_cache_keys) == 2


@pytest.mark.asyncio
async def test_lexical_concept_match_is_labelled_as_a_mention_not_a_persisted_relation(monkeypatch):
    driver = _FakeDriver(include_neo4j_memory=False, include_stillness=True)
    service = _service(monkeypatch, driver)
    service.list_memories = AsyncMock(
        return_value={
            "memories": [
                {
                    "id": "memory-1",
                    "content": "I reflect on Stillness every morning",
                    "claim": "I reflect on Stillness",
                    "state_category": None,
                }
            ]
        }
    )

    with TenantContext.scope("tenant-a", user_id="user-1"):
        graph = await service.build_personal_knowledge_graph("user-1")

    inferred = [
        edge for edge in graph["edges"]
        if edge["source"] == "memory:memory-1" and edge["target"] == "concept:Stillness"
    ]
    assert len(inferred) == 1
    assert inferred[0]["label"] == "MENTIONS_CONCEPT"
