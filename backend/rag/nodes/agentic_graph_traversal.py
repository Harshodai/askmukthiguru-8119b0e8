"""Agentic Graph Traversal Node for COMPARATIVE Intent and tier3_complex queries.

This node implements a ReAct (Reasoning + Acting) loop that enables the LLM to
iteratively traverse the ontology graph to gather sufficient context for
comparative or complex questions about spiritual concepts.

Key Features:
- Deterministic Neo4j queries exposed as tools for the LLM
- Tool responses include structured next-step hints and navigation advice
- Maximum 3 traversal steps to prevent runaway latency
- Only triggers for COMPARATIVE intent or tier3_complex query tiers
- Contextual awareness: starts from doctrine tags or initial retrieval
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Annotated

from app.config import settings
from rag.prompts import AGENTIC_TRAVERSAL_SYSTEM_PROMPT
from rag.states import GraphState
from .tools import get_concept_details, get_adjacent_concepts, get_graph_traversal_context

logger = logging.getLogger(__name__)

# Fast model settings for traversal decisions
FAST_MODEL_TIMEOUT = getattr(settings, "agentic_graph_timeout_per_step", 15)
FAST_MODEL_NAME = getattr(settings, "agentic_graph_fast_model", "nim:meta/llama-3.1-8b-instruct")
MAX_STEPS = getattr(settings, "agentic_graph_max_steps", 3)
ENABLED = getattr(settings, "agentic_graph_traversal_enabled", True)


async def agentic_graph_traversal(state: GraphState, config: dict = None) -> dict:
    """
    ReAct loop for walking the ontology graph during COMPARATIVE intent or complex queries.

    Steps:
    1. Initialize: Extract starting concepts from doctrine tags or initial retrieval
    2. THINK: LLM analyzes current graph context and decides next traversal step
    3. ACT: LLM calls get_concept_details or get_adjacent_concepts tools
    4. OBSERVE: Parse tool response (which includes navigation_hints)
    5. Repeat until DONE, no candidates, or max steps reached
    """
    if not ENABLED:
        return {}

    intent = state.get("intent", "")
    query_tier = state.get("query_tier", "")

    # Only trigger for COMPARATIVE intent or tier3_complex
    if intent != "COMPARATIVE" and query_tier != "tier3_complex":
        return {}

    request_id = state.get("request_id")
    log_extra = {"request_id": request_id} if request_id else {}
    logger.info(
        f"Starting Agentic Graph Traversal for intent={intent}, tier={query_tier}",
        extra=log_extra,
    )

    # Initialize traversal context from state
    traversal_context = state.get("graph_traversal_context", [])
    current_step = 0
    max_steps = MAX_STEPS

    # If no traversal context yet, extract from doctrine tags or initial retrieval
    if not traversal_context:
        try:
            from ingest.pipeline import extract_doctrine_tags

            # First, check if we have doctrine tags in state
            if "graph_traversal_start_concepts" in state:
                start_concepts = state.get("graph_traversal_start_concepts", [])
            else:
                # Extract from query using existing pipeline function
                start_concepts = extract_doctrine_tags(state.get("question", ""))

            # Fallback: if no start concepts found, extract entity concepts from initial retrieval docs
            if not start_concepts:
                start_concepts = _extract_concepts_from_docs(state.get("relevant_docs", []))

            if start_concepts:
                for concept_id in start_concepts[:3]:  # Limit to top 3 concepts
                    if current_step >= max_steps:
                        break
                    concept_result = await get_concept_details(concept_id, state)
                    current_step += 1

                    if concept_result.get("node_data"):
                        traversal_context.append({
                            "concept_id": concept_id,
                            "node_data": concept_result["node_data"],
                            "step": current_step,
                            "reasoning": f"Starting concept from doctrine tags",
                        })

                    if current_step < max_steps:
                        adj_result = await get_adjacent_concepts(concept_id, state)
                        current_step += 1
                        traversal_context.append({
                            "concept_id": f"adjacent_to_{concept_id}",
                            "adjacent_concepts": adj_result["adjacent_concepts"],
                            "relation_summary": adj_result["relation_summary"],
                            "step": current_step,
                            "reasoning": f"Initial connectivity exploration from {concept_id}",
                        })

        except Exception as e:
            logger.warning(f"Failed to initialize graph traversal: {e}", extra={"request_id": request_id} if request_id else {})
            return {
                "graph_traversal_error": f"Initialization failed: {str(e)}",
                "graph_traversal_context": [],
            }

    # ReAct loop
    while current_step < max_steps:
        logger.debug(
            f"[Agentic Graph Traversal] Step {current_step + 1}/{max_steps}"
        )

        # Prepare context for LLM decision making
        context_summary = _prepare_context_summary(traversal_context)

        # Ask LLM what to do next
        next_action = await _ask_llm_to_decide(
            state.get("question", ""),
            context_summary,
            current_step,
            max_steps,
            request_id=request_id,
        )

        if next_action.get("action") == "DONE":
            logger.info(
                f"Agentic Graph Traversal completed at step {current_step + 1}"
            )
            break

        if next_action.get("action") == "STOP":
            logger.info("Agentic Graph Traversal stopped by LLM")
            break

        # Execute the action
        try:
            action_result = await _execute_traversal_action(
                next_action, state, current_step, request_id=request_id
            )

            if action_result:
                traversal_context.extend(action_result["context_chunks"])
            else:
                logger.warning(
                    f"Agentic Graph Traversal: Action {next_action} returned no result",
                    extra={"request_id": request_id} if request_id else {},
                )
                break

            current_step += 1

        except Exception as e:
            logger.error(f"Error in Agentic Graph Traversal action: {e}", extra={"request_id": request_id} if request_id else {})
            break

    # Mark traversal as complete if we exited normally
    result = {
        "graph_traversal_context": traversal_context,
        "graph_traversal_steps": current_step,
        "graph_traversal_done": next_action.get("done", False) if "next_action" in locals() else False,
    }

    # Add to relevant_docs if we have meaningful traversal data
    if traversal_context and _has_meaningful_traversal(traversal_context):
        traversal_doc = _format_traversal_as_document(traversal_context)

        # rerank_documents (the very next node) reads state["documents"], not
        # state["relevant_docs"] — and grade_documents (after that) always
        # overwrites relevant_docs from its own grading pass regardless of
        # what's here. Without also writing "documents", the traversal doc
        # is silently discarded before generation ever sees it. Write both:
        # "documents" so it actually flows through reranking + CRAG grading
        # like every other candidate (correctly gradeable, not force-injected
        # ungraded), and "relevant_docs" too as a harmless fallback in case
        # grading is ever bypassed for this tier.
        existing_docs = state.get("documents") or state.get("relevant_docs", [])
        result["documents"] = [traversal_doc] + existing_docs
        result["relevant_docs"] = [traversal_doc] + state.get("relevant_docs", [])

    return result


def _prepare_context_summary(traversal_context: List[Dict]) -> Dict[str, Any]:
    """Prepare a concise summary of current traversal state for the LLM."""
    if not traversal_context:
        return {
            "traversal_summary": "Starting traversal from scratch",
            "concepts_found": [],
            "connections": [],
            "completed_steps": 0,
        }

    # Aggregate all traversed concepts
    traversed_concepts = []
    connections = []

    for chunk in traversal_context:
        if "node_data" in chunk:
            node = chunk["node_data"]
            traversed_concepts.append(
                {
                    "entity_id": node.get("entity_id"),
                    "name": node.get("name"),
                    "type": node.get("type"),
                    "description": node.get("description", ""),
                }
            )
        elif "adjacent_concepts" in chunk:
            for adj in chunk["adjacent_concepts"]:
                connections.append(
                    {
                        "source": chunk.get("concept_id", "unknown"),
                        "target": adj.get("entity_id", "unknown"),
                        "relation": adj.get("relation_type", "unknown"),
                        "description": adj.get("relation_description", ""),
                    }
                )

    return {
        "traversal_summary": f"Traversed {len(traversed_concepts)} concepts and {len(connections)} connections",
        "concepts_found": traversed_concepts,
        "connections": connections,
        "completed_steps": len(set(chunk.get("step", 0) for chunk in traversal_context)),
    }


async def _ask_llm_to_decide(
    question: str,
    context_summary: Dict,
    step: int,
    max_steps: int,
    *,
    request_id: str | None = None,
) -> Dict[str, Any]:
    """Ask the fast model to decide what to do next in the traversal."""
    try:
        from services.ollama_service import OllamaService

        ollama = OllamaService()

        # Build actual entity IDs from traversed context, not just counts.
        traversed_ids = [
            c.get("entity_id") for c in context_summary.get("concepts_found", [])
        ]
        candidate_ids = [eid for eid in traversed_ids if eid] or ["none yet"]
        candidate_concepts = "\n".join(f"- {eid}" for eid in candidate_ids)

        system_prompt = AGENTIC_TRAVERSAL_SYSTEM_PROMPT.format(
            step=step + 1,
            max_steps=max_steps,
            traversal_summary=context_summary.get(
                "traversal_summary", "Starting traversal from scratch"
            ),
            question=question,
            candidate_concepts=candidate_concepts,
        )

        user_prompt = (
            f"Already traversed concept IDs: {', '.join(candidate_ids)}\n"
            f"Need to answer: {question}\n\n"
            "What should we do next? Return ONLY a JSON object with 'action', 'entity_id', and 'reasoning'."
        )

        response = await ollama._generate_fast(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout=FAST_MODEL_TIMEOUT,
            max_retries=1,
            model=FAST_MODEL_NAME,
            metadata={"request_id": request_id} if request_id else None,
        )

        # Parse response
        return _parse_llm_traversal_decision(response, context_summary)

    except Exception as e:
        logger.error(
            f"Error asking LLM to decide traversal: {e}",
            extra={"request_id": request_id} if request_id else {},
        )
        return {
            "action": "STOP",
            "reasoning": f"Failed to get LLM decision: {str(e)}",
        }


def _parse_llm_traversal_decision(response: str, context_summary: Dict) -> Dict[str, Any]:
    """Parse the LLM's traversal decision from its response.

    Prefer a strict JSON response. Fall back to heuristic text matching for
    non-JSON outputs. Entity IDs are case-preserving so Neo4j lookups keep
    their casing.
    """
    import json
    import re

    raw = (response or "").strip()

    # 1. Try strict JSON first.
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            action = (parsed.get("action") or "").upper()
            if action in {"EXPLORE", "NAVIGATE", "DONE", "STOP"}:
                return {
                    "action": action,
                    "entity_id": parsed.get("entity_id"),
                    "reasoning": parsed.get("reasoning") or response,
                    "done": action in {"DONE", "STOP"} and (parsed.get("done") is not False),
                }
    except json.JSONDecodeError:
        pass

    lowered = raw.lower()
    action = "STOP"
    entity_id = None
    reasoning = ""

    # 2. Heuristic fallback for non-JSON responses.
    if "done" in lowered:
        return {
            "action": "DONE",
            "reasoning": "LLM decided to stop traversal",
            "done": True,
        }

    if "stop" in lowered:
        return {
            "action": "STOP",
            "reasoning": "LLM decided to stop traversal",
            "done": False,
        }

    if "explore" in lowered or "look at" in lowered:
        action = "EXPLORE"
    elif "navigate" in lowered or "follow" in lowered:
        action = "NAVIGATE"
    else:
        action = "STOP"
        reasoning = f"Unclear action in LLM response: {raw[:100]}"

    # Extract entity_id - case-preserving so graph ids keep their casing
    entity_match = re.search(
        r"(?:explore|navigate|follow)\s+(?:concept\s+)?([A-Za-z][A-Za-z\s'\-]+?)(?:\s|$|,|\.|\"|\')",
        raw,
    )
    if entity_match:
        entity_id = entity_match.group(1).strip()

    # Quoted entities take precedence (also case-preserving)
    quoted_match = re.search(r'"([^"]+)"', raw)
    if quoted_match:
        entity_id = quoted_match.group(1).strip()

    # If no entity_id found, use the first concept from context if available
    if not entity_id:
        concepts = context_summary.get("concepts_found", [])
        if concepts:
            entity_id = concepts[0].get("entity_id")
        else:
            entity_id = "unknown"

    return {
        "action": action,
        "entity_id": entity_id,
        "reasoning": response if not reasoning else reasoning,
        "done": action == "DONE",
    }


async def _execute_traversal_action(
    action: Dict[str, Any],
    state: GraphState,
    step: int,
    *,
    request_id: str | None = None,
) -> Optional[Dict[str, Any]]:
    """Execute the LLM-decided traversal action."""
    action_name = action.get("action")
    entity_id = action.get("entity_id")
    reasoning = action.get("reasoning", "")

    try:
        if action_name == "EXPLORE":
            # Get concept details
            result = await get_concept_details(entity_id, state)

            context_chunks = []
            if result.get("node_data"):
                context_chunks.append({
                    "concept_id": entity_id,
                    "node_data": result["node_data"],
                    "navigation_hints": result.get("navigation_hints", []),
                    "step": step,
                    "reasoning": f"Explored concept '{entity_id}' per request: {reasoning}",
                })

            return {"context_chunks": context_chunks}

        elif action_name == "NAVIGATE":
            # Get adjacent concepts
            result = await get_adjacent_concepts(entity_id, state)

            context_chunks = []
            context_chunks.append({
                "concept_id": entity_id,
                "adjacent_concepts": result["adjacent_concepts"],
                "relation_summary": result["relation_summary"],
                "traversal_options": result["traversal_options"],
                "step": step,
                "reasoning": f"Navigated from '{entity_id}' to explore connections: {reasoning}",
            })

            return {"context_chunks": context_chunks}

        elif action_name == "DONE":
            return {"context_chunks": [], "done": True}

        elif action_name == "STOP":
            return {"context_chunks": [], "done": False}

        else:
            logger.error(f"Unknown traversal action: {action_name}")
            return {"context_chunks": [], "done": False}

    except Exception as e:
        logger.error(
            f"Error executing traversal action {action_name} for {entity_id}: {e}",
            extra={"request_id": request_id} if request_id else {},
        )
        return None


def _extract_concepts_from_docs(docs: List[Dict]) -> List[str]:
    """Extract likely ontology entity concepts from relevant docs as fallback."""
    concepts: set[str] = set()
    for doc in docs:
        text = doc.get("text") or ""
        # Look for bolded/mentioned concepts and explicit entity IDs in metadata.
        for candidate in doc.get("metadata", {}).get("concepts", []) or []:
            if isinstance(candidate, str):
                concepts.add(candidate.strip())
        # Simple pattern for **Concept Name** mentions.
        import re
        for match in re.finditer(r"\*\*([A-Z][A-Za-z\s'-]{2,40})\*\*", text):
            concepts.add(match.group(1).strip())
    return list(concepts)[:5]


def _has_meaningful_traversal(traversal_context: List[Dict]) -> bool:
    """Check if the traversal yielded meaningful data for answering the question."""
    if not traversal_context:
        return False

    # Consider meaningful if we have concept details or meaningful connections
    has_node_data = any("node_data" in chunk for chunk in traversal_context)
    has_relationships = any(
        "adjacent_concepts" in chunk and chunk["adjacent_concepts"]
        for chunk in traversal_context
    )

    return has_node_data or has_relationships


def _format_traversal_as_document(traversal_context: List[Dict]) -> Dict[str, Any]:
    """Format the traversal context as a structured document for inclusion in relevant_docs."""
    if not traversal_context:
        return {}

    # Extract all traversed concepts and their relationships
    traversed_concepts = []
    all_relationships = []

    for chunk in traversal_context:
        if "node_data" in chunk:
            node = chunk["node_data"]
            traversed_concepts.append(
                {
                    "entity_id": node.get("entity_id", ""),
                    "name": node.get("name", ""),
                    "type": node.get("type", ""),
                    "description": node.get("description", ""),
                    "properties": node.get("properties", {}),
                }
            )

        if "adjacent_concepts" in chunk:
            for adj in chunk["adjacent_concepts"]:
                all_relationships.append(
                    {
                        "source": chunk.get("concept_id", ""),
                        "target": adj.get("entity_id", ""),
                        "target_name": adj.get("name", ""),
                        "relation_type": adj.get("relation_type", ""),
                        "relation_description": adj.get("relation_description", ""),
                    }
                )

    # Create a structured document
    content_lines = []
    content_lines.append("## Graph Traversal Context")
    content_lines.append("")
    content_lines.append(f"Retrieved {len(traversed_concepts)} spiritual concepts and {len(all_relationships)} relationships.")
    content_lines.append("")

    # Add concepts with proper formatting
    content_lines.append("### Concepts Explored")
    for concept in traversed_concepts:
        content_lines.append(f"- **{concept.get('name', 'Unknown')}** ({concept.get('type', 'Unknown')})")
        content_lines.append(f"  Entity ID: {concept.get('entity_id', '')}")
        content_lines.append(f"  Description: {concept.get('description', '')}")
        if concept.get("properties"):
            content_lines.append(f"  Properties: {concept.get('properties')}")
        content_lines.append("")

    # Add relationships
    if all_relationships:
        content_lines.append("### Relationships Discovered")
        for rel in all_relationships:
            content_lines.append(
                f"- **{rel.get('source', 'Unknown')}** → **{rel.get('target_name', 'Unknown')}** via _{rel.get('relation_type', 'Unknown')}_"
            )
            content_lines.append(f"  Description: {rel.get('relation_description', '')}")

    content = "\n".join(content_lines)

    return {
        "text": content,
        "score": 0.95,  # High score since this is direct graph traversal
        "title": "Agentic Graph Traversal Context",
        "source": "neo4j_agentic_traversal",
        "content_type": "graph_traversal",
        "metadata": {
            "traversal_step": len(set(chunk.get("step", 0) for chunk in traversal_context)),
            "concepts_traversed": len(traversed_concepts),
            "relationships_discovered": len(all_relationships),
            "traversal_timestamp": ""  # Will be filled by pipeline
        },
    }