"""Tenant predicate on BOTH GraphRAG hops — ticket A22 / outside audit MULTI-001.

Regression guard for ``rag/nodes/atomic_graphrag.py``. Both openCypher constants
(``ATOMIC_GRAPHRAG_CYPHER`` and ``ATOMIC_VECTOR_GRAPHRAG_CYPHER``) traverse two
hops: ``seed -[r1]- n1`` (hop 1) and ``n1 -[r2]- n2`` (hop 2). Before commit
``28f2f552`` neither hop carried a tenant predicate, so on a multi-tenant graph
another tenant's nodes/edges could leak into the LLM context. The fix filters
``r1``/``n1`` and ``r2``/``n2`` in BOTH queries with the pattern already used
elsewhere in the codebase (``rag/nodes/retrieval.py:414`` renders
``coalesce(r.tenant_id, "<default>") = $tenant_id``).

What this file proves (no live graph needed):
  * every scoped alias — the seed *and* both hops — in every query carries the
    predicate, and the guard is *capable of failing* when any single predicate is
    removed (meta-test);
  * the query-construction path forwards the *active* tenant (not the default)
    as ``$tenant_id`` for both the seed branch and the vector branch, and two
    distinct tenant identities produce two distinct ``$tenant_id`` values.

What this file does NOT prove: that a live Memgraph/Neo4j actually returns only
same-tenant rows. That requires committing two tenants' nodes/edges to a real
graph, which this repo's constraints forbid a test from doing (no Qdrant/Neo4j
writes, shared tree). It is therefore left as a marked gap, not faked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import settings
from rag.nodes.atomic_graphrag import (
    ATOMIC_GRAPHRAG_CYPHER,
    ATOMIC_VECTOR_GRAPHRAG_CYPHER,
    execute_atomic_graphrag,
)
from services.tenant_context import TenantContext

# Hop 1 = (r1, n1); hop 2 = (r2, n2). All four must be tenant-scoped.
# `seed` is the fifth (2026-10-19, MULTI-001 follow-up): scoping only the hops
# still let a name collision resolve the seed to another tenant's node, and the
# RETURN payload hands back that node's own name/description.
_SCOPED_ALIASES = ("seed", "r1", "n1", "r2", "n2")
_QUERIES = {
    "seed": ATOMIC_GRAPHRAG_CYPHER,
    "vector": ATOMIC_VECTOR_GRAPHRAG_CYPHER,
}


def _predicate(alias: str) -> str:
    return f"coalesce({alias}.tenant_id, $default_tenant_id) = $tenant_id"


def _unscoped_aliases(cypher: str) -> list[str]:
    """Scoped aliases in ``cypher`` that are missing the tenant predicate."""
    return [alias for alias in _SCOPED_ALIASES if _predicate(alias) not in cypher]


@pytest.mark.parametrize("query_name", sorted(_QUERIES))
def test_every_scoped_alias_is_tenant_scoped(query_name: str) -> None:
    missing = _unscoped_aliases(_QUERIES[query_name])
    assert missing == [], (
        f"{query_name} query: alias(es) missing the tenant predicate: {missing}. "
        "The seed and both hops must scope by tenant "
        "(outside audit MULTI-001 / ticket A22)."
    )


@pytest.mark.parametrize("query_name", sorted(_QUERIES))
@pytest.mark.parametrize("alias", _SCOPED_ALIASES)
def test_guard_detects_each_removed_predicate(query_name: str, alias: str) -> None:
    """A guard that cannot fail is worthless.

    Remove exactly one predicate from an in-memory copy and confirm the guard
    reports that alias (and only that one) as unscoped. This keeps the guard
    above honest: if someone deletes a predicate line, the string no longer
    matches and the test that reads the real constants fails.
    """
    mutated = _QUERIES[query_name].replace(_predicate(alias), "__REMOVED__")
    assert _predicate(alias) not in mutated, "mutation did not apply"
    assert _unscoped_aliases(mutated) == [alias]


def _capture_driver() -> tuple[MagicMock, MagicMock]:
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    session.run.return_value = []
    return driver, session


@pytest.mark.parametrize("tenant_id", ["tenant_alpha", "tenant_beta"])
def test_seed_branch_forwards_active_tenant(tenant_id: str) -> None:
    driver, session = _capture_driver()
    with TenantContext.scope(tenant_id):
        execute_atomic_graphrag(driver, ["Karma"])
    kwargs = session.run.call_args.kwargs
    assert kwargs["tenant_id"] == tenant_id
    assert kwargs["default_tenant_id"] == settings.default_tenant_id


@pytest.mark.parametrize("tenant_id", ["tenant_alpha", "tenant_beta"])
def test_vector_branch_forwards_active_tenant(tenant_id: str) -> None:
    driver, session = _capture_driver()
    with TenantContext.scope(tenant_id):
        execute_atomic_graphrag(driver, None, query_vector=[0.1, 0.2])
    kwargs = session.run.call_args.kwargs
    assert kwargs["tenant_id"] == tenant_id
    assert kwargs["default_tenant_id"] == settings.default_tenant_id


def test_two_tenants_produce_distinct_tenant_params() -> None:
    """Two-tenant harness without a live graph: the same query, run under two
    tenant identities, must send two different ``$tenant_id`` values. (It cannot
    show row filtering — see the module docstring gap note.)"""
    seen: dict[str, str] = {}
    for tenant_id in ("tenant_alpha", "tenant_beta"):
        driver, session = _capture_driver()
        with TenantContext.scope(tenant_id):
            execute_atomic_graphrag(driver, ["Karma"])
        seen[tenant_id] = session.run.call_args.kwargs["tenant_id"]
    assert seen == {"tenant_alpha": "tenant_alpha", "tenant_beta": "tenant_beta"}
    assert seen["tenant_alpha"] != settings.default_tenant_id


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))


def test_vector_seed_with_clauses_are_valid_cypher_order() -> None:
    """`WITH .. WHERE .. ORDER BY .. LIMIT` is not valid Cypher: a WITH takes ORDER BY/LIMIT
    before its WHERE. The tenant filter and the sort/limit must live in separate WITH clauses,
    otherwise every vector-seeded call raises and silently falls back to plain Qdrant."""
    import re

    cypher = re.sub(r"(?m)//.*$", "", ATOMIC_VECTOR_GRAPHRAG_CYPHER)
    for clause in re.split(r"(?m)^\s*WITH\b", cypher)[1:]:
        body = clause.split("CALL {")[0]
        if "WHERE" in body and "ORDER BY" in body:
            assert body.index("ORDER BY") < body.index("WHERE"), body
