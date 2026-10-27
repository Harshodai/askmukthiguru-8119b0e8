"""Plan T3: graph-guided concept expansion — fail-open contract + normalisation.

No Neo4j, no container, no network: the driver and the underlying expansion
coroutine are both faked.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from services.first_person_graph_expansion import expand_query_concepts

QUERY = "how do I deal with anger"


def _container_with(driver):
    return SimpleNamespace(neo4j_driver=driver)


def _fake_driver():
    return object()


def test_returns_empty_when_container_has_no_driver(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.get_container", lambda: _container_with(None)
    )
    assert expand_query_concepts(QUERY) == []


def test_returns_empty_when_container_construction_raises(monkeypatch):
    def _boom():
        raise RuntimeError("container not ready")

    monkeypatch.setattr("app.dependencies.get_container", _boom)
    assert expand_query_concepts(QUERY) == []


def test_returns_empty_when_expansion_raises(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.get_container", lambda: _container_with(_fake_driver())
    )

    async def _boom(query, driver, **kwargs):
        raise RuntimeError("cypher exploded")

    monkeypatch.setattr("rag.kg_expansion.expand_query_via_kg", _boom)
    assert expand_query_concepts(QUERY) == []


def test_returns_empty_on_timeout_without_blocking_the_caller(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.get_container", lambda: _container_with(_fake_driver())
    )

    async def _slow(query, driver, **kwargs):
        await asyncio.sleep(5.0)
        return ["Karma"]

    monkeypatch.setattr("rag.kg_expansion.expand_query_via_kg", _slow)
    started = time.monotonic()
    assert expand_query_concepts(QUERY, timeout_s=0.05) == []
    assert time.monotonic() - started < 2.0


def test_empty_and_whitespace_query_never_touch_the_graph(monkeypatch):
    def _explode():
        raise AssertionError("container must not be consulted for an empty query")

    monkeypatch.setattr("app.dependencies.get_container", _explode)
    assert expand_query_concepts("") == []
    assert expand_query_concepts("   ") == []
    assert expand_query_concepts("\n\t ") == []


def test_normalises_output(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.get_container", lambda: _container_with(_fake_driver())
    )

    async def _neighbors(query, driver, **kwargs):
        return [" Anger ", "Karma", "karma", "   ", "Dharma", "Grace", 7, None]

    monkeypatch.setattr("rag.kg_expansion.expand_query_via_kg", _neighbors)

    # " Anger " is the query itself (case-insensitive) -> dropped.
    assert expand_query_concepts("anger", max_neighbors=2) == ["Karma", "Dharma"]
    assert expand_query_concepts("anger") == ["Karma", "Dharma", "Grace"]
    # The query is only dropped on an exact match, not on a token match.
    assert expand_query_concepts(QUERY)[0] == "Anger"


def test_passes_max_hops_and_entity_bound_to_the_expansion(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.get_container", lambda: _container_with(_fake_driver())
    )
    seen: dict[str, object] = {}

    async def _capture(query, driver, **kwargs):
        seen["query"] = query
        seen.update(kwargs)
        return ["Karma"]

    monkeypatch.setattr("rag.kg_expansion.expand_query_via_kg", _capture)
    assert expand_query_concepts(f"  {QUERY}  ", max_neighbors=3, timeout_s=0.4) == [
        "Karma"
    ]
    assert seen["query"] == QUERY
    assert seen["max_hops"] == 1
    assert seen["max_entities"] == 3
    assert seen["timeout"] == 0.4


def test_zero_max_neighbors_short_circuits(monkeypatch):
    def _explode():
        raise AssertionError("container must not be consulted when max_neighbors <= 0")

    monkeypatch.setattr("app.dependencies.get_container", _explode)
    assert expand_query_concepts(QUERY, max_neighbors=0) == []
