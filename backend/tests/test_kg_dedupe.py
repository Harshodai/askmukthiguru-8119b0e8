"""Personal knowledge-graph duplicate collapse (2026-11-28)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.memory_service_v2 import MemoryServiceV2, _dedupe_kg, _norm_kg_label
from services.tenant_context import TenantContext


async def _build(mems, neo4j_mems=None, limit=50):
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    svc = MemoryServiceV2(sb, MagicMock())
    svc.list_memories = AsyncMock(return_value={"memories": mems})
    driver = None
    if neo4j_mems is not None:
        driver = MagicMock()
        session = driver.session.return_value.__enter__.return_value
        rows = [MagicMock(data=MagicMock(return_value=m)) for m in neo4j_mems]
        session.run.return_value = rows
    svc._get_neo4j = MagicMock(return_value=driver)
    MemoryServiceV2._KG_CACHE.clear()
    with TenantContext.scope("t", user_id="u"):
        return await svc.build_personal_knowledge_graph("u", limit=limit)


def _assert_consistent(g, limit=50):
    ids = {n["id"] for n in g["nodes"]}
    assert len(ids) == len(g["nodes"]) <= limit
    for e in g["edges"]:
        assert e["source"] in ids and e["target"] in ids and e["source"] != e["target"]
    keys = [(n["type"], _norm_kg_label(n["label"])) for n in g["nodes"] if n["type"] != "User"]
    assert len(keys) == len(set(keys))


@pytest.mark.asyncio
async def test_identical_memories_collapse_to_one_node():
    mems = [{"id": f"m{i}", "content": "x", "claim": "Breathe slowly"} for i in range(5)]
    g = await _build(mems)
    mem = [n for n in g["nodes"] if n["type"] == "Memory"]
    assert len(mem) == 1 and mem[0]["merged_count"] == 5
    assert len(mem[0]["merged_ids"]) == 5
    _assert_consistent(g)


@pytest.mark.asyncio
async def test_same_memory_across_neo4j_and_supabase_and_state_case():
    neo = [
        {
            "id": "n1",
            "content": "c",
            "insight": "Be still.",
            "state_category": "Calm",
            "created_at": "2026-01-01",
        }
    ]
    sup = [
        {
            "id": "s1",
            "content": "c",
            "claim": "be  still",
            "state_category": "calm",
            "created_at": "2026-02-01",
        }
    ]
    g = await _build(sup, neo4j_mems=neo)
    assert len([n for n in g["nodes"] if n["type"] == "Memory"]) == 1
    states = [n for n in g["nodes"] if n["type"] == "State"]
    assert len(states) == 1
    mem = next(n for n in g["nodes"] if n["type"] == "Memory")
    assert mem["created_at"] == "2026-02-01"
    _assert_consistent(g)


def test_dedupe_redirects_edges_and_orders_by_created_at():
    nodes = {
        "user:u": {"id": "user:u", "label": "You", "type": "User"},
        "memory:a": {"id": "memory:a", "label": "Calm", "type": "Memory", "created_at": "1"},
        "memory:b": {"id": "memory:b", "label": "calm!", "type": "Memory", "created_at": "2"},
        "state:x": {"id": "state:x", "label": "Joy", "type": "State"},
    }
    edges = [
        {"source": "user:u", "target": "memory:a", "label": "HAS_MEMORY"},
        {"source": "user:u", "target": "memory:b", "label": "HAS_MEMORY"},
        {"source": "memory:a", "target": "memory:b", "label": "RELATED_TO"},
        {"source": "memory:b", "target": "state:x", "label": "IN_STATE"},
    ]
    n, e = _dedupe_kg(nodes, edges)
    assert set(n) == {"user:u", "memory:a", "state:x"}
    assert n["memory:a"]["created_at"] == "2"
    assert len(e) == 2 and all(x["source"] != x["target"] for x in e)


@pytest.mark.asyncio
async def test_limit_caps_nodes():
    mems = [{"id": f"m{i}", "content": "x", "claim": f"thought {i}"} for i in range(40)]
    g = await _build(mems, limit=10)
    _assert_consistent(g, limit=10)
