"""
Mukthi Guru — Reasoning-Based Tree Navigation
(Inspired by PageIndex's reasoning-driven retrieval)

Instead of blindly vector-searching ALL chunks, this module lets the LLM
examine the RAPTOR level-1 summary nodes first and REASON about which
topic clusters are most relevant to the user's question.

This creates a "Table of Contents" effect:
1. LLM reads the cluster summaries (like a ToC)
2. LLM picks the most relevant clusters (reasoning, not similarity)
3. Vector search is scoped to those clusters only

After retrieval, a sufficiency check asks the LLM if the context is
enough to answer well. If not, the search widens to additional clusters.
"""

import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)


async def navigate_tree(
    query: str,
    summary_nodes: list[dict],
    llm,
    max_clusters: int = 3,
) -> list[int]:
    """
    Reasoning-based tree navigation over RAPTOR summary nodes.

    The LLM examines each summary and reasons about which topic clusters
    are most likely to contain the answer — just like a human would scan
    a table of contents before diving into a book.

    Args:
        query: The user's question
        summary_nodes: List of dicts with 'cluster_id', 'text', 'topic_label', 'titles'
        llm: OllamaService instance
        max_clusters: Maximum clusters to select

    Returns:
        List of cluster_ids to search within
    """
    if not summary_nodes:
        logger.warning("Tree navigation: No summary nodes available, skipping")
        return []

    if len(summary_nodes) <= max_clusters:
        # Fewer summaries than max — search all
        return [s["cluster_id"] for s in summary_nodes]

    # Build the "Table of Contents" for the LLM
    toc_entries = []
    for s in summary_nodes:
        topic = s.get("topic_label", "")
        titles = ", ".join(s.get("titles", [])[:3])
        entry = f"[Cluster {s['cluster_id']}]"
        if topic:
            entry += f" Topic: {topic}"
        if titles:
            entry += f" | Sources: {titles}"
        entry += f"\nSummary: {s['text'][:300]}"
        toc_entries.append(entry)

    toc_text = "\n\n".join(toc_entries)

    from rag.prompts import TREE_NAVIGATION_PROMPT

    prompt = (
        f"User Question: {query}\n\n"
        f"Knowledge Base Table of Contents ({len(summary_nodes)} sections):\n\n"
        f"{toc_text}\n\n"
        f"Select up to {max_clusters} clusters."
    )

    try:
        result = await llm._generate_fast(TREE_NAVIGATION_PROMPT, prompt)

        # Parse cluster IDs from the response
        selected = _parse_cluster_ids(result, summary_nodes)

        if not selected:
            # Fallback: return all clusters if parsing fails
            logger.warning("Tree navigation: Could not parse cluster IDs, using all")
            return [s["cluster_id"] for s in summary_nodes]

        logger.info(
            f"Tree navigation: selected clusters {selected} "
            f"from {len(summary_nodes)} total"
        )
        return selected[:max_clusters]

    except Exception as e:
        logger.error(f"Tree navigation failed: {e}")
        return [s["cluster_id"] for s in summary_nodes]


async def check_sufficiency(
    query: str,
    context: str,
    llm,
) -> dict:
    """
    Iterative sufficiency check — PageIndex's key to high accuracy.

    After retrieval, asks the LLM: "Do you have enough context to
    answer this question well?" If not, the pipeline should widen
    the search to additional clusters.

    Returns:
        Dict with 'sufficient' (bool) and 'reason' (str)
    """
    from rag.prompts import SUFFICIENCY_CHECK_PROMPT

    prompt = (
        f"Question: {query}\n\n"
        f"Retrieved Context:\n{context[:3000]}"  # Truncate for efficiency
    )

    try:
        result = await llm._generate_fast(SUFFICIENCY_CHECK_PROMPT, prompt)
        result_upper = result.upper().strip()

        sufficient = "SUFFICIENT" in result_upper and "INSUFFICIENT" not in result_upper

        logger.info(
            f"Sufficiency check: {'SUFFICIENT' if sufficient else 'INSUFFICIENT'}"
        )
        return {"sufficient": sufficient, "reason": result.strip()}

    except Exception as e:
        logger.error(f"Sufficiency check failed: {e}")
        # Assume sufficient on failure to avoid infinite loops
        return {"sufficient": True, "reason": f"Check failed: {e}"}


def _parse_cluster_ids(response: str, summary_nodes: list[dict]) -> list[int]:
    """
    Parse cluster IDs from LLM response.

    Handles formats like:
    - "Clusters: 1, 3, 5"
    - "1, 2, 3"
    - "[1, 3]"
    - "Cluster 1\nCluster 3"
    """
    import re

    valid_ids = {s["cluster_id"] for s in summary_nodes}

    # Try JSON array first
    try:
        parsed = json.loads(response)
        if isinstance(parsed, list):
            return [int(x) for x in parsed if int(x) in valid_ids]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Extract all numbers from the response
    numbers = re.findall(r'\b(\d+)\b', response)
    selected = []
    for n in numbers:
        cid = int(n)
        if cid in valid_ids and cid not in selected:
            selected.append(cid)

    return selected
