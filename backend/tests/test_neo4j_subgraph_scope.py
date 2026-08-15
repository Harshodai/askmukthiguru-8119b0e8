"""Regression coverage for corpus-scoped Neo4j traversal."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rag.nodes import retrieval
from services.tenant_context import TenantContext


class _Session:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        return [{"source": "meditation", "rel": "LEADS_TO", "desc": None, "target": "stillness"}]


class _Driver:
    def __init__(self) -> None:
        self.session_instance = _Session()

    def session(self):
        return self.session_instance


@pytest.mark.asyncio
async def test_targeted_subgraph_query_binds_corpus_scope(monkeypatch):
    # ContextVars leak across tests in the same pytest process when set without a
    # reset (see test_cache_tenant_isolation.py's TenantContext.set("default")) --
    # pin explicitly rather than relying on ambient state left by another test.
    TenantContext.set(retrieval.settings.default_tenant_id)
    driver = _Driver()
    monkeypatch.setattr(retrieval.settings, "neo4j_uri", "bolt://test", raising=False)
    monkeypatch.setattr("ingest.pipeline.extract_doctrine_tags", lambda _query: ["meditation"])
    monkeypatch.setattr("app.dependencies.get_container", lambda: SimpleNamespace(neo4j_driver=driver))

    context = await retrieval.query_neo4j_subgraph("How do I meditate?", corpus_id="teacher-a-corpus")

    assert "Targeted Subgraph Context" in context
    cypher, params = driver.session_instance.calls[0]
    assert "coalesce(r.tenant_id, \"oneness\") = $tenant_id" in cypher
    assert "coalesce(r.corpus_id, \"askmukthiguru\") = $corpus_id" in cypher
    assert params["corpus_id"] == "teacher-a-corpus"
    assert params["tenant_id"] == "oneness"
