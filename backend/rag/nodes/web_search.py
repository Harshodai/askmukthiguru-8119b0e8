"""Web Search node for real-time / temporal queries."""

from __future__ import annotations

import logging

from rag.states import GraphState

logger = logging.getLogger(__name__)


async def web_search_node(state: GraphState, config: dict = None) -> dict:
    """
    Fetch real-time web results for temporal queries.

    This node runs in parallel with retrieve_documents when needs_web_search=True.
    Results are formatted as document dicts and will be merged downstream.
    """
    from rag.nodes import _services

    web_search_service = getattr(_services, "_web_search", None)
    if web_search_service is None:
        logger.debug("WebSearchService not available, skipping web search")
        return {"web_search_results": []}

    question = state.get("rewritten_query") or state["question"]
    user_id = state.get("user_id")

    try:
        results = await web_search_service.search(question, user_id=user_id)
    except Exception as exc:
        logger.warning(f"Web search node failed: {exc}")
        results = []

    return {"web_search_results": results}
