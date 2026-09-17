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

_ALGO_BACKEND: Optional[str] = None  # "mage", "gds", or "none"


def _gds_procedure_available(driver) -> bool:
    """Return True if an algorithm backend (MAGE or GDS) is callable. Cached after first check."""
    return _detect_algorithm_backend(driver) != "none"


def _detect_algorithm_backend(driver) -> str:
    """Detect whether Memgraph MAGE or Neo4j GDS is available."""
    global _ALGO_BACKEND
    if _ALGO_BACKEND is not None:
        return _ALGO_BACKEND
    if driver is None:
        _ALGO_BACKEND = "none"
        return _ALGO_BACKEND
    try:
        with driver.session() as session:
            # 1. Probe for Memgraph MAGE
            try:
                res = session.run(
                    "CALL mg.procedures() YIELD name WHERE name = 'pagerank.get' RETURN count(*) AS cnt"
                ).single()
                if res and res["cnt"] > 0:
                    _ALGO_BACKEND = "mage"
                    logger.info("Memgraph MAGE algorithms detected — kg_algorithms enabled.")
                    return _ALGO_BACKEND
            except Exception:
                pass

            # 2. Probe for Neo4j GDS
            try:
                session.run("CALL gds.list() YIELD name RETURN name LIMIT 1").consume()
                _ALGO_BACKEND = "gds"
                logger.info("Neo4j GDS plugin detected — kg_algorithms enabled.")
                return _ALGO_BACKEND
            except Exception:
                pass
    except Exception:
        pass

    _ALGO_BACKEND = "none"
    logger.warning("Neither Memgraph MAGE nor Neo4j GDS detected — kg_algorithms returning empty.")
    return _ALGO_BACKEND


async def run_louvain(
    neo4j_driver: Any,
    *,
    node_label: str = "base",
    relationship_type: str = "RELATED_TO",
    graph_name: str = "kg_louvain",
) -> list[dict[str, Any]]:
    """Run Louvain community detection. Returns [{node_id, communityId}, ...]."""
    if neo4j_driver is None:
        return []
    backend = await asyncio.to_thread(_detect_algorithm_backend, neo4j_driver)
    if backend == "none":
        return []
    try:

        def _run() -> list[dict[str, Any]]:
            with neo4j_driver.session() as session:
                if backend == "mage":
                    # Memgraph MAGE community detection
                    rows = session.run(
                        "CALL community_detection.get() YIELD node, community_id "
                        "RETURN coalesce(node.entity_id, node.name, toString(id(node))) AS node_id, community_id AS communityId"
                    )
                    return [
                        {"node_id": r["node_id"], "communityId": r["communityId"]} for r in rows
                    ]
                else:
                    # Neo4j GDS projection
                    try:
                        session.run(f"CALL gds.graph.drop('{graph_name}', false)").consume()
                    except Exception as _e:
                        logger.debug("[kg algorithms] suppressed non-critical error: %s", _e)
                    session.run(
                        "CALL gds.graph.project($name, $node, $rel)",
                        name=graph_name,
                        node=node_label,
                        rel=relationship_type,
                    ).consume()
                    rows = session.run(
                        f"CALL gds.louvain.stream('{graph_name}') "
                        "YIELD nodeId, communityId "
                        "RETURN gds.util.asNode(nodeId).entity_id AS node_id, communityId"
                    )
                    return [
                        {"node_id": r["node_id"], "communityId": r["communityId"]} for r in rows
                    ]

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
    """Run PageRank. Returns [{node_id, score}, ...] sorted desc by score."""
    if neo4j_driver is None:
        return []
    backend = await asyncio.to_thread(_detect_algorithm_backend, neo4j_driver)
    if backend == "none":
        return []
    try:

        def _run() -> list[dict[str, Any]]:
            with neo4j_driver.session() as session:
                if backend == "mage":
                    # Memgraph MAGE PageRank
                    rows = session.run(
                        "CALL pagerank.get() YIELD node, rank "
                        "RETURN coalesce(node.entity_id, node.name, toString(id(node))) AS node_id, rank AS score "
                        "ORDER BY score DESC LIMIT 50"
                    )
                    return [{"node_id": r["node_id"], "score": r["score"]} for r in rows]
                else:
                    # Neo4j GDS projection
                    try:
                        session.run(f"CALL gds.graph.drop('{graph_name}', false)").consume()
                    except Exception as _e:
                        logger.debug("[kg algorithms] suppressed non-critical error: %s", _e)
                    session.run(
                        "CALL gds.graph.project($name, $node, $rel)",
                        name=graph_name,
                        node=node_label,
                        rel=relationship_type,
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
    import asyncio as _a

    assert _a.run(run_louvain(None)) == []
    assert _a.run(run_pagerank(None)) == []
    _ALGO_BACKEND = None
    assert _gds_procedure_available(None) is False
    print("kg_algorithms self-check OK (MAGE/GDS fallback verified).")
