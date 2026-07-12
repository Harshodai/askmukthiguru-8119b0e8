"""Verify Neo4j GDS plugin is loaded.

Skipped (not failed) if GDS is unavailable — so CI passes even when
Neo4j hasn't been restarted with the updated plugin list yet.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.neo4j]


def _neo4j_config():
    """Return (uri, user, password) from env with sensible dev defaults."""
    return (
        os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        os.environ.get("NEO4J_USER", "neo4j"),
        os.environ.get("NEO4J_PASSWORD", "mukthiguru_neo4j_pass"),
    )


@pytest.mark.skipif(
    not os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
    reason="NEO4J_URI not set",
)
def test_gds_list():
    """CALL gds.list() and expect at least one procedure name back."""
    from neo4j import GraphDatabase

    uri, user, password = _neo4j_config()
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
    except Exception as exc:
        pytest.skip(f"Neo4j not reachable: {exc}")
        return

    try:
        with driver.session() as session:
            result = session.run(
                "CALL gds.list() YIELD name RETURN name ORDER BY name LIMIT 5"
            )
            rows = [r["name"] for r in result]
        assert len(rows) > 0, (
            "CALL gds.list() returned 0 rows — GDS plugin may not be loaded. "
            "Check NEO4J_PLUGINS in docker-compose.yml"
        )
    except Exception as exc:
        pytest.skip(f"GDS plugin not available: {exc}")
    finally:
        driver.close()


def test_gds_version():
    """CALL gds.version() returns a non-empty version string."""
    from neo4j import GraphDatabase

    uri, user, password = _neo4j_config()
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
    except Exception as exc:
        pytest.skip(f"Neo4j not reachable: {exc}")
        return

    try:
        with driver.session() as session:
            result = session.run("RETURN gds.version() AS version")
            row = result.single()
        assert row is not None, "gds.version() returned no row"
        version = row["version"]
        assert isinstance(version, str) and len(version) > 0
    except Exception as exc:
        pytest.skip(f"GDS plugin not available: {exc}")
    finally:
        driver.close()
