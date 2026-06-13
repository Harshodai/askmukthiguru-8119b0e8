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

# Expanded simple query patterns (synced with intent.py _SIMPLE_QUERY_PATTERNS)
_SIMPLE_QUERY_STARTS: tuple[str, ...] = (
    "who", "what is", "what are", "when", "where", "how to", "how do",
    "how does", "how many", "how much", "can you", "explain the",
    "what did", "tell me about", "describe", "define", "meaning of",
)

# Deep query patterns — comparative, analytical, multi-hop
_DEEP_QUERY_PATTERNS: list[str] = [
    r"\bcompare\b", r"\bcontrast\b", r"\bdifference between\b",
    r"\bsimilarities between\b", r"\bversus\b", r"\bvs\b",
    r"\brelationship between\b", r"\bhow are .* connected\b",
    r"\bpros and cons\b", r"\badvantages? and disadvantages?\b",
    r"\bevolution of\b", r"\bover time\b", r"\bacross different\b",
    r"\btrick question\b", r"\btrap\b", r"\bfooled\b",
    r"\btest the bot\b", r"\btry to confuse\b",
]

# Doctrine keyword fast-path triggers
_DOCTRINE_FAST_PATH_KEYWORDS: list[str] = [
    "four sacred secrets", "four secrets", "sacred secret",
    "deeksha", "oneness blessing",
    "soul sync", "soul-sync",
    "ekam", "varadaiahpalem",
    "manifest 2026", "manifest 2025", "12 powers",
    "beautiful state", "beautiful state teachings",
    "preethaji", "krishnaji", "founder",
    "loka seva", "ekam world",
]


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


async def select_graph_for_query(
    query: str, container: Optional[Any] = None, detected_intent: Optional[str] = None
) -> str:
    """Select the most appropriate compiled graph variant for a query using dynamic LLM classification with heuristic fallback.

    Args:
        query: Raw user query (already translated to English if necessary).
        container: The ServiceContainer instance to access LLM providers.
        detected_intent: Optional intent label from intent router.

    Returns:
        "fast" — Simple factual queries (1-2 LLM calls, <20s)
        "standard" — Complex factual queries (3-4 LLM calls, <35s)
        "deep" — Comparative/analytical queries (5-6 LLM calls, <45s)
    """
    if not query:
        return "standard"

    q = query.lower().strip()

    # 1. Dynamic LLM-based classification (preferred)
    if container:
        try:
            # Prefer openrouter for fast classification if configured
            provider = getattr(container, "openrouter", None)
            from app.config import settings

            if not provider or not getattr(settings, "openrouter_api_key", None):
                # Fallback to the main configured classifier
                provider = getattr(container, "ollama", None)

            if provider:
                import json
                system_prompt = "You are a query complexity classifier. Respond only with JSON containing the key 'tier'."
                user_prompt = CLASSIFY_COMPLEXITY_PROMPT.format(query=query)

                # Call fast classification method
                if hasattr(provider, "_generate_fast"):
                    res = await provider._generate_fast(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=0.0,
                        max_tokens=50,
                        timeout=3.0,
                    )
                else:
                    res = await provider.generate(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=0.0,
                        max_tokens=50,
                        timeout=3.0,
                    )

                res_clean = res.strip()
                if res_clean.startswith("```"):
                    lines = res_clean.splitlines()
                    if len(lines) >= 3:
                        res_clean = "\n".join(lines[1:-1]).strip()

                first_brace = res_clean.find("{")
                last_brace = res_clean.rfind("}")
                if first_brace != -1 and last_brace != -1:
                    data = json.loads(res_clean[first_brace:last_brace+1])
                    tier = data.get("tier", "").strip().lower()
                    if tier in ("fast", "standard", "deep"):
                        logger.info(f"Dynamic LLM Query Router: classified query as '{tier}'")
                        return tier
        except Exception as e:
            logger.warning(f"Dynamic LLM Query Router failed: {e}. Falling back to heuristics.")

    # 2. Heuristic fallback (original logic)
    tokens = q.split()

    # Check deep patterns first (highest priority)
    for pattern in _DEEP_QUERY_PATTERNS:
        if re.search(pattern, q):
            return "deep"

    # Check if intent router already classified as simple
    if detected_intent in ("FACTUAL", "QUERY"):
        if len(tokens) <= 15:
            return "fast"

    # Check doctrine-specific fast path triggers
    for keyword in _DOCTRINE_FAST_PATH_KEYWORDS:
        if keyword in q:
            if len(tokens) <= 12:
                return "fast"

    # Check simple query patterns
    if len(tokens) <= 8:
        for st in _SIMPLE_QUERY_STARTS:
            if q.startswith(st):
                return "fast"

    # Broader regex-based simple query detection
    simple_patterns = [
        r"^(what|who|where|when|how|why|is|are|can|do|does|did)\s",
        r"^(tell me|explain|describe|define)\s+(about|the|what|how)",
        r"^(what is|what are|who is|who are|where is|where are)\s+",
    ]
    for pattern in simple_patterns:
        if re.search(pattern, q) and len(tokens) <= 10:
            return "fast"

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
