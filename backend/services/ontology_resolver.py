"""Dynamic LLM-driven ontology & concept resolver.

Extracts canonical spiritual concepts, inner states, and doctrine themes
from any seeker query to query the Neo4j Knowledge Graph and expand Qdrant
retrieval filters dynamically, eliminating brittle hardcoded lists.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_RESOLVER_CACHE: dict[str, list[str]] = {}
_MAX_CACHE_ENTRIES = 2048

_SYSTEM_PROMPT = (
    "You are an expert ontology concept resolver for a spiritual wisdom archive.\n"
    "Given a seeker's inquiry, extract 2 to 5 canonical spiritual concepts, inner states, "
    "or practices that capture the core inquiry (e.g., 'Relationship', 'Hurt', 'Dissolving Hurt', "
    "'Suffering State', 'Beautiful State', 'Healing', 'Forgiveness', 'Inner Stillness', 'Connection', 'Karma').\n"
    "Reply with ONLY a valid JSON object of the form:\n"
    '{"concepts": ["Concept One", "Concept Two"]}\n'
    "Each concept must be in Title Case. No other text."
)


def _clean_concept(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip()
    return " ".join(word.capitalize() for word in text.split())


async def resolve_query_concepts_llm_async(
    query: str,
    llm_service: Any = None,
    *,
    timeout_s: float = 1.2,
) -> list[str]:
    """Dynamically resolve query concepts using a fast structured LLM call."""
    clean_query = query.strip()
    if not clean_query:
        return []

    cache_key = hashlib.sha256(clean_query.lower().encode("utf-8")).hexdigest()[:16]
    if cache_key in _RESOLVER_CACHE:
        return list(_RESOLVER_CACHE[cache_key])

    # Try resolving LLM service from container if not provided
    if llm_service is None:
        try:
            from app.dependencies import get_container
            container = get_container()
            llm_service = getattr(container, "openrouter", None) or getattr(container, "llm", None)
        except Exception:
            llm_service = None

    if llm_service is None or not hasattr(llm_service, "generate"):
        return _fallback_token_concepts(clean_query)

    try:
        kwargs: dict[str, Any] = {
            "temperature": 0.0,
            "max_tokens": 128,
        }
        # Use fast model if available
        try:
            from app.config import settings
            model = getattr(settings, "first_person_relevance_model", None) or getattr(settings, "fast_model", "anthropic/claude-haiku-5.5")
            kwargs["model"] = model
        except Exception:
            pass

        user_prompt = f"Query: {clean_query}"
        
        call_coro = llm_service.generate(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            **kwargs,
        )
        if asyncio.iscoroutine(call_coro) or asyncio.isfuture(call_coro):
            raw_response = await asyncio.wait_for(call_coro, timeout=timeout_s)
        else:
            raw_response = await asyncio.wait_for(asyncio.to_thread(lambda: call_coro), timeout=timeout_s)

        raw_text = str(raw_response or "").strip()
        # Parse JSON
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            raw_concepts = data.get("concepts", [])
            concepts = [_clean_concept(c) for c in raw_concepts if isinstance(c, str) and c.strip()]
            concepts = [c for c in concepts if c]
            if concepts:
                if len(_RESOLVER_CACHE) >= _MAX_CACHE_ENTRIES:
                    _RESOLVER_CACHE.clear()
                _RESOLVER_CACHE[cache_key] = concepts
                return concepts

    except Exception as exc:
        logger.debug("[OntologyResolver] LLM concept resolution failed: %s; using fallback", exc)

    return _fallback_token_concepts(clean_query)


def resolve_query_concepts_llm(
    query: str,
    llm_service: Any = None,
    *,
    timeout_s: float = 1.2,
) -> list[str]:
    """Synchronous wrapper for resolve_query_concepts_llm_async."""
    clean_query = query.strip()
    if not clean_query:
        return []

    cache_key = hashlib.sha256(clean_query.lower().encode("utf-8")).hexdigest()[:16]
    if cache_key in _RESOLVER_CACHE:
        return list(_RESOLVER_CACHE[cache_key])

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If called synchronously while an event loop is already running on this thread,
            # do not spawn a threadpool running asyncio.run(), which creates a secondary event loop
            # and breaks connection pools (Redis/aiohttp Future attached to different loop).
            # Instead, use the zero-dependency instant token extractor.
            return _fallback_token_concepts(clean_query)
        elif loop:
            return loop.run_until_complete(
                resolve_query_concepts_llm_async(clean_query, llm_service, timeout_s=timeout_s)
            )
        else:
            return asyncio.run(
                resolve_query_concepts_llm_async(clean_query, llm_service, timeout_s=timeout_s)
            )
    except Exception as exc:
        logger.debug("[OntologyResolver] sync call failed: %s; using fallback", exc)
        return _fallback_token_concepts(clean_query)


def _fallback_token_concepts(query: str) -> list[str]:
    """Zero-dependency fallback extracting key Title-case tokens from query."""
    stop_words = {
        "how", "what", "why", "when", "where", "who", "do", "i", "can", "to", "in", "my",
        "the", "a", "an", "is", "are", "of", "and", "or", "for", "with", "about", "according",
        "teachings", "teach", "guru", "say"
    }
    words = re.findall(r"\b[A-Za-z]{3,}\b", query)
    meaningful = [w.capitalize() for w in words if w.lower() not in stop_words]
    return meaningful[:5]
