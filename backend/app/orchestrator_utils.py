"""Mukthi Guru — Orchestrator Utilities

Shared request preparation, memory context preparation, and language routing utilities
used by both synchronous and streaming orchestrators.
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


def cache_language_key(message: str, language: str) -> str:
    """Generate a cache key based on the language and trimmed message."""
    normalized_lang = (language or "en").lower().strip()
    return f"{normalized_lang}:{message.strip()}"


def select_graph_for_query(query: str) -> str:
    """Select the most appropriate compiled graph variant for a query."""
    q = query.lower().strip()
    tokens = q.split()

    deep_keywords = [
        "compare", "contrast", "difference between", "differences between",
        "how does", "why is", "explain the connection", "relationship between",
        "multiple", "several", "various", "deeper", "profound", "ultimate",
    ]
    if any(kw in q for kw in deep_keywords):
        return "deep"

    # Fast path: use regex to catch simple factual queries —
    # more robust than startswith() alone (matches "what are", "where is", etc.)
    fast_pattern = re.compile(r"^(who\s|what\s+(is|are|was|were)\s|when\s|where\s|how\s+(many|much)\s|list\s)")
    if len(tokens) <= 8 and fast_pattern.search(q):
        return "fast"

    return "standard"


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
