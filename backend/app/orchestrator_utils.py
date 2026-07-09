"""Mukthi Guru — Orchestrator Utilities

Shared request preparation, memory context preparation, and language routing utilities
used by both synchronous and streaming orchestrators.

Fast-path routing: classifies queries into fast/standard/deep based on
intent, doctrine keywords, and query structure.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any, Optional

from app.config import settings
from app.language_utils import detect_and_prepare_language_info
from rag.memory import build_memory_context, normalize_session_id

if TYPE_CHECKING:
    from app.dependencies import ServiceContainer
    from app.schemas import ChatRequest

logger = logging.getLogger(__name__)

# Query patterns live in rag.query_patterns so intent routing and graph
# selection pull from a single source. Aliased here with the original
# leading-underscore names so existing call sites are unchanged.
from rag.query_patterns import (
    DOCTRINE_FAST_PATH_KEYWORDS as _DOCTRINE_FAST_PATH_KEYWORDS,
    HEURISTIC_BROAD_SIMPLE_PATTERNS,
    HEURISTIC_DEEP_PATTERNS as _DEEP_QUERY_PATTERNS,
    HEURISTIC_MULTI_PART_INDICATORS as _MULTI_PART_INDICATORS,
    HEURISTIC_SIMPLE_PATTERNS as _SIMPLE_QUERY_PATTERNS,
)


def cache_language_key(message: str, language: str) -> str:
    """Generate a cache key based on the language and trimmed message."""
    normalized_lang = (language or "en").lower().strip()
    return f"{normalized_lang}:{message.strip()}"


CLASSIFY_COMPLEXITY_PROMPT = """You are an expert query complexity classifier for a RAG spiritual application (Mukthi Guru).
Classify the user's query into one of three complexity tiers:
- "fast": Simple factual queries, basic definitions, questions about founders, or casual greetings.
- "standard": Factual queries requiring standard retrieval, or detailed questions about specific spiritual practices or concepts.
- "deep": Complex, multi-hop, analytical, comparative, or deeply reflective queries.

Your output MUST be a JSON object containing exactly one key "tier" with one of the values: "fast", "standard", "deep". Do not output any thinking or extra text.
User Query: {query}
Output:"""


from app.telemetry_db import log_router_decision


async def select_graph_for_query(
    query: str,
    container: Optional[ServiceContainer] = None,
    detected_intent: Optional[str] = None,
    query_tier: Optional[str] = None,
) -> str:
    """Select the most appropriate compiled graph variant for a query using dynamic LLM classification with heuristic fallback.

    Args:
        query: Raw user query (already translated to English if necessary).
        container: The ServiceContainer instance to access LLM providers.
        detected_intent: Optional intent label from intent router.
        query_tier: Optional tier label (tier2_simple, tier3_complex, etc.).

    Returns:
        "fast" — Simple factual queries (1-2 LLM calls, <20s)
        "standard" — Complex factual queries (3-4 LLM calls, <35s)
        "deep" — Comparative/analytical queries (5-6 LLM calls, <45s)
    """
    if not query:
        return "standard"

    threshold = getattr(settings, "semantic_router_confidence_threshold", 0.65)
    shadow_mode = getattr(settings, "semantic_router_shadow_mode", False)
    q = query.lower().strip()

    # 0. Respect on-device intent router's tier classification
    # Runs BEFORE semantic router to ensure simple FAQ queries route to the
    # fast graph instead of being overridden by the embedding router.
    if query_tier in ("tier2_simple", "fast"):
        try:
            asyncio.create_task(
                log_router_decision(
                    query=query,
                    tier="fast",
                    confidence=1.0,
                    method="tier_respect",
                )
            )
        except Exception:
            pass
        return "fast"

    # 1. Heuristic routing FIRST (no LLM, deterministic, prevents simple queries
    # like "what is Soul Sync" from being over-classified as 'standard' by the
    # embedding router and paying for 6+ serial LLM calls).
    tokens = q.split()

    # Deep patterns first (highest priority)
    for pattern in _DEEP_QUERY_PATTERNS:
        if re.search(pattern, q):
            try:
                asyncio.create_task(
                    log_router_decision(
                        query=query,
                        tier="deep",
                        confidence=1.0,
                        method="heuristic_deep",
                    )
                )
            except Exception:
                pass
            return "deep"

    # Multi-part guard: if query contains conjunctions/comparatives, don't fast-path
    is_multi_part = any(re.search(patn, q) for patn in _MULTI_PART_INDICATORS)

    # Doctrine keyword fast-path: known spiritual terms get fast even at 25 tokens
    if detected_intent in ("FACTUAL", "QUERY"):
        if any(kw in q for kw in _DOCTRINE_FAST_PATH_KEYWORDS) and not is_multi_part:
            if len(tokens) <= 25:
                try:
                    asyncio.create_task(
                        log_router_decision(
                            query=query,
                            tier="fast",
                            confidence=1.0,
                            method="heuristic_doctrine",
                        )
                    )
                except Exception:
                    pass
                return "fast"
        elif len(tokens) <= 20 and not is_multi_part:
            try:
                asyncio.create_task(
                    log_router_decision(
                        query=query,
                        tier="fast",
                        confidence=1.0,
                        method="heuristic_short",
                    )
                )
            except Exception:
                pass
            return "fast"

    # Regex-based simple query detection
    for pattern in _SIMPLE_QUERY_PATTERNS:
        if re.search(pattern, q) and len(tokens) <= 15 and not is_multi_part:
            try:
                asyncio.create_task(
                    log_router_decision(
                        query=query,
                        tier="fast",
                        confidence=1.0,
                        method="heuristic_pattern",
                    )
                )
            except Exception:
                pass
            return "fast"

    # Broader regex-based simple query detection
    for pattern in HEURISTIC_BROAD_SIMPLE_PATTERNS:
        if re.search(pattern, q) and len(tokens) <= 15 and not is_multi_part:
            try:
                asyncio.create_task(
                    log_router_decision(
                        query=query,
                        tier="fast",
                        confidence=1.0,
                        method="heuristic_broad",
                    )
                )
            except Exception:
                pass
            return "fast"

    # Final catch-all: short greetings and statements
    if len(tokens) <= 4 and detected_intent in ("CASUAL", "GREETING"):
        try:
            asyncio.create_task(
                log_router_decision(
                    query=query,
                    tier="fast",
                    confidence=1.0,
                    method="heuristic_greeting",
                )
            )
        except Exception:
            pass
        return "fast"

    # 2. Semantic router (embedding-based, sub-100 ms, zero LLM call)
    semantic_tier: str | None = None
    semantic_confidence: float = 0.0
    if container and hasattr(container, "semantic_router"):
        try:
            semantic_router = getattr(container, "semantic_router", None)
            if semantic_router:
                semantic_tier, semantic_confidence = semantic_router.classify_with_score(query)
                logger.info(
                    f"SemanticModelRouter: classified as '{semantic_tier}' "
                    f"(confidence={semantic_confidence:.3f})"
                )
                if semantic_confidence >= threshold and not shadow_mode:
                    try:
                        asyncio.create_task(
                            log_router_decision(
                                query=query,
                                tier=semantic_tier,
                                confidence=semantic_confidence,
                                method="semantic",
                            )
                        )
                    except Exception:
                        pass
                    return semantic_tier
                if shadow_mode:
                    logger.info(
                        f"SemanticModelRouter shadow mode: semantic='{semantic_tier}' "
                        f"(conf={semantic_confidence:.3f}), continuing to heuristic for actual routing"
                    )
                else:
                    logger.warning(
                        f"SemanticModelRouter low confidence ({semantic_confidence:.3f} < {threshold}). "
                        f"Falling back to default 'standard'."
                    )
        except Exception as exc:
            logger.warning(f"SemanticModelRouter failed: {exc}. Falling back to heuristics.")

    # 3. Default fallback
    try:
        asyncio.create_task(
            log_router_decision(
                query=query,
                tier="standard",
                confidence=1.0,
                method="default",
                shadow_tier=semantic_tier if shadow_mode else None,
            )
        )
    except Exception:
        pass
    return "standard"


def should_skip_verification(query_tier: str, detected_intent: str) -> bool:
    """Determine if verification nodes can be skipped.

    Fast-path queries get lightweight verification only.
    """
    return query_tier in ("fast", "tier2_simple") or detected_intent in ("CASUAL", "MEDITATION")


def get_expected_keywords(query: str) -> list[str]:
    """Extract expected doctrine keywords from a query for retrieval boosting."""
    q = query.lower()
    keywords: list[str] = []

    if "four sacred secret" in q or "four secret" in q or "sacred secrets" in q:
        keywords.extend(["spiritual vision", "inner truth", "universal intelligence", "spiritual right action"])
    elif "first sacred secret" in q or "1st sacred secret" in q or "explain the first" in q:
        keywords.append("spiritual vision")
    elif "second sacred secret" in q or "2nd sacred secret" in q:
        keywords.append("inner truth")
    elif "third sacred secret" in q or "3rd sacred secret" in q:
        keywords.append("universal intelligence")
    elif "fourth sacred secret" in q or "4th sacred secret" in q:
        keywords.append("spiritual right action")
    elif "sacred secret" in q:
        keywords.extend(["spiritual vision", "inner truth", "universal intelligence", "spiritual right action"])
    if "deeksha" in q:
        keywords.extend(["oneness blessing", "frontal lobe", "parietal", "neurobiological"])
    if "soul sync" in q or "soul-sync" in q:
        keywords.extend(["breath awareness", "humming", "pause", "Aham", "golden light", "intention"])
    if "manifest 2026" in q or "manifest 2025" in q or "12 powers" in q:
        keywords.extend(["manifest", "12 powers", "monthly", "intention", "heart connection", "deeksha"])
    if "ekam" in q:
        keywords.extend(["varadaiahpalem", "tirupati", "andhra pradesh", "india"])
    if "beautiful state" in q:
        keywords.extend(["calm", "joy", "love", "connection", "beautiful state teachings"])
    if "preethaji" in q or "krishnaji" in q:
        keywords.extend(["co-founders", "oneness movement", "ekam", "lokaa foundation"])

    return keywords


async def prepare_request_state(
    container: ServiceContainer,
    chat_body: ChatRequest,
    preferred_lang: str,
    user: Optional[dict] = None,
) -> dict[str, Any]:
    """Prepare translated history, memory context, and language info for the query."""
    user_msg = chat_body.user_message.strip()
    cache_key = cache_language_key(user_msg, preferred_lang)

    lang_detection, _, is_indic, should_translate = detect_and_prepare_language_info(
        container, user_msg, preferred_lang
    )
    user_id = user.get("id", "anonymous") if user else "anonymous"
    stable_session_id = normalize_session_id(chat_body.session_id, user_id)
    chat_history = [m.model_dump() for m in chat_body.messages]
    if len(chat_history) > settings.chat_history_max_messages:
        chat_history = chat_history[-settings.chat_history_max_messages :]

    user_msg_en = user_msg
    if should_translate:
        user_msg_en = await container.translation.translate_text(
            text=user_msg, source_lang=preferred_lang, target_lang="en"
        )
        logger.info(f"Translated user query from {preferred_lang} to English: {user_msg_en}")

    chat_history_en = []
    if is_indic and should_translate:
        for msg in chat_history:
            msg_content_en = await container.translation.translate_text(
                text=msg["content"], source_lang=preferred_lang, target_lang="en"
            )
            chat_history_en.append({"role": msg["role"], "content": msg_content_en})
    else:
        chat_history_en = chat_history

    memory_context, distress_history = await prepare_user_memory(
        container,
        user_id,
        chat_history_en,
    )

    return {
        "user_msg_en": user_msg_en,
        "is_indic": is_indic,
        "preferred_lang": preferred_lang,
        "user_id": user_id,
        "stable_session_id": stable_session_id,
        "chat_history_en": chat_history_en,
        "memory_context": memory_context,
        "distress_history": distress_history,
        "lang_detection": lang_detection,
        "original_user_msg": chat_body.user_message,
        "original_chat_history": chat_body.messages,
        "cache_key": cache_key,
    }


async def prepare_user_memory(
    container: ServiceContainer,
    user_id: str,
    chat_history: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Fetch user profile and memory context to guide the prompt generation."""
    if not container.user_profile:
        return "", []

    # Anonymous users have no persistent profile — skip all DB calls
    if not user_id or user_id == "anonymous":
        return "", []

    profile = await container.user_profile.get_or_create_profile(user_id)
    profile.total_conversations += 1
    await container.user_profile.update_profile(profile)

    recent_memories = await container.user_profile.get_recent_memories(user_id, limit=3)
    memory_context = build_memory_context(
        recent_memories=recent_memories,
        chat_history=chat_history,
    )

    if settings.feature_memory_enabled and getattr(container, "memory_service", None):
        try:
            last_query = chat_history[-1]["content"] if chat_history else ""

            async def fetch_memory_layer():
                core_m = await container.memory_service.get_core(user_id)
                semantic_m = []
                if last_query:
                    semantic_m = await container.memory_service.search_semantic(
                        user_id, last_query, limit=3, min_similarity=0.6
                    )
                return core_m, semantic_m

            core_m, semantic_m = await asyncio.wait_for(fetch_memory_layer(), timeout=0.200)

            memory_blocks = []
            if core_m:
                memory_blocks.append("USER PROFILE & CORE FACTS:\n- " + "\n- ".join(c["content"] for c in core_m))
            if semantic_m:
                memory_blocks.append("PAST RELEVANT RECOLLECTIONS:\n- " + "\n- ".join(s["content"] for s in semantic_m))

            if memory_blocks:
                new_memory_context = "\n\n".join(memory_blocks)
                if memory_context:
                    memory_context = f"{memory_context}\n\n{new_memory_context}"
                else:
                    memory_context = new_memory_context
        except asyncio.TimeoutError:
            logger.warning(f"Memory layer fetch timed out for user {user_id} (exceeded 200ms budget)")
        except Exception as e:
            logger.warning(f"Memory layer fetch failed: {e}")

    distress_history = []
    for mem in recent_memories:
        if mem.emotional_arc:
            recent_emotion = mem.emotional_arc[-1]
            if recent_emotion.get("distress_level", 0) >= 2:
                distress_history.append(recent_emotion)

    return memory_context, distress_history
