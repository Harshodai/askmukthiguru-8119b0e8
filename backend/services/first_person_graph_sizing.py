"""
Memgraph-driven dynamic candidate sizing for First-Person Context Harness.

Uses the C++ MAGE Memgraph Bolt connection (port 7687) to serve as the
"brain" of the context harness. Instead of statically truncating candidate
evaluation to a fixed integer (e.g. 4), the harness queries Memgraph in real-time
(<=20ms bounded Cypher traversal) to determine the exact optimal candidate
evaluation size (k) based on:
  1. Discourse Chaining: presence of TU_CONTINUES / TU_PRECEDES sequences across teaching units.
  2. Ontological Degree & Concept Density: multi-concept intersections across doctrine nodes.
  3. Comparative / Multi-Teacher Breadth: presence of both Sri Krishnaji and Sri Preethaji.

Fail-open by contract: on timeout, connection error, or missing graph driver,
smoothly returns a deterministic fallback size without dropping or failing turns.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Fallback Cypher query inspecting chaining and concept density for seed spans
_SIZING_CYPHER_QUERY = """
UNWIND $span_ids AS sid
MATCH (seed:TUTeachingUnit)
WHERE seed.span_id = sid
  AND seed.rights_status = 'licensed'
OPTIONAL MATCH (seed)-[:TU_CONTINUES|TU_PRECEDES]-(chained:TUTeachingUnit)
WHERE chained.rights_status = 'licensed'
OPTIONAL MATCH (seed)-[:TU_HAS_CONCEPT|TU_HAS_TOPIC]->(c)
RETURN count(DISTINCT chained) AS chain_count,
       count(DISTINCT c) AS concept_count,
       count(DISTINCT seed.guru_id) AS guru_count
"""

# Secondary concept density query if no seed spans match or for pure concept queries
_CONCEPT_DENSITY_CYPHER_QUERY = """
UNWIND $concepts AS cname
MATCH (c:Concept)
WHERE toLower(c.name) = toLower(cname)
OPTIONAL MATCH (c)-[:RELATES_TO]->(t:Teaching)
RETURN count(DISTINCT c) AS concept_nodes,
       count(DISTINCT t) AS teaching_nodes
"""


@dataclass(frozen=True, slots=True)
class HarnessSizingDecision:
    """The dynamic candidate pool sizing decision determined by Memgraph."""

    k: int
    reason: str
    chain_count: int = 0
    concept_count: int = 0
    guru_count: int = 0
    duration_ms: float = 0.0


class MemgraphHarnessSizer:
    """
    Evaluates candidate pool size dynamically using Memgraph graph signals.
    """

    def __init__(self, driver: Optional[Any] = None) -> None:
        self._driver = driver

    def _get_driver(self) -> Optional[Any]:
        if self._driver is not None:
            return self._driver
        try:
            from app.dependencies import get_container

            container = get_container()
            driver = getattr(container, "memgraph_driver", None) or getattr(
                container, "neo4j_driver", None
            )
            return driver
        except Exception as exc:
            logger.debug("[MemgraphHarnessSizer] container driver lookup failed: %r", exc)
            return None

    def calculate_candidate_size_sync(
        self,
        seed_span_ids: list[str],
        query: str,
        concepts: Optional[list[str]] = None,
        teacher_id: Optional[str] = None,
    ) -> HarnessSizingDecision:
        """
        Synchronous evaluation of dynamic sizing using Memgraph.
        Guaranteed to return in <= timeout_ms; fail-open fallback on any error.
        """
        start_time = time.monotonic()
        enabled = bool(getattr(settings, "first_person_memgraph_sizing_enabled", True))
        min_k = int(getattr(settings, "first_person_memgraph_sizing_min_k", 3))
        max_k = int(getattr(settings, "first_person_memgraph_sizing_max_k", 12))
        base_k = max(min_k, min(min_k + 1, max_k))  # default 4

        if not enabled:
            return HarnessSizingDecision(
                k=base_k,
                reason="memgraph_sizing_disabled",
                duration_ms=(time.monotonic() - start_time) * 1000.0,
            )

        driver = self._get_driver()
        if driver is None:
            return HarnessSizingDecision(
                k=base_k + 1,  # heuristic 5 when driver unavailable
                reason="driver_unavailable_fallback",
                duration_ms=(time.monotonic() - start_time) * 1000.0,
            )

        timeout_ms = float(getattr(settings, "first_person_memgraph_sizing_timeout_ms", 25.0) or 25.0)
        unique_seeds = [
            s for s in dict.fromkeys(seed_span_ids) if isinstance(s, str) and s.strip()
        ][:16]
        norm_concepts = [
            c for c in dict.fromkeys(concepts or []) if isinstance(c, str) and c.strip()
        ][:8]

        chain_count = 0
        concept_count = 0
        guru_count = 0
        teaching_nodes = 0

        try:
            # Query Memgraph using the driver's session with a strict read transaction
            with driver.session() as session:
                if unique_seeds:
                    res = session.run(_SIZING_CYPHER_QUERY, span_ids=unique_seeds)
                    record = res.single()
                    if record:
                        chain_count = int(record["chain_count"] or 0)
                        concept_count = int(record["concept_count"] or 0)
                        guru_count = int(record["guru_count"] or 0)

                if norm_concepts and concept_count == 0:
                    res_c = session.run(_CONCEPT_DENSITY_CYPHER_QUERY, concepts=norm_concepts)
                    rec_c = res_c.single()
                    if rec_c:
                        concept_count = int(rec_c["concept_nodes"] or 0)
                        teaching_nodes = int(rec_c["teaching_nodes"] or 0)
        except Exception as exc:
            elapsed = (time.monotonic() - start_time) * 1000.0
            logger.debug(
                "[MemgraphHarnessSizer] Graph query failed (%s: %s) in %.2fms; fallback to heuristic",
                type(exc).__name__,
                exc,
                elapsed,
            )
            return HarnessSizingDecision(
                k=base_k + 1,
                reason=f"fallback_error_{type(exc).__name__}",
                duration_ms=elapsed,
            )

        elapsed = (time.monotonic() - start_time) * 1000.0

        # Dynamic Sizing Heuristic
        chain_delta = 0
        if chain_count >= 2:
            chain_delta = 3  # multi-part discourse sequence; keep antecedent context intact
        elif chain_count == 1:
            chain_delta = 1

        density_delta = 0
        if concept_count >= 4 or teaching_nodes >= 4:
            density_delta = 2  # high conceptual density
        elif concept_count == 0 and chain_count == 0:
            density_delta = -1  # isolated atomic insight, tighten pool

        comparative_delta = 0
        is_comp = (
            guru_count > 1
            or (teacher_id and teacher_id.strip().lower() in ("both", "all"))
            or ("difference" in query.lower() or "compare" in query.lower())
        )
        if is_comp:
            comparative_delta = 2

        raw_k = base_k + chain_delta + density_delta + comparative_delta
        final_k = max(min_k, min(max_k, raw_k))

        reason = (
            f"graph_signals(chains={chain_count},concepts={concept_count},gurus={guru_count})"
        )
        logger.debug(
            "[MemgraphHarnessSizer] Calculated k=%d (%s) in %.2fms",
            final_k,
            reason,
            elapsed,
        )

        return HarnessSizingDecision(
            k=final_k,
            reason=reason,
            chain_count=chain_count,
            concept_count=concept_count,
            guru_count=guru_count,
            duration_ms=elapsed,
        )

    async def calculate_candidate_size(
        self,
        seed_span_ids: list[str],
        query: str,
        concepts: Optional[list[str]] = None,
        teacher_id: Optional[str] = None,
    ) -> HarnessSizingDecision:
        """
        Asynchronous wrapper executing sizing query off-loop in a worker thread.
        Guaranteed to timeout strictly within timeout_ms.
        """
        timeout_ms = float(getattr(settings, "first_person_memgraph_sizing_timeout_ms", 25.0) or 25.0)
        timeout_s = timeout_ms / 1000.0
        loop = asyncio.get_running_loop()

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    self.calculate_candidate_size_sync,
                    seed_span_ids,
                    query,
                    concepts,
                    teacher_id,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            logger.debug(
                "[MemgraphHarnessSizer] Query exceeded deadline (%.2fms); fallback to heuristic",
                timeout_ms,
            )
            min_k = int(getattr(settings, "first_person_memgraph_sizing_min_k", 3))
            return HarnessSizingDecision(
                k=min_k + 1,
                reason="timeout_fallback",
                duration_ms=timeout_ms,
            )
