"""Intent routing and short-circuit node handlers."""

from __future__ import annotations

import logging
import re

from rag.meditation import (
    format_meditation_response,
    get_distress_response,
    is_meditation_complete,
    should_start_meditation,
)
from rag.prompts import CASUAL_SYSTEM_PROMPT, STIMULUS_RAG_PROMPT
from rag.states import GraphState
from services.serene_mind_engine import DistressAssessment, DistressLevel

from . import _services
from .utils import _trace_update, get_node_timeout, log_metrics, settings

logger = logging.getLogger(__name__)

# Simple LRU cache for intent classification
_intent_classification_cache: dict[str, tuple[str, str]] = {}
_INTENT_CACHE_MAX = 1000

_CAPABILITY_PATTERNS = [
    "what can you", "what do you know", "what topics", "what kind of things",
    "what can you answer", "what teachings do you have", "what is in your repository",
    "what do you store", "what information do you have", "how can you help",
    "what questions can you", "what are you able to", "tell me about yourself",
    "what do you do", "who are you", "what do you offer", "how do you work",
]

_SIMPLE_QUERY_PATTERNS = [
    r"^who is (sri )?preethaji",
    r"^who is (sri )?krishnaji",
    r"^what is (the )?beautiful state",
    r"^what is (the )?ekam",
    r"^what is deeksha",
    r"^what is soul sync",
    r"^what are (the )?four sacred secrets",
    r"^what is oneness",
    r"^what is moksha",
    r"^define ",
    r"^explain ",
]

# Temporal query patterns: trigger web search for real-time info
_TEMPORAL_PATTERNS = [
    "this month", "next festival", "upcoming", "when is", "schedule",
    "calendar", "latest", "current events", "this year", "next year",
    "next month", "last month", "this week", "next week", "today",
    "recent", "announcement", "program", "scope of manifest",
    "manifest scope", "ekam events", "oneness events",
]


@log_metrics
async def intent_router(state: GraphState, config: dict = None) -> dict:
    """Classify user message -> DISTRESS / QUERY / CASUAL / ADVERSARIAL / SAFETY_VIOLATION."""
    try:
        return await _intent_router_impl(state, config)
    except Exception as e:
        logger.exception("Intent router failed, falling back to safe default")
        question = state.get("question", "")
        lower_q = question.lower()
        needs_web_search = False
        query_tier = "tier2_simple"
        if any(pat in lower_q for pat in _TEMPORAL_PATTERNS):
            needs_web_search = True
            query_tier = "tier3_complex"
            logger.info("Intent Router Fallback: temporal pattern detected, enabling web search")
        return {
            "intent": "FACTUAL",
            "query_tier": query_tier,
            "needs_web_search": needs_web_search,
            "evaluation_trace": _trace_update(
                state, intent="FACTUAL", query_tier=query_tier,
                routing_reason="semantic_router_fallback",
                needs_web_search=needs_web_search
            ),
        }


async def _intent_router_impl(state: GraphState, config: dict = None) -> dict:
    """Internal implementation of the intent router."""
    from rag.nodes.utils import emit_status
    await emit_status(config, "Understanding your question...")

    question = state["question"]
    lower_q = question.lower()
    ollama = _services._ollama

    # Check if we're in an active meditation session (state machine check)
    meditation_step = state.get("meditation_step", 0)
    if meditation_step > 0:
        if is_meditation_complete(meditation_step):
            return {"intent": "CASUAL", "meditation_step": 0}
        if should_start_meditation(question):
            return {"intent": "MEDITATION_CONTINUE", "meditation_step": meditation_step}
        return {"intent": "CASUAL", "meditation_step": 0}

    # ---- Serene Mind Distress Check (BEFORE pre-router) ----
    # Only route to DISTRESS if keyword-based detection (Stage 1) finds MODERATE+ distress.
    # This avoids false positives from semantic/LLM stages on short queries like "Hello".
    serene_mind = _services._serene_mind
    if serene_mind is not None:
        chat_history = state.get("chat_history", [])
        try:
            # Use keyword-only assessment (Stage 1 only) for routing decision
            keyword_assessment = serene_mind.assess_distress(question, chat_history)
            if keyword_assessment.level >= DistressLevel.MODERATE:
                logger.info(
                    f"Intent Router: Serene Mind keyword detected {keyword_assessment.level.name} distress "
                    f"(confidence={keyword_assessment.confidence:.2f}), routing to DISTRESS"
                )
                return {
                    "intent": "DISTRESS",
                    "query_tier": "tier2_simple",
                    "evaluation_trace": _trace_update(
                        state, intent="DISTRESS", query_tier="tier2_simple",
                        routing_reason="serene_mind_keyword_distress",
                        distress_level=keyword_assessment.level.name,
                        distress_confidence=keyword_assessment.confidence,
                        distress_signals=keyword_assessment.detected_signals,
                    ),
                }
        except Exception as e:
            logger.warning(f"Serene Mind keyword distress check failed: {e}")

    # ---- Temporal / Real-Time Query Check ----
    # Detects queries about current/future events (festivals, schedules, etc.)
    # and flags them for web search. Runs before prerouter and cache.
    if any(pat in lower_q for pat in _TEMPORAL_PATTERNS):
        logger.info(f"Intent Router: temporal query detected, flagging for web search: {question[:60]}...")
        return {
            "intent": "FACTUAL",
            "query_tier": "tier3_complex",
            "needs_web_search": True,
            "evaluation_trace": _trace_update(
                state, intent="FACTUAL", query_tier="tier3_complex",
                routing_reason="temporal_query_heuristic",
                needs_web_search=True
            ),
        }

    # ---- Regex Pre-Router Check ----
    from rag.intent_prerouter import preroute_intent
    pre_intent = preroute_intent(question)
    if pre_intent:
        logger.info(f"Intent Router: Regex Pre-Router matched intent: {pre_intent}")
        mapped_intent = "FACTUAL" if pre_intent == "QUERY" else pre_intent
        query_tier = "tier2_simple"
        return {
            "intent": mapped_intent,
            "query_tier": query_tier,
            "evaluation_trace": _trace_update(
                state, intent=mapped_intent, query_tier=query_tier,
                routing_reason="regex_prerouter"
            ),
        }

    # ---- Heuristic fast-path #1: capability / meta questions ----
    if any(kw in lower_q for kw in _CAPABILITY_PATTERNS):
        logger.info("Intent Router: heuristic fast-path — capability/meta question, fast")
        return {
            "intent": "FACTUAL",
            "query_tier": "tier2_simple",
            "evaluation_trace": _trace_update(
                state, intent="FACTUAL", query_tier="tier2_simple",
                routing_reason="heuristic_capability"
            ),
        }

    # ---- Heuristic fast-path #2: pattern-based simple factual ----
    for pattern in _SIMPLE_QUERY_PATTERNS:
        if re.search(pattern, lower_q):
            logger.info(f"Intent Router: heuristic fast-path — simple factual match ({pattern}), fast")
            return {
                "intent": "FACTUAL",
                "query_tier": "tier2_simple",
                "evaluation_trace": _trace_update(
                    state, intent="FACTUAL", query_tier="tier2_simple",
                    routing_reason="heuristic_simple"
                ),
            }



    # ---- Cache check ----
    cache_key = lower_q.strip()
    if cache_key in _intent_classification_cache:
        cached_intent, cached_complexity = _intent_classification_cache[cache_key]
        if cached_intent == "QUERY":
            cached_intent = "FACTUAL"
        tier = "tier2_simple" if cached_complexity == "simple" else "tier3_complex"
        if cached_intent == "FACTUAL":
            logger.info(f"Intent Router: cache hit — {cached_intent} | {tier}")
            return {
                "intent": cached_intent,
                "query_tier": tier,
                "evaluation_trace": _trace_update(
                    state, intent=cached_intent, query_tier=tier,
                    routing_reason="cache_hit"
                ),
            }
        return {
            "intent": cached_intent,
            "query_tier": tier,
            "evaluation_trace": _trace_update(
                state, intent=cached_intent, query_tier=tier,
                routing_reason="cache_hit"
            ),
        }

    # ---- On-Device Intent Classifier (Phase 3 / Strategic) ----
    # Fast keyword/embedding classification before expensive LLM call.
    # Skips the LLM entirely for ~90% of queries and guarantees <50 ms.
    try:
        from rag.nodes.on_device_intent import classify_with_reason as _on_device_classify
        on_device_result = _on_device_classify(question)
        if on_device_result:
            intent, tier, routing_reason = on_device_result
            logger.info(f"Intent Router: on-device classifier match — {intent} | {tier} ({routing_reason})")
            return {
                "intent": intent,
                "query_tier": tier,
                "evaluation_trace": _trace_update(
                    state, intent=intent, query_tier=tier,
                    routing_reason=routing_reason
                ),
            }
    except Exception as e:
        logger.debug(f"On-device intent classifier failed: {e}, proceeding to LLM")

    # ---- Single LLM call for both intent + complexity classification ----
    try:
        t_out = get_node_timeout("intent_router", 12)
        result = await ollama.classify_intent_and_complexity(
            text=question, timeout=t_out, max_retries=1
        )
        intent = result["intent"]
        complexity = result["complexity"]
    except Exception as e:
        logger.warning(
            f"Combined intent+complexity classification failed: {e}. "
            f"Falling back to separate classify call."
        )
        try:
            t_out = get_node_timeout("intent_router", 12)
            intent = await ollama.classify(text=question, timeout=t_out, max_retries=1)
        except Exception as e2:
            logger.warning(f"Intent classification also failed: {e2}. Defaulting to FACTUAL.")
            intent = "FACTUAL"
        complexity = "complex"

    if intent == "QUERY":
        intent = "FACTUAL"

    query_tier = None
    if intent == "FACTUAL":
        if complexity == "simple":
            query_tier = "tier2_simple"
        else:
            query_tier = "tier3_complex"

    # Store in cache
    _intent_classification_cache[cache_key] = (intent, complexity)
    if len(_intent_classification_cache) > _INTENT_CACHE_MAX:
        oldest = next(iter(_intent_classification_cache))
        del _intent_classification_cache[oldest]

    logger.info(
        f"Intent Router: classified '{question[:80]}...' -> {intent} | tier -> {query_tier} (question_len={len(question)})"
    )
    return {
        "intent": intent,
        "query_tier": query_tier,
        "evaluation_trace": _trace_update(
            state, intent=intent, query_tier=query_tier, routing_reason="classifier"
        ),
    }


async def handle_casual(state: GraphState, config: dict = None) -> dict:
    """Handle casual conversation with multi-turn awareness."""
    if state.get("final_answer"):
        return state

    from rag.nodes.utils import emit_status
    await emit_status(config, "Saying hello...")

    chat_history = state.get("chat_history", [])
    ollama = _services._ollama

    history_ctx = ""
    if chat_history:
        recent = chat_history[-4:]
        history_lines = [
            f"{m.get('role', 'user').capitalize()}: {m.get('content', '')[:150]}" for m in recent
        ]
        history_ctx = "\n\nRecent conversation:\n" + "\n".join(history_lines)

    try:
        response = await ollama.generate(
            system_prompt=CASUAL_SYSTEM_PROMPT,
            user_prompt=state["question"] + history_ctx,
        )
        if not response or not response.strip():
            logger.warning("handle_casual: LLM returned empty response, using warm fallback")
            response = (
                "🙏 Namaste! I am Mukthi Guru, here to share the wisdom of "
                "Sri Preethaji and Sri Krishnaji. How may I serve your journey "
                "towards inner peace today?"
            )
    except Exception as e:
        logger.error(f"handle_casual failed: {e}")
        response = (
            "🙏 Namaste! I am Mukthi Guru, here to walk with you on the "
            "path of spiritual awakening. Please share what is in your heart."
        )
    return {"final_answer": response}


async def handle_distress(state: GraphState, config: dict = None) -> dict:
    """Handle distress with COMPASSIONATE TEACHINGS + meditation offer."""
    from rag.nodes.utils import emit_status
    await emit_status(config, "Holding space for what you're feeling...")

    question = state["question"]
    chat_history = state.get("chat_history", [])
    serene_mind = _services._serene_mind
    ollama = _services._ollama

    if serene_mind is not None:
        assessment = await serene_mind.async_assess_distress(question, chat_history)
    else:
        assessment = DistressAssessment(level=DistressLevel.MODERATE, confidence=0.5)

    relevant_docs = state.get("relevant_docs", [])

    if relevant_docs:
        context = "\n\n---\n\n".join(
            f"[Source: {doc.get('title', 'Unknown')}]\n{doc['text']}" for doc in relevant_docs[:3]
        )

        prompt = f"""The user is in emotional distress. Their message: {question}

Retrieved teachings from Sri Preethaji and Sri Krishnaji:
{context}

Based on the above teachings, compose a deeply compassionate response that:
1. Acknowledges their pain with genuine empathy
2. Shares the MOST relevant teaching that speaks directly to their situation
3. Uses Sri Preethaji or Sri Krishnaji's words naturally, as if the guru is speaking directly
4. Offers to guide them through a Serene Mind meditation
5. Keeps the tone warm, personal, and non-clinical"""

        try:
            response = await ollama.generate(
                system_prompt=STIMULUS_RAG_PROMPT,
                user_prompt=prompt,
                temperature=0.3,
            )
            if not response or not response.strip():
                logger.warning(
                    "Distress generation returned empty response. Falling back to template."
                )
                response = (
                    serene_mind.get_response(assessment)
                    if serene_mind
                    else get_distress_response()
                )
        except Exception as e:
            logger.error(f"Distress generation failed: {e}")
            response = (
                serene_mind.get_response(assessment) if serene_mind else get_distress_response()
            )
    else:
        response = (
            serene_mind.get_response(assessment) if serene_mind else get_distress_response()
        )

    if assessment.level >= DistressLevel.SEVERE:
        crisis_info = (
            "\n\n🆘 **Crisis Support (available 24/7):**\n"
            "• iCall (India): 9152987821\n"
            "• AASRA (India): 9820466726 | aasra.info\n"
            "• Vandrevala Foundation: 1860-2662-345\n"
            "• International: Crisis Text Line — text HOME to 741741"
        )
        response = crisis_info + "\n\n" + response

    logger.info(
        f"Distress handler: level={assessment.level.name}, has_teachings={bool(relevant_docs)}"
    )
    return {
        "final_answer": response,
        "meditation_step": 0,
    }


async def handle_meditation(state: GraphState, config: dict = None) -> dict:
    """Continue an active meditation session or start a new specific one."""
    from rag.nodes.utils import emit_status
    await emit_status(config, "Guiding you into the practice...")

    step = state.get("meditation_step", 1)
    question = state.get("question", "").lower()
    from rag.meditation import MEDITATION_SCRIPTS

    if "soul sync" in question and step == 1:
        script = MEDITATION_SCRIPTS["soul_sync"]
        response = f"**{script['title']}**\n\n" + "\n".join(
            [f"{i + 1}. {s}" for i, s in enumerate(script["steps"])]
        )
        return {"final_answer": response, "meditation_step": 0}

    if "serene mind" in question and step == 1:
        script = MEDITATION_SCRIPTS["serene_mind"]
        response = f"**{script['title']}**\n\n" + "\n".join(
            [f"{i + 1}. {s}" for i, s in enumerate(script["steps"])]
        )
        return {"final_answer": response, "meditation_step": 0}

    if "meditation" in question and step == 1:
        script = MEDITATION_SCRIPTS["serene_mind"]
        response = f"**{script['title']}**\n\n" + "\n".join(
            [f"{i + 1}. {s}" for i, s in enumerate(script["steps"])]
        )
        return {"final_answer": response, "meditation_step": 0}

    response = format_meditation_response(step)
    return {
        "final_answer": response,
        "meditation_step": step + 1,
    }


def route_by_intent(state: GraphState) -> str:
    """Route after intent classification."""
    intent = state.get("intent", "CASUAL")
    if intent == "DISTRESS":
        return "query"
    elif intent in ["MEDITATION", "MEDITATION_CONTINUE"]:
        return "meditation"
    elif intent in [
        "QUERY",
        "FACTUAL",
        "RELATIONAL",
        "FOLLOW_UP",
        "ADVERSARIAL",
        "SAFETY_VIOLATION",
    ]:
        return "query"
    elif intent in ["ERROR"]:
        return "casual"
    else:
        return "casual"


def route_after_grading(state: GraphState) -> str:
    """Route after CRAG grading."""
    relevant = state.get("relevant_docs", [])
    rewrite_count = state.get("rewrite_count", 0)
    intent = state.get("intent", "FACTUAL")

    if intent in ["SAFETY_VIOLATION", "ADVERSARIAL"]:
        return "relevant"

    if relevant:
        if intent == "DISTRESS":
            return "distress"
        return "relevant"
    elif rewrite_count < settings.rag_max_rewrites:
        return "rewrite"
    else:
        if intent == "DISTRESS":
            return "distress"
        return "fallback"

