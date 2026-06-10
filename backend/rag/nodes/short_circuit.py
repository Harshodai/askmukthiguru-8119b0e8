"""Short circuit query rewriting and fallback node handlers."""

from __future__ import annotations

import logging

from rag.states import GraphState
from rag.timeout_utils import get_node_timeout

from . import _services
from .utils import emit_status, log_metrics

logger = logging.getLogger(__name__)


@log_metrics
async def rewrite_query(state: GraphState, config: dict = None) -> dict:
    """CRAG: Self-correcting query rewrite."""
    rewrite_count = state.get("rewrite_count", 0) + 1
    original = state.get("rewritten_query") or state["question"]
    ollama = _services._ollama

    await emit_status(config, "Rephrasing the question for better retrieval...")
    t_out = get_node_timeout("default_fast", 30.0)
    rewritten = await ollama.rewrite_query(original=original, reasons=state.get("grading_reasons", []), timeout=t_out)
    logger.info(f"CRAG rewrite #{rewrite_count}: {original[:50]}... -> {rewritten[:50]}...")

    return {
        "rewritten_query": rewritten,
        "rewrite_count": rewrite_count,
    }


async def handle_fallback(state: GraphState, config: dict = None) -> dict:
    """Return the graceful fallback response."""
    await emit_status(config, "Preparing a graceful response...")
    return {
        "final_answer": "I don't have that specific teaching. Please try asking another question."
    }
