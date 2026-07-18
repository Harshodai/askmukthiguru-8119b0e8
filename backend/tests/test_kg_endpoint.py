"""
Regression tests for the hardened /api/kg/sparql read-only guard.

See SECURE_CODE_REVIEW finding F-01: the old guard was an uppercased
substring denylist and the query ran via plain auto-commit `session.run`.
These tests lock in that (a) whitespace/comment bypass tricks are now
caught by the token-boundary guard, and (b) legitimate reads still work
end-to-end through a Neo4j-enforced read transaction.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.kg import _assert_read_only, _normalize
from app.main import app, get_current_user_from_supabase

client = TestClient(app)


def _admin_user():
    return {"id": "admin-1", "email": "admin@example.com", "is_superuser": True}


def _regular_user():
    return {"id": "user-1", "email": "user@example.com", "is_superuser": False}


@pytest.fixture(autouse=True)
def _admin_override():
    app.dependency_overrides[get_current_user_from_supabase] = _admin_user
    yield
    app.dependency_overrides.pop(get_current_user_from_supabase, None)


# --------------------------------------------------------------------------
# Guard unit tests — the bypasses SECURE_CODE_REVIEW.md flagged as working
# against the old substring denylist.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "MATCH (n) DETACH DELETE n",
        "MATCH (n) SET\tn.x = 1",                       # whitespace variant
        "MATCH (n) SET\nn.x = 1",
        "MATCH (n) CALL/**/apoc.create.node([],{})",     # comment-split phrase
        "LOAD CSV FROM 'file:///etc/passwd' AS row RETURN row",
        "MATCH (n) FOREACH (x IN [1] | CREATE (m))",
        "CALL dbms.security.createUser('x','y',false)",  # non-allowlisted CALL
        "CREATE (n:Evil) RETURN n",
        "MATCH (n) REMOVE n.x",
        "MATCH (n) DROP INDEX foo",
    ],
)
def test_write_bypass_payloads_are_blocked(query):
    with pytest.raises(Exception):
        _assert_read_only(_normalize(query))


def test_legit_reads_pass_the_guard():
    _assert_read_only(_normalize("MATCH (n:Concept) RETURN n LIMIT 10"))
    _assert_read_only(_normalize("CALL db.labels()"))


# --------------------------------------------------------------------------
# Endpoint tests
# --------------------------------------------------------------------------

def test_kg_sparql_rejects_write_without_touching_driver():
    """Blocked queries must 400 without ever touching Neo4j."""
    async def _mock_check_input(_q):
        return {"blocked": False}

    container = MagicMock()
    container.guardrails = MagicMock()
    container.guardrails.check_input = _mock_check_input

    with patch("app.api.kg.get_container", return_value=container):
        resp = client.post("/api/kg/sparql", json={"query": "MATCH (n) DETACH DELETE n"})
        assert resp.status_code == 400


def test_kg_sparql_requires_admin():
    app.dependency_overrides[get_current_user_from_supabase] = _regular_user
    resp = client.post("/api/kg/sparql", json={"query": "MATCH (n) RETURN n LIMIT 1"})
    assert resp.status_code == 403


def test_kg_sparql_runs_inside_managed_read_transaction():
    """Legit query executes via session.execute_read (not auto-commit run)."""

    class _Rec(dict):
        def keys(self):
            return list(super().keys())

        def get(self, k, default=None):
            return dict.get(self, k, default)

    fake_result = [_Rec(name="Beautiful State")]

    def _execute_read(fn, **kwargs):
        tx = MagicMock()
        tx.run.return_value = iter(fake_result)
        return fn(tx)

    session = MagicMock()
    session.execute_read.side_effect = _execute_read
    session.run.side_effect = AssertionError("must use execute_read, not auto-commit run")
    session.__enter__.return_value = session
    session.__exit__.return_value = False

    driver = MagicMock()
    driver.session.return_value = session

    async def _mock_check_input(_q):
        return {"blocked": False}

    container = MagicMock()
    container.neo4j_driver = driver
    container.guardrails = MagicMock()
    container.guardrails.check_input = _mock_check_input

    with patch("app.api.kg.get_container", return_value=container):
        resp = client.post(
            "/api/kg/sparql",
            json={"query": "MATCH (n:Concept {name: 'Beautiful State'}) RETURN n.name AS name", "limit": 10},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"] == ["name"]
    assert body["rows"] == [{"name": "Beautiful State"}]
    session.execute_read.assert_called_once()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
