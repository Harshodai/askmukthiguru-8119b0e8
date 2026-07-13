"""Agentic Graph RAG traversal tools for LLM-driven graph walking.

This module provides deterministic Neo4j query tools that an LLM can call
to traverse the ontology graph during COMPARAITIVE intent processing.
Tool return values include navigation hints so the LLM can decide
what to explore next.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Dict, Optional

from app.config import settings
from rag.states import GraphState

logger = logging.getLogger(__name__)


async def get_concept_details(entity_id: str, state: GraphState) -> Dict[str, Any]:
    """
    Deterministic Neo4j query to retrieve full details of a concept node.

    Returns node properties, relationships, and adjacent concepts with navigation hints.
    This allows the LLM to understand the entity and decide what to explore next.

    Args:
        entity_id: The entity_id of the concept to retrieve
        state: Current pipeline state for context

    Returns:
        Dict containing:
        - node_data: Full node properties and type
        - relationships: Direct parent/child relationships with descriptions
        - adjacent_concepts: List of {entity_id, relation_type, relation_description}
        - navigation_hints: Recommendations for next traversal steps
        - source: "neo4j_ontology"
    """
    from app.dependencies import get_container

    try:
        driver = get_container().neo4j_driver
        if driver is None:
            raise RuntimeError("Neo4j driver unavailable")

        def _query(tx):
            cypher = """
            MATCH (n {entity_id: $entity_id})
            OPTIONAL MATCH (n)-[r]->(child)
            OPTIONAL MATCH (parent)-[p]->(n)
            RETURN n, collect(DISTINCT r) as rels, collect(DISTINCT p) as parents
            """
            result = tx.run(cypher, entity_id=entity_id)
            record = result.single()
            if not record:
                return None

            node = dict(record["n"])
            node["entity_id"] = node.get("entity_id")
            node["name"] = node.get("name")
            node["type"] = node.get("type")
            node["description"] = node.get("description")

            adjacent_concepts = []
            relationships = []

            # Extract child relationships from the records
            for rel in record["rels"]:
                if rel:
                    child = rel.end_node
                    child_dict = dict(child)
                    adjacent_concepts.append({
                        "entity_id": child_dict.get("entity_id"),
                        "relation_type": rel.type,
                        "relation_description": rel.get("description") or rel.type,
                        "child_name": child_dict.get("name"),
                        "child_type": child_dict.get("type"),
                    })
                    relationships.append({
                        "type": rel.type,
                        "description": rel.get("description") or rel.type,
                        "target": child_dict.get("name"),
                        "target_type": child_dict.get("type"),
                    })

            # Build navigation hints
            navigation_hints = []
            if adjacent_concepts:
                # Suggest exploring key adjacent concepts
                for adj in adjacent_concepts[:3]:
                    if adj["entity_id"]:
                        navigation_hints.append(
                            f"Explore '{adj['child_name']}' via relation '{adj['relation_type']}': {adj['relation_description']}"
                        )

            return {
                "node_data": {
                    "entity_id": node.get("entity_id"),
                    "name": node.get("name"),
                    "type": node.get("type"),
                    "description": node.get("description"),
                    "properties": {k: v for k, v in node.items() if k not in ["entity_id", "name", "type", "description"]},
                },
                "relationships": relationships,
                "adjacent_concepts": adjacent_concepts,
                "navigation_hints": navigation_hints,
                "source": "neo4j_ontology",
            }

        result = await asyncio.to_thread(driver.execute_read, _query)

        if result is None:
            return {
                "node_data": None,
                "relationships": [],
                "adjacent_concepts": [],
                "navigation_hints": [f"No concept found with entity_id: {entity_id}"],
                "source": "neo4j_ontology",
            }

        return result

    except Exception as e:
        logger.error(f"Error retrieving concept details for entity_id {entity_id}: {e}")
        return {
            "node_data": None,
            "relationships": [],
            "adjacent_concepts": [],
            "navigation_hints": [f"Error retrieving concept details: {str(e)}"],
            "source": "neo4j_ontology_error",
        }


async def get_adjacent_concepts(entity_id: str, state: GraphState) -> Dict[str, Any]:
    """
    Deterministic Neo4j query to retrieve all adjacent concepts for an entity.

    Returns direct neighbors with relationship types and traversal instructions.
    This helps the LLM understand the connectivity and decide what concepts
    to explore to answer comparative questions.

    Args:
        entity_id: The entity_id to get adjacent concepts for
        state: Current pipeline state for context

    Returns:
        Dict containing:
        - adjacent_concepts: Full list of adjacent concept details
        - relation_summary: Count of different relationship types
        - traversal_options: Structured recommendations for next hops
        - source: "neo4j_ontology"
    """
    from app.dependencies import get_container

    try:
        driver = get_container().neo4j_driver
        if driver is None:
            raise RuntimeError("Neo4j driver unavailable")

        def _query(tx):
            cypher = """
            MATCH (n {entity_id: $entity_id})-[r]->(m)
            WHERE m.entity_id IS NOT NULL
            RETURN n.entity_id AS source, m.entity_id AS target, r.type AS relation_type, r.description AS relation_description, m.name AS target_name, m.type AS target_type
            """
            result = tx.run(cypher, entity_id=entity_id)

            adjacent_concepts = []
            relation_counts = {}

            for record in result:
                target_entity_id = record["target"]
                target_name = record["target_name"]
                target_type = record["target_type"]
                relation_type = record["relation_type"]
                relation_desc = record["relation_description"] or relation_type

                adj = {
                    "entity_id": target_entity_id,
                    "name": target_name,
                    "type": target_type,
                    "relation_type": relation_type,
                    "relation_description": relation_desc,
                    "navigation_hint": f"Follow '{relation_type}' from '{entity_id}' to '{target_name}'",
                }
                adjacent_concepts.append(adj)

                relation_type_key = relation_type
                relation_counts[relation_type_key] = relation_counts.get(relation_type_key, 0) + 1

            traversal_options = []

            # Prioritize by relation type diversity
            for rel_type, count in sorted(relation_counts.items(), key=lambda x: -x[1]):
                rel_concepts = [c for c in adjacent_concepts if c["relation_type"] == rel_type]
                if rel_concepts:
                    example = rel_concepts[0]
                    traversal_options.append({
                        "option": f"Explore {len(rel_concepts)} concepts via '{rel_type}'",
                        "examples": [
                            f"{example['name']} ({example['type']}) via {example['relation_type']}",
                        ],
                        "relation_type": rel_type,
                        "count": count,
                    })

            return {
                "adjacent_concepts": adjacent_concepts,
                "relation_summary": relation_counts,
                "traversal_options": traversal_options,
                "source": "neo4j_ontology",
            }

        result = await asyncio.to_thread(driver.execute_read, _query)
        return result

    except Exception as e:
        logger.error(f"Error retrieving adjacent concepts for entity_id {entity_id}: {e}")
        return {
            "adjacent_concepts": [],
            "relation_summary": {},
            "traversal_options": [f"Error retrieving adjacent concepts: {str(e)}"],
            "source": "neo4j_ontology_error",
        }


async def get_graph_traversal_context(state: GraphState) -> Dict[str, Any]:
    """
    Utility function to retrieve the current graph traversal context from state.

    Args:
        state: Current pipeline state

    Returns:
        Current graph traversal context or empty dict if not present
    """
    return {
        "traversed_concepts": state.get("graph_traversal_context", []),
        "traversal_step": state.get("graph_traversal_steps", 0),
        "traversal_done": state.get("graph_traversal_done", False),
        "start_concepts": state.get("graph_traversal_start_concepts", []),
    }