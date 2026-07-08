"""Neo4j Graph Data Science (GDS) algorithm stubs.

Checks whether the Neo4j Graph Data Science (GDS) plugin is loaded.
If GDS is present, exposes `run_louvain()` and `run_pagerank()`.
If GDS is absent, the helpers log a warning and return empty results.

GDS is configured via NEO4J_PLUGINS=["apoc","n10s","graph-data-science"]
in docker-compose.yml and k8s helm templates. The Neo4j 5.17.0 Docker image
auto-downloads the matching GDS jar on startup.
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