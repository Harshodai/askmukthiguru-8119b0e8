"""Short circuit query rewriting and fallback node handlers."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.tracing import trace_rag_node
from rag.states import GraphState
from rag.timeout_utils import get_node_timeout
from services.voice import register as voice_register

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
# The label is rarely the first thing the model says. Live 2026-09-15 trace:
# rewrite_query returned "Here is the rewritten query:\n\nConnect the fourth
# sacred secret..." -- the old pattern anchored on "rewritten query" at the very
# start, so nothing was stripped and the PREAMBLE became the search query. Worse,
# `original` is `state["rewritten_query"]`, so pass 2 prepended a second preamble
# to the first. That is the multi-hop failure: two poisoned retrieval passes,
# ~28s of LLM time, then the bare "I don't have that specific teaching".
_REWRITE_LABEL = re.compile(
    r"^\s*(?:(?:sure|certainly|okay|ok)\s*[,!.]?\s*)?"
    r"(?:here(?:'s| is)|below is|this is)?\s*"
    r"(?:the\s+|a\s+)?"
    r"(?:rewritten|revised|improved|reformulated)?\s*"
    r"(?:search\s+)?(?:query|question|version)\s*[:\-]\s*",
    re.IGNORECASE,
)

# A real search query against this corpus never talks about queries. If the
# label survived cleaning, the model wrapped its answer in prose we failed to
# parse -- searching for that text is strictly worse than searching the original.
_REWRITE_STILL_META = re.compile(
    r"\b(?:rewritten|reformulated|revised)\s+(?:search\s+)?quer(?:y|ies)\b", re.IGNORECASE
)


def _clean_rewrite(text: str) -> str:
    """Strip the model's chat wrapper off a rewritten query.

    Stripping repeats because the preambles stack: `rewrite_query` feeds
    `state["rewritten_query"]` back in as the next pass's input, so a wrapper
    that survived pass 1 gets a second one prepended in pass 2. Bounded at 3 --
    beyond that the output is prose, not a query, and `RewrittenQuery` rejects
    it so the seeker's original question is used instead.
    """
    cleaned = (text or "").strip().strip('"“”').strip()
    for _ in range(3):
        stripped = _REWRITE_LABEL.sub("", cleaned).strip().strip('"“”').strip()
        if stripped == cleaned:
            break
        cleaned = stripped
    return cleaned


class RewrittenQuery(BaseModel):
    """A CRAG rewrite that is safe to hand to the retriever.

    The rules used to be an inline `if not x or len(x) < 5 or "error" in x`
    chain, which is exactly the shape that grows a new clause per incident and
    never gets one removed. As a model they are declarative, individually
    named in the error, and testable without going through the node.

    Construction failing is the normal, expected outcome for a bad rewrite --
    `rewrite_query` catches `ValidationError` and reuses the seeker's original
    question, which is always a valid query.
    """

    model_config = ConfigDict(frozen=True)

    # 1000 chars is well past any real search query; beyond it the model is
    # answering the question rather than rewriting it.
    text: str = Field(min_length=5, max_length=1000)

    @field_validator("text", mode="before")
    @classmethod
    def _strip_chat_wrapper(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("rewrite must be a string")
        return _clean_rewrite(value)

    @field_validator("text")
    @classmethod
    def _reject_meta_language(cls, value: str) -> str:
        """A search query against this corpus never talks about queries.

        If the label survived stripping, the model wrapped its output in prose
        we could not parse; searching for that text is strictly worse than
        searching the seeker's own words.
        """
        if _REWRITE_STILL_META.search(value):
            raise ValueError("rewrite still contains query-meta language")
        return value

    @field_validator("text")
    @classmethod
    def _reject_provider_error_text(cls, value: str) -> str:
        """Providers return their failures as prose, not exceptions."""
        if "error" in value.lower():
            raise ValueError("rewrite looks like a provider error message")
        return value


@trace_rag_node("regenerate_gate")
@log_metrics
async def regenerate_gate(state: GraphState, config: dict = None) -> dict:
    """Opt-in cheap correction: consume one rewrite attempt without re-retrieving.

    A pure faithfulness/persona failure on documents `grade_documents` already
    judged relevant is a generation problem (Self-RAG territory), not a
    retrieval problem (CRAG territory) -- see settings.rag_regenerate_before_rewrite
    docstring in app/config.py. This node exists only to increment
    `rewrite_count` against the same budget rewrite_query would have consumed,
    so total worst-case attempts across a request are unchanged; the actual
    retry happens because this edges straight back to generate_answer with
    the context already engineered, instead of through retrieve_documents.
    """
    rewrite_count = state.get("rewrite_count", 0) + 1
    await emit_status(config, "Reconsidering the answer for faithfulness...")
    logger.info(
        f"Self-RAG regenerate (attempt {rewrite_count}): retrying generation on "
        "already-graded context instead of re-retrieving"
    )
    return {"rewrite_count": rewrite_count}


@trace_rag_node("rewrite_query")
@log_metrics
async def rewrite_query(state: GraphState, config: dict = None) -> dict:
    """CRAG: Self-correcting query rewrite."""
    rewrite_count = state.get("rewrite_count", 0) + 1
    original = state.get("rewritten_query") or state["question"]

    await emit_status(config, "Rephrasing the question for better retrieval...")
    t_out = get_node_timeout("default_fast", 30.0)
    _gateway = getattr(_services, "_llm_gateway", None)
    if _gateway is not None and hasattr(_gateway, "generate"):
        from rag.prompts import QUERY_REWRITE_PROMPT

        _rewrite_user = f"Original query: {original}"
        _reasons = state.get("grading_reasons", [])
        if _reasons:
            _rewrite_user += "\n\nReasons for previous retrieval failure:\n" + "\n".join(
                f"- {r}" for r in _reasons if r
            )
        rewritten = await _gateway.generate(
            system_prompt=QUERY_REWRITE_PROMPT,
            user_prompt=_rewrite_user,
            task="rewrite",
            operation="rewrite_query",
        )
    else:
        # Gateway missing (standalone/offline) — direct provider fallback only.
        rewritten = await _services._ollama.rewrite_query(
            original=original, reasons=state.get("grading_reasons", []), timeout=t_out
        )
    try:
        rewritten = RewrittenQuery(text=rewritten).text
    except ValidationError as exc:
        reasons = "; ".join(e["msg"] for e in exc.errors())
        logger.warning(
            "CRAG: rewrite rejected (%s); reusing the original query %r",
            reasons,
            original[:80],
        )
        rewritten = original
    else:
        logger.info(f"CRAG rewrite #{rewrite_count}: {original[:50]}... -> {rewritten[:50]}...")

    return {
        "rewritten_query": rewritten,
        "rewrite_count": rewrite_count,
    }


@trace_rag_node("handle_fallback")
@log_metrics
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
            "route_decision": "limited_comparison_fallback",
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
                "route_decision": "reflective_fallback",
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
                "route_decision": "grounded_partial_evidence",
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
        logger.warning(
            "Terminal grounded-partial fallback unavailable; using canonical fallback: %s", exc
        )

    return {
        # One voice across every refusal surface (services/voice/register.py).
        "final_answer": voice_register.FALLBACK_RESPONSE,
        "route_decision": "no_context_short_circuit",
        "verification": {
            "passed": False,
            "method": "no_context_short_circuit",
            "citations_verified": True,
        },
        "faithfulness_score": 0.0,
        "confidence_score": 0.0,
        "is_faithful": False,
        "_needs_retry": False,
    }
