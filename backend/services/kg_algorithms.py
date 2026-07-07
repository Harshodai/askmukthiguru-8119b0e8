"""Neo4j Graph Data Science (GDS) algorithm stubs (Task E4.5).

Checks whether the Neo4j Graph Data Science (GDS) plugin is loaded.
If GDS is present, exposes `run_louvain()` and `run_pagerank()`.
If GDS is absent (the current state — only apoc.jar + n10s.jar are loaded),
the helpers log a warning and return empty results.

## GDS Status — ROADMAP (2026-07-07)

GDS is NOT loaded on `mukthiguru-neo4j`. Plugin directory contents:
    /var/lib/neo4j/plugins/README.txt
    /var/lib/neo4j/plugins/apoc.jar
    /var/lib/neo4j/plugins/n10s.jar

To enable GDS (roadmap):
  1. Download `neo4j-graph-data-science-<version>.jar` matching the Neo4j
     server version (currently 5.17.0 — see apoc jar filename) from
     https://neo4j.com/deployment-center/#gds-tab
  2. Drop the jar into the Neo4j plugins volume
     (`/var/lib/neo4j/plugins/` in the container; mount in docker-compose).
  3. In `neo4j.conf`: `dbms.security.procedures.unrestricted=gds.*,apoc.*,n10s.*`
     and `dbms.security.procedures.allowlist=gds.*,apoc.*,n10s.*`
  4. Restart Neo4j. Verify: `CALL gds.list() YIELD name RETURN count(*)`
     (or `RETURN gds.version()`).
  5. Then re-enable the real algorithm bodies below (the graph projection
     + stream patterns are stubbed in comments).

Do NOT install GDS unilaterally — it changes the Neo4j image footprint and
needs volume/permission coordination with docker-compose.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_GDS_AVAILABLE: Optional[bool] = None


def _gds_procedure_available(driver) -> bool:
    """Return True if `gds.list()` is callable. Cached after first check."""
    global _GDS_AVAILABLE
    if _GDS_AVAILABLE is not None:
        return _GDS_AVAILABLE
    if driver is None:
        _GDS_AVAILABLE = False
        return False
    try:
        with driver.session() as session:
            session.run("CALL gds.list() YIELD name RETURN name LIMIT 1").consume()
        _GDS_AVAILABLE = True
        logger.info("GDS plugin detected — kg_algorithms enabled.")
    except Exception:
        _GDS_AVAILABLE = False
        logger.warning(
            "GDS plugin NOT loaded on Neo4j — kg_algorithms returning empty. "
            "See module docstring for install roadmap."
        )
    return _GDS_AVAILABLE


async def run_louvain(
    neo4j_driver: Any,
    *,
    node_label: str = "base",
    relationship_type: str = "RELATED_TO",
    graph_name: str = "kg_louvain",
) -> list[dict[str, Any]]:
    """Run Louvain community detection. Returns [{node_id, communityId}, ...].

    Stub: returns [] if GDS is absent. If present, projects an in-memory
    graph and streams Louvain results.
    """
    if neo4j_driver is None:
        return []
    available = await asyncio.to_thread(_gds_procedure_available, neo4j_driver)
    if not available:
        return []
    try:
        def _run() -> list[dict[str, Any]]:
            with neo4j_driver.session() as session:
                # Project (idempotent-ish: drop first)
                try:
                    session.run(f"CALL gds.graph.drop('{graph_name}', false)").consume()
                except Exception:
                    pass
                session.run(
                    "CALL gds.graph.project($name, $node, $rel)",
                    name=graph_name, node=node_label, rel=relationship_type,
                ).consume()
                rows = session.run(
                    f"CALL gds.louvain.stream('{graph_name}') "
                    "YIELD nodeId, communityId "
                    "RETURN gds.util.asNode(nodeId).entity_id AS node_id, communityId"
                )
                return [{"node_id": r["node_id"], "communityId": r["communityId"]} for r in rows]
        return await asyncio.to_thread(_run)
    except Exception as e:
        logger.warning(f"run_louvain failed: {e}")
        return []


async def run_pagerank(
    neo4j_driver: Any,
    *,
    node_label: str = "base",
    relationship_type: str = "RELATED_TO",
    graph_name: str = "kg_pagerank",
    max_iterations: int = 20,
) -> list[dict[str, Any]]:
    """Run PageRank. Returns [{node_id, score}, ...] sorted desc by score.

    Stub: returns [] if GDS is absent.
    """
    if neo4j_driver is None:
        return []
    available = await asyncio.to_thread(_gds_procedure_available, neo4j_driver)
    if not available:
        return []
    try:
        def _run() -> list[dict[str, Any]]:
            with neo4j_driver.session() as session:
                try:
                    session.run(f"CALL gds.graph.drop('{graph_name}', false)").consume()
                except Exception:
                    pass
                session.run(
                    "CALL gds.graph.project($name, $node, $rel)",
                    name=graph_name, node=node_label, rel=relationship_type,
                ).consume()
                rows = session.run(
                    f"CALL gds.pageRank.stream('{graph_name}', {{maxIterations: $iter}}) "
                    "YIELD nodeId, score "
                    "RETURN gds.util.asNode(nodeId).entity_id AS node_id, score "
                    "ORDER BY score DESC LIMIT 50",
                    iter=max_iterations,
                )
                return [{"node_id": r["node_id"], "score": r["score"]} for r in rows]
        return await asyncio.to_thread(_run)
    except Exception as e:
        logger.warning(f"run_pagerank failed: {e}")
        return []


if __name__ == "__main__":
    # Self-check — no live Neo4j needed. None driver -> [] for both.
    import asyncio as _a
    assert _a.run(run_louvain(None)) == []
    assert _a.run(run_pagerank(None)) == []
    # _gds_procedure_available with None -> False, cached.
    _GDS_AVAILABLE = None  # reset cache
    assert _gds_procedure_available(None) is False
    print("kg_algorithms self-check OK (GDS-absent degraded path verified).")