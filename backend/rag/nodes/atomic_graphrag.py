"""Atomic GraphRAG Traversal Node for Memgraph (2025/2026).

Executes entity expansion, 1-hop weighted retrieval, 2-hop decay traversal,
and formatted subgraph assembly in ONE atomic openCypher query using CALL { ... }
subqueries, eliminating multi-turn LLM/DB roundtrip latency.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Complete Atomic openCypher Query for Seed Entities
ATOMIC_GRAPHRAG_CYPHER = """
UNWIND $seed_entities AS seed_id
MATCH (seed:base)
WHERE seed.entity_id = seed_id OR seed.name = seed_id

// 1. Hop 1 Neighborhood Expansion with Relationship Weighting
CALL {
  WITH seed
  MATCH (seed)-[r1]-(n1:base)
  WHERE NOT type(r1) IN $excluded_rel_types
  WITH seed, r1, n1,
       (coalesce(r1.weight, 1.0) * coalesce(r1.confidence, 1.0)) AS w1
  ORDER BY w1 DESC
  LIMIT $hop1_limit
  RETURN collect(DISTINCT n1) AS hop1_nodes,
         collect({
           source: coalesce(seed.entity_id, seed.name),
           target: coalesce(n1.entity_id, n1.name),
           target_name: n1.name,
           target_type: labels(n1),
           target_desc: coalesce(n1.description, ''),
           rel_type: type(r1),
           rel_weight: w1,
           rel_desc: coalesce(r1.description, type(r1))
         }) AS hop1_edges
}

// 2. Hop 2 Neighborhood Expansion with Distance Decay
CALL {
  WITH seed, hop1_nodes
  UNWIND hop1_nodes AS n1
  MATCH (n1)-[r2]-(n2:base)
  WHERE NOT n2 IN hop1_nodes AND n2 <> seed AND NOT type(r2) IN $excluded_rel_types
  WITH n1, r2, n2,
       (coalesce(r2.weight, 1.0) * coalesce(r2.confidence, 1.0) * $hop2_decay) AS w2
  ORDER BY w2 DESC
  LIMIT $hop2_limit
  RETURN collect({
           source: coalesce(n1.entity_id, n1.name),
           target: coalesce(n2.entity_id, n2.name),
           target_name: n2.name,
           target_type: labels(n2),
           target_desc: coalesce(n2.description, ''),
           rel_type: type(r2),
           rel_weight: w2,
           rel_desc: coalesce(r2.description, type(r2))
         }) AS hop2_edges,
         collect(DISTINCT {
           entity_id: coalesce(n2.entity_id, n2.name),
           name: n2.name,
           labels: labels(n2),
           description: coalesce(n2.description, '')
         }) AS hop2_nodes_data
}

RETURN {
  seed: {
    entity_id: coalesce(seed.entity_id, seed.name),
    name: seed.name,
    labels: labels(seed),
    description: coalesce(seed.description, '')
  },
  hop1_edges: hop1_edges,
  hop2_edges: hop2_edges,
  hop2_nodes: hop2_nodes_data
} AS subgraph_context;
"""

# Native Vector Search + Atomic Neighborhood Traversal
ATOMIC_VECTOR_GRAPHRAG_CYPHER = """
CALL vector_search.search($vector_index, $top_k_seeds, $query_vector)
YIELD node AS seed, similarity

CALL {
  WITH seed
  MATCH (seed)-[r1]-(n1:base)
  WHERE NOT type(r1) IN $excluded_rel_types
  WITH seed, r1, n1,
       (coalesce(r1.weight, 1.0) * coalesce(r1.confidence, 1.0)) AS w1
  ORDER BY w1 DESC
  LIMIT $hop1_limit
  RETURN collect(DISTINCT n1) AS hop1_nodes,
         collect({
           source: coalesce(seed.entity_id, seed.name),
           target: coalesce(n1.entity_id, n1.name),
           target_name: n1.name,
           target_type: labels(n1),
           target_desc: coalesce(n1.description, ''),
           rel_type: type(r1),
           rel_weight: w1,
           rel_desc: coalesce(r1.description, type(r1))
         }) AS hop1_edges
}

CALL {
  WITH seed, hop1_nodes
  UNWIND hop1_nodes AS n1
  MATCH (n1)-[r2]-(n2:base)
  WHERE NOT n2 IN hop1_nodes AND n2 <> seed AND NOT type(r2) IN $excluded_rel_types
  WITH n1, r2, n2,
       (coalesce(r2.weight, 1.0) * coalesce(r2.confidence, 1.0) * $hop2_decay) AS w2
  ORDER BY w2 DESC
  LIMIT $hop2_limit
  RETURN collect({
           source: coalesce(n1.entity_id, n1.name),
           target: coalesce(n2.entity_id, n2.name),
           target_name: n2.name,
           target_type: labels(n2),
           target_desc: coalesce(n2.description, ''),
           rel_type: type(r2),
           rel_weight: w2,
           rel_desc: coalesce(r2.description, type(r2))
         }) AS hop2_edges,
         collect(DISTINCT {
           entity_id: coalesce(n2.entity_id, n2.name),
           name: n2.name,
           labels: labels(n2),
           description: coalesce(n2.description, '')
         }) AS hop2_nodes_data
}

RETURN {
  seed: {
    entity_id: coalesce(seed.entity_id, seed.name),
    name: seed.name,
    labels: labels(seed),
    description: coalesce(seed.description, ''),
    similarity: similarity
  },
  hop1_edges: hop1_edges,
  hop2_edges: hop2_edges,
  hop2_nodes: hop2_nodes_data
} AS subgraph_context;
"""


def format_subgraphs_to_markdown(subgraphs: list[dict[str, Any]]) -> str:
    """Format extracted subgraphs into LLM-ready markdown text."""
    if not subgraphs:
        return ""

    markdown_lines = ["## Ontological Knowledge Graph Context\n"]
    for sg in subgraphs:
        seed = sg.get("seed", {})
        seed_name = seed.get("name") or seed.get("entity_id") or "Unknown Concept"
        similarity = seed.get("similarity")
        if similarity is not None:
            markdown_lines.append(
                f"### Core Concept: **{seed_name}** (Similarity: {similarity:.3f})"
            )
        else:
            markdown_lines.append(f"### Core Concept: **{seed_name}**")

        if seed.get("description"):
            markdown_lines.append(f"> {seed['description']}\n")

        hop1 = sg.get("hop1_edges", [])
        if hop1:
            markdown_lines.append("#### Direct (1-Hop) Doctrinal Relationships:")
            for e in hop1:
                weight_str = f" [weight: {e['rel_weight']:.2f}]" if "rel_weight" in e else ""
                desc_str = (
                    f" - {e['rel_desc']}"
                    if e.get("rel_desc") and e["rel_desc"] != e["rel_type"]
                    else ""
                )
                markdown_lines.append(
                    f"- **{e['source']}** --[{e['rel_type']}{weight_str}]--> **{e['target_name']}**{desc_str}"
                )
            markdown_lines.append("")

        hop2 = sg.get("hop2_edges", [])
        if hop2:
            markdown_lines.append("#### Extended (2-Hop) Contextual Connections:")
            for e in hop2:
                weight_str = f" [weight: {e['rel_weight']:.2f}]" if "rel_weight" in e else ""
                markdown_lines.append(
                    f"- **{e['source']}** --[{e['rel_type']}{weight_str}]--> **{e['target_name']}**"
                )
            markdown_lines.append("")

    return "\n".join(markdown_lines).strip()


def execute_atomic_graphrag(
    driver: Any,
    seed_entities: Optional[list[str]] = None,
    *,
    query_vector: Optional[list[float]] = None,
    vector_index: str = "spiritual_concept_idx",
    top_k_seeds: int = 3,
    hop1_limit: int = 8,
    hop2_limit: int = 5,
    hop2_decay: float = 0.6,
    excluded_rel_types: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Execute Atomic GraphRAG retrieval synchronously against Memgraph.

    Args:
        driver: Neo4j / Memgraph Bolt driver.
        seed_entities: Optional list of starting concept names or entity IDs.
        query_vector: Optional query embedding vector for native Memgraph vector search.
        vector_index: Vector index name in Memgraph.
        top_k_seeds: Number of seed nodes to retrieve if vector search is used.
        hop1_limit: Max 1-hop relationships to traverse per seed.
        hop2_limit: Max 2-hop relationships to traverse.
        hop2_decay: Decay multiplier applied to 2-hop edge weights.
        excluded_rel_types: Relationship types to skip during traversal.

    Returns:
        dict containing:
        - 'subgraphs': list of extracted subgraph dicts
        - 'subgraph_text': formatted markdown context string
        - 'context_document': alias to subgraph_text for RAG compatibility
        - 'source': 'memgraph_atomic_graphrag'
        - 'retrieved_seeds_count': count of seed nodes processed
    """
    if driver is None:
        logger.warning("execute_atomic_graphrag called with driver=None")
        return {
            "subgraphs": [],
            "subgraph_text": "",
            "context_document": "",
            "source": "memgraph_atomic_graphrag",
            "retrieved_seeds_count": 0,
            "error": "Driver unavailable",
        }

    seeds = [s.strip() for s in (seed_entities or []) if s and s.strip()]
    if not seeds and query_vector is None:
        return {
            "subgraphs": [],
            "subgraph_text": "",
            "context_document": "",
            "source": "memgraph_atomic_graphrag",
            "retrieved_seeds_count": 0,
        }

    excluded = (
        excluded_rel_types
        if excluded_rel_types is not None
        else [
            "MUTUALLY_EXCLUSIVE",
            "PRIVATE_NOTE",
        ]
    )

    try:
        with driver.session() as session:
            if query_vector is not None:
                params = {
                    "vector_index": vector_index,
                    "top_k_seeds": top_k_seeds,
                    "query_vector": query_vector,
                    "hop1_limit": hop1_limit,
                    "hop2_limit": hop2_limit,
                    "hop2_decay": hop2_decay,
                    "excluded_rel_types": excluded,
                }
                res = session.run(ATOMIC_VECTOR_GRAPHRAG_CYPHER, **params)
            else:
                params = {
                    "seed_entities": seeds,
                    "hop1_limit": hop1_limit,
                    "hop2_limit": hop2_limit,
                    "hop2_decay": hop2_decay,
                    "excluded_rel_types": excluded,
                }
                res = session.run(ATOMIC_GRAPHRAG_CYPHER, **params)

            subgraphs: list[dict[str, Any]] = []
            for record in res:
                if "subgraph_context" in record:
                    subgraphs.append(record["subgraph_context"])
                elif hasattr(record, "data"):
                    subgraphs.append(record.data().get("subgraph_context", {}))

            subgraph_text = format_subgraphs_to_markdown(subgraphs)

            return {
                "subgraphs": subgraphs,
                "subgraph_text": subgraph_text,
                "context_document": subgraph_text,
                "source": "memgraph_atomic_graphrag",
                "retrieved_seeds_count": len(subgraphs),
            }

    except Exception as e:
        logger.error(f"Error executing atomic GraphRAG query: {e}")
        return {
            "subgraphs": [],
            "subgraph_text": "",
            "context_document": "",
            "source": "memgraph_atomic_graphrag",
            "retrieved_seeds_count": 0,
            "error": str(e),
        }


async def aexecute_atomic_graphrag(
    driver: Any,
    seed_entities: Optional[list[str]] = None,
    *,
    query_vector: Optional[list[float]] = None,
    vector_index: str = "spiritual_concept_idx",
    top_k_seeds: int = 3,
    hop1_limit: int = 8,
    hop2_limit: int = 5,
    hop2_decay: float = 0.6,
    excluded_rel_types: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Async convenience wrapper for execute_atomic_graphrag."""
    return await asyncio.to_thread(
        execute_atomic_graphrag,
        driver,
        seed_entities=seed_entities,
        query_vector=query_vector,
        vector_index=vector_index,
        top_k_seeds=top_k_seeds,
        hop1_limit=hop1_limit,
        hop2_limit=hop2_limit,
        hop2_decay=hop2_decay,
        excluded_rel_types=excluded_rel_types,
    )
