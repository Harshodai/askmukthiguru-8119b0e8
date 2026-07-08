"""Short circuit query rewriting and fallback node handlers."""

from __future__ import annotations

import logging
import re

from rag.states import GraphState
from rag.timeout_utils import get_node_timeout

from app.tracing import trace_rag_node
from . import _services
from .utils import emit_status, log_metrics

logger = logging.getLogger(__name__)

# LLM rewriters often prefix their own label ("Rewritten query: ...").  Left
# unstripped, rewrite #2 operates on rewrite #1's label and the query degrades
# into keyword soup — strip label, surrounding quotes, and leading newlines.
_REWRITE_LABEL = re.compile(r"^\s*(?:rewritten\s+query|rewrite|query)\s*[:\-]\s*", re.IGNORECASE)


def _clean_rewrite(text: str) -> str:
    cleaned = (text or "").strip().strip('"“”').strip()
    cleaned = _REWRITE_LABEL.sub("", cleaned).strip().strip('"“”').strip()
    return cleaned


@trace_rag_node("rewrite_query")
@log_metrics
async def rewrite_query(state: GraphState, config: dict = None) -> dict:
    """CRAG: Self-correcting query rewrite."""
    rewrite_count = state.get("rewrite_count", 0) + 1
    original = state.get("rewritten_query") or state["question"]
    ollama = _services._ollama

    await emit_status(config, "Rephrasing the question for better retrieval...")
    t_out = get_node_timeout("default_fast", 30.0)
    rewritten = await ollama.rewrite_query(original=original, reasons=state.get("grading_reasons", []), timeout=t_out)
    rewritten = _clean_rewrite(rewritten)
    if not rewritten or len(rewritten.strip()) < 5 or "error" in rewritten.lower():
        logger.warning(f"CRAG: Rewritten query '{rewritten}' is invalid/empty, falling back to original query '{original}'")
        rewritten = original
    else:
        logger.info(f"CRAG rewrite #{rewrite_count}: {original[:50]}... -> {rewritten[:50]}...")

    return {
        "rewritten_query": rewritten,
        "rewrite_count": rewrite_count,
    }


@trace_rag_node("handle_fallback")
async def handle_fallback(state: GraphState, config: dict = None) -> dict:
    """Return the graceful fallback response."""
    await emit_status(config, "Preparing a graceful response...")
    return {
        "final_answer": "I don't have that specific teaching. Please try asking another question."
    }
