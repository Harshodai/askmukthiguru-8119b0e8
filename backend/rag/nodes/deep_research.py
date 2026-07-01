"""RAGFlow Gap 1 — Deep Research (recursive sufficiency retrieval).

Loops: judge gathered context → if insufficient, fire complementary queries via
retrieve_for_single_query → dedupe → recurse up to settings.rag_deep_research_max_depth.
Auto-fires for tier3_complex + standard intent; opt-in for others.

ponytail: reuses retrieve_for_single_query + _services accessors; no new retrieval code.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.config import settings
from rag.nodes import _services
from rag.nodes.retrieval import retrieve_for_single_query
from rag.prompts.deep_research_prompts import (
    SUFFICIENCY_CHECK_SYSTEM,
    SUFFICIENCY_CHECK_USER,
)
from rag.timeout_utils import get_node_timeout

logger = logging.getLogger(__name__)


def _parse_json_safe(text: str) -> dict | None:
    """Strip code fences and extract the first balanced JSON object."""
    if not text:
        return None
    cleaned = text.strip()
    # strip ```json ... ``` fences
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    # find first { ... last }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except Exception:
        return None


def _deduplicate(docs: list[dict]) -> list[dict]:
    """Dedupe by chunk id / text prefix. Preserves order, keeps first occurrence."""
    seen: set[str] = set()
    out: list[dict] = []
    for d in docs:
        key = str(
            d.get("id")
            or d.get("chunk_id")
            or d.get("point_id")
            or (d.get("text", "")[:64])
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _context_summary(docs: list[dict], top_k: int = 5, per_doc: int = 300) -> str:
    """First N docs, truncated — fed to the sufficiency judge."""
    chunks = []
    for d in docs[:top_k]:
        t = (d.get("text") or d.get("content") or "").strip()
        if t:
            chunks.append(t[:per_doc])
    return "\n---\n".join(chunks) if chunks else "(no context gathered)"


def _deep_research_active(state: dict) -> bool:
    """Auto-fire for tier3_complex + standard intent; opt-in otherwise."""
    if getattr(settings, "rag_deep_research_enabled", False):
        return True
    if state.get("query_tier") == "tier3_complex":
        return True
    # 'standard' intent here means the user-confirmed "standard" activation bucket.
    if state.get("intent") == "standard":
        return True
    return False


async def conduct_deep_research(
    question: str,
    accumulated_docs: list[dict],
    state: dict,
    depth: int | None = None,
) -> list[dict]:
    """Recursive sufficiency loop. Returns deduped accumulated docs.

    Guard: returns accumulated_docs unchanged when feature disabled or depth exhausted.
    Failures in the judge LLM or follow-up retrieval are non-fatal: log + return what we have.
    """
    if not _deep_research_active(state):
        return accumulated_docs
    if depth is None:
        depth = getattr(settings, "rag_deep_research_max_depth", 2)
    if depth <= 0 or not accumulated_docs:
        return accumulated_docs

    ollama = _services._ollama
    if ollama is None:
        logger.warning("Deep research: ollama service unavailable, skipping")
        return accumulated_docs

    summary = _context_summary(accumulated_docs)
    try:
        raw = await ollama._generate_fast(
            system_prompt=SUFFICIENCY_CHECK_SYSTEM,
            user_prompt=SUFFICIENCY_CHECK_USER.format(
                question=question, context_summary=summary
            ),
            timeout=get_node_timeout("default_fast", getattr(settings, "node_timeout_fast", 15)),
            max_retries=1,
        )
    except Exception as e:
        logger.warning("Deep research: sufficiency judge failed (non-fatal): %s", e)
        return accumulated_docs

    verdict = _parse_json_safe(raw)
    if not verdict:
        logger.warning("Deep research: unparseable judge output: %.120s", raw)
        return accumulated_docs
    if verdict.get("is_sufficient", True):
        return accumulated_docs

    follow_ups = [q for q in (verdict.get("complementary_queries") or []) if q and q.strip()]
    follow_ups = follow_ups[:2]
    if not follow_ups:
        return accumulated_docs

    logger.info(
        "Deep research: insufficient at depth=%d, firing %d follow-ups: %s",
        depth, len(follow_ups), follow_ups,
    )

    chat_history = state.get("chat_history", []) or []
    intent = state.get("intent", "FACTUAL")
    selected_clusters = state.get("selected_clusters", []) or []
    knowledge_tags = state.get("knowledge_tags")
    query_tier = state.get("query_tier", "standard")
    embedder = _services._embedder
    qdrant = _services._qdrant
    lightrag = _services._lightrag

    async def _one(q: str) -> list[dict]:
        try:
            return await retrieve_for_single_query(
                query=q,
                chat_history=chat_history,
                hyde_text=None,
                intent=intent,
                selected_clusters=selected_clusters,
                embedder=embedder,
                qdrant=qdrant,
                lightrag=lightrag,
                knowledge_tags=knowledge_tags,
                query_tier=query_tier,
            )
        except Exception as e:
            logger.warning("Deep research: follow-up retrieval failed for %r: %s", q, e)
            return []

    results = await asyncio.gather(*[_one(q) for q in follow_ups])
    new_docs: list[dict] = []
    for r in results:
        if r:
            new_docs.extend(r)

    if not new_docs:
        return accumulated_docs

    merged = _deduplicate(accumulated_docs + new_docs)
    return await conduct_deep_research(question, merged, state, depth - 1)