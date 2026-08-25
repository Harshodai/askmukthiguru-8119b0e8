"""Short circuit query rewriting and fallback node handlers."""

from __future__ import annotations

import logging
import re

from app.tracing import trace_rag_node
from rag.states import GraphState
from rag.timeout_utils import get_node_timeout

from . import _services
from .utils import emit_status, log_metrics

logger = logging.getLogger(__name__)

_COMPARISON_TERMS = ("difference between", "compare", "versus", " vs ", " vs.")


def _is_simple_meditation_comparison_request(question: str) -> bool:
    lowered = " ".join(str(question or "").casefold().split())
    return bool(
        any(term in lowered for term in _COMPARISON_TERMS)
        and "meditation" in lowered
        and "contemplation" in lowered
        and len(lowered) <= 180
    )


def _simple_meditation_comparison_fallback() -> str:
    return (
        "Here is a general distinction, not a quoted teaching: meditation usually "
        "emphasizes stabilizing attention, while contemplation usually emphasizes "
        "sustained inquiry or reflection on a theme. They can overlap—meditation "
        "steadies the mind, and contemplation examines what becomes clear. I could "
        "not verify a direct teaching on this comparison from the retrieved sources."
    )

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
    rewritten = await ollama.rewrite_query(
        original=original, reasons=state.get("grading_reasons", []), timeout=t_out
    )
    rewritten = _clean_rewrite(rewritten)
    if not rewritten or len(rewritten.strip()) < 5 or "error" in rewritten.lower():
        logger.warning(
            f"CRAG: Rewritten query '{rewritten}' is invalid/empty, falling back to original query '{original}'"
        )
        rewritten = original
    else:
        logger.info(f"CRAG rewrite #{rewrite_count}: {original[:50]}... -> {rewritten[:50]}...")

    return {
        "rewritten_query": rewritten,
        "rewrite_count": rewrite_count,
    }


@trace_rag_node("handle_fallback")
async def handle_fallback(state: GraphState, config: dict = None) -> dict:
    """Return a bounded, honest fallback without discarding safe general help."""
    await emit_status(config, "Preparing a graceful response...")
    if _is_simple_meditation_comparison_request(state.get("question", "")):
        logger.info(
            "Terminal fallback: replacing simple meditation comparison refusal with limited-support explanation"
        )
        return {
            "final_answer": _simple_meditation_comparison_fallback(),
            "citations": [],
            "verification": {
                "passed": False,
                "method": "limited_comparison_fallback",
                "citations_verified": True,
            },
            "faithfulness_score": 0.0,
            "confidence_score": 0.0,
            "is_faithful": False,
            "_needs_retry": False,
        }

    # Keep the terminal route consistent with format_final_answer: a narrow
    # general peace question gets a useful, explicitly non-doctrinal reflection
    # even when retrieval/CRAG exhausted before the formatter ran.
    try:
        from rag.nodes.generation import (
            _generic_peace_meaning_fallback,
            _generic_peace_meaning_request,
        )

        if _generic_peace_meaning_request(state.get("question", "")):
            logger.info(
                "Terminal fallback: replacing no-evidence peace meaning refusal with bounded reflection"
            )
            return {
                "final_answer": _generic_peace_meaning_fallback(),
                "citations": [],
                "verification": {
                    "passed": False,
                    "method": "reflective_peace_meaning_fallback",
                    "citations_verified": True,
                },
                "faithfulness_score": 0.0,
                "confidence_score": 0.0,
                "is_faithful": False,
                "_needs_retry": False,
            }
    except Exception as exc:
        logger.warning("Terminal peace fallback unavailable; using canonical fallback: %s", exc)

    # CRAG exhausted its rewrite budget without relevant_docs clearing the
    # grading bar, but retrieval did find candidates — reranked_docs/documents
    # still hold them even though relevant_docs (the post-grade filtered set)
    # is empty here. generate_answer already falls back to a grounded partial
    # answer when a generated draft fails verification post-hoc; this path is
    # the other terminal route into the same bare-refusal state and had no
    # equivalent safety valve, so a real retrieved-evidence miss produced a
    # generic refusal instead of the excerpts that were actually found.
    try:
        from rag.nodes.generation import _grounded_partial_answer

        candidate_docs = state.get("reranked_docs") or state.get("documents") or []
        partial = _grounded_partial_answer(candidate_docs) if candidate_docs else None
        if partial:
            partial_answer, partial_citations = partial
            logger.info(
                "Terminal fallback: replacing bare refusal with grounded partial from %d candidate doc(s)",
                len(candidate_docs),
            )
            return {
                "final_answer": partial_answer,
                "citations": partial_citations,
                "verification": {
                    "passed": False,
                    "method": "grounded_partial_fallback",
                    "citations_verified": True,
                },
                "faithfulness_score": 0.0,
                "confidence_score": 0.0,
                "is_faithful": False,
                "_needs_retry": False,
            }
    except Exception as exc:
        logger.warning("Terminal grounded-partial fallback unavailable; using canonical fallback: %s", exc)

    return {
        "final_answer": "I don't have that specific teaching. Please try asking another question."
    }
