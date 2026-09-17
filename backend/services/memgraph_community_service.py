"""Memgraph MAGE Community Service for Hierarchical GraphRAG.

Provides:
- Community detection using Memgraph MAGE Louvain (`community_detection.get`)
- Cluster aggregation and central concept extraction
- Automated compilation of :Community doctrine summaries
- Global GraphRAG retrieval for high-level thematic queries
- Graceful fallback when MAGE is not installed or during testing
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CommunityCluster:
    community_id: int
    member_count: int
    members: list[dict[str, Any]]
    title: str = ""
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    central_entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "community_id": self.community_id,
            "member_count": self.member_count,
            "title": self.title,
            "summary": self.summary,
            "keywords": self.keywords,
            "central_entities": self.central_entities,
            "members": self.members,
        }


class MemgraphCommunityService:
    """Manages precomputation and global retrieval of GraphRAG communities."""

    def __init__(self, driver: Any, llm_service: Optional[Any] = None) -> None:
        self.driver = driver
        self.llm = llm_service
        self._mage_available: Optional[bool] = None

    def check_mage_available(self) -> bool:
        """Check if Memgraph MAGE community_detection procedure is registered."""
        if self._mage_available is not None:
            return self._mage_available
        if self.driver is None:
            self._mage_available = False
            return False

        try:
            with self.driver.session() as session:
                res = session.run(
                    "CALL mg.procedures() YIELD name "
                    "WHERE name = 'community_detection.get' "
                    "RETURN count(*) AS cnt"
                ).single()
                self._mage_available = bool(res and res["cnt"] > 0)
        except Exception as e:
            logger.debug(f"Failed to probe Memgraph MAGE procedures: {e}")
            self._mage_available = False

        return self._mage_available

    def _run_community_pipeline_tx(
        self,
        tx: Any,
        *,
        has_mage: bool,
        weight_property: str,
        min_community_size: int,
    ) -> list[dict[str, Any]]:
        """Unit-of-work for the Louvain-detect -> cluster -> persist pipeline.

        Runs entirely inside the ONE transaction `session.execute_write`
        opens for it. Previously each step was its own `session.run()`,
        which Memgraph auto-commits independently -- an OOM between the
        community_id SET (step 1) and the :Community persist (step 4) left
        `node.community_id` committed with no matching summary node ever
        written (observed: 178 :Community nodes, ~170 stale after a
        512MB-cap OOM mid-run). Raising here rolls back every write this
        function made, so a crash leaves the graph exactly as it was before
        the run started instead of half-updated.
        """
        # 1. Execute MAGE Louvain (writes node.community_id)
        if has_mage:
            try:
                tx.run(
                    "CALL community_detection.get($weight) YIELD node, community_id "
                    "SET node.community_id = community_id",
                    weight=weight_property,
                ).consume()
            except Exception as e:
                logger.warning(f"MAGE community_detection execution failed: {e}")

        # 2. Extract cluster groupings from node.community_id
        cluster_query = """
        MATCH (n:base)
        WHERE n.community_id IS NOT NULL
        WITH n.community_id AS cid,
             collect({
               entity_id: coalesce(n.entity_id, n.name),
               name: n.name,
               description: coalesce(n.description, ''),
               labels: labels(n),
               degree: size([(n)-[]-() | 1])
             }) AS members,
             count(n) AS member_count
        WHERE member_count >= $min_size
        RETURN cid, member_count, members
        ORDER BY member_count DESC
        """
        records = tx.run(cluster_query, min_size=min_community_size)
        raw_clusters = [dict(r) for r in records]

        if not raw_clusters:
            logger.info("No communities found matching min_size filter.")
            return []

        # 3. Generate summaries (pure Python, no DB access)
        summarized_clusters = self.generate_community_summaries(raw_clusters)

        # 4. Persist :Community nodes and member links
        persist_query = """
        UNWIND $summaries AS s
        MERGE (c:Community {community_id: s.community_id})
        SET c.title = s.title,
            c.summary = s.summary,
            c.keywords = s.keywords,
            c.member_count = s.member_count,
            c.central_entities = s.central_entities,
            c.updated_at = datetime()
        WITH c, s
        UNWIND s.central_entities AS cent
        MATCH (n:base) WHERE n.name = cent OR n.entity_id = cent
        MERGE (c)-[:HAS_CENTRAL_MEMBER]->(n)
        """
        payload = [c.to_dict() for c in summarized_clusters]
        tx.run(persist_query, summaries=payload).consume()

        return payload

    def compute_and_store_communities(
        self,
        *,
        weight_property: str = "weight",
        min_community_size: int = 2,
    ) -> list[dict[str, Any]]:
        """Synchronously execute Louvain community detection via MAGE and persist :Community nodes.

        Runs the detect/cluster/persist steps in one explicit transaction
        (`session.execute_write`) so they commit or roll back together --
        see `_run_community_pipeline_tx` for why that matters.
        """
        if self.driver is None:
            logger.warning("MemgraphCommunityService: driver is None, returning empty.")
            return []

        has_mage = self.check_mage_available()

        try:
            with self.driver.session() as session:
                payload = session.execute_write(
                    self._run_community_pipeline_tx,
                    has_mage=has_mage,
                    weight_property=weight_property,
                    min_community_size=min_community_size,
                )
                if payload:
                    logger.info(f"Persisted {len(payload)} :Community nodes to Memgraph.")
                return payload

        except Exception as e:
            logger.error(f"Error in compute_and_store_communities: {e}")
            return []

    async def acompute_and_store_communities(
        self,
        *,
        weight_property: str = "weight",
        min_community_size: int = 2,
    ) -> list[dict[str, Any]]:
        """Async convenience wrapper for compute_and_store_communities."""
        return await asyncio.to_thread(
            self.compute_and_store_communities,
            weight_property=weight_property,
            min_community_size=min_community_size,
        )

    def generate_community_summaries(
        self,
        raw_clusters: list[dict[str, Any]],
    ) -> list[CommunityCluster]:
        """Compile structured summaries for each detected community cluster."""
        results: list[CommunityCluster] = []

        for cluster in raw_clusters:
            cid = int(cluster.get("cid", 0))
            count = int(cluster.get("member_count", 0))
            members = cluster.get("members", [])

            # Rank members by in-graph degree
            sorted_members = sorted(members, key=lambda m: m.get("degree", 0), reverse=True)
            # ponytail: most LightRAG-inserted nodes carry entity_id but not name;
            # fall back to entity_id so central_entities isn't empty for those clusters
            central_entities = [
                (m.get("name") or m.get("entity_id"))
                for m in sorted_members[:5]
                if (m.get("name") or m.get("entity_id"))
            ]

            # Compile title & summary
            if len(central_entities) >= 2:
                title = f"{central_entities[0]} & {central_entities[1]} Teaching Domain"
            elif central_entities:
                title = f"{central_entities[0]} Spiritual Domain"
            else:
                title = f"Doctrinal Community {cid}"

            summary = (
                f"Core spiritual doctrine cluster encompassing {count} interconnected concepts "
                f"focused on {', '.join(central_entities[:3])}. Provides foundational practices "
                "and philosophical context within the lineage."
            )

            results.append(
                CommunityCluster(
                    community_id=cid,
                    member_count=count,
                    members=members,
                    title=title,
                    summary=summary,
                    keywords=central_entities,
                    central_entities=central_entities,
                )
            )

        return results

    def retrieve_community_summaries(
        self,
        query_concepts: list[str],
        *,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Retrieve top macro-community summaries matching query concepts."""
        if self.driver is None or not query_concepts:
            return []

        clean_concepts = [c.strip() for c in query_concepts if c and c.strip()]
        if not clean_concepts:
            return []

        query = """
        MATCH (n:base)
        WHERE n.entity_id IN $concepts OR n.name IN $concepts
        MATCH (c:Community {community_id: n.community_id})
        WITH c, count(DISTINCT n) AS matched_concepts, collect(DISTINCT n.name) AS overlap
        RETURN c.community_id AS community_id,
               c.title AS title,
               c.summary AS summary,
               c.keywords AS keywords,
               c.central_entities AS central_entities,
               c.member_count AS member_count,
               matched_concepts,
               overlap
        ORDER BY matched_concepts DESC, c.member_count DESC
        LIMIT $top_k
        """
        try:
            with self.driver.session() as session:
                res = session.run(query, concepts=clean_concepts, top_k=top_k)
                return [dict(r) for r in res]
        except Exception as e:
            logger.error(f"retrieve_community_summaries failed: {e}")
            return []

    async def aretrieve_community_summaries(
        self,
        query_concepts: list[str],
        *,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Async convenience wrapper for retrieve_community_summaries."""
        return await asyncio.to_thread(
            self.retrieve_community_summaries,
            query_concepts,
            top_k=top_k,
        )
