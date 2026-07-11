"""Intent routing and short-circuit node handlers."""

from __future__ import annotations

import logging
import re

from rag.meditation import (
    format_meditation_response,
    get_distress_response,
    get_meditation_complete_message,
    is_meditation_complete,
    is_meditation_imperative,
    should_start_meditation,
)
from rag.prompts import CASUAL_SYSTEM_PROMPT, STIMULUS_RAG_PROMPT
from rag.states import GraphState
from services.serene_mind_engine import DistressAssessment, DistressLevel

from app.tracing import trace_rag_node
from . import _services
from .utils import _trace_update, get_node_timeout, log_metrics, settings

logger = logging.getLogger(__name__)

# LRU cache for intent classification (finding #33: proper LRU with TTL)
import time as _time
from collections import OrderedDict as _OrderedDict

_intent_classification_cache: _OrderedDict[str, tuple[str, str, float]] = _OrderedDict()
_INTENT_CACHE_MAX = 1000
_INTENT_CACHE_TTL = 3600  # 1 hour

# Query patterns live in rag.query_patterns so intent routing and graph
# selection pull from a single source. Aliased here with the original
# leading-underscore names so existing call sites are unchanged.
from rag.query_patterns import (
    DOCTRINE_CAPABILITY_PATTERNS as _CAPABILITY_PATTERNS,
    DOCTRINE_SIMPLE_PATTERNS as _SIMPLE_QUERY_PATTERNS,
    DOCTRINE_TEMPORAL_PATTERNS as _TEMPORAL_PATTERNS,
)
from rag.doc_utils import doc_text


def _cache_hint(intent: str) -> dict:
    """E3.1: emit cache_preferred hint for cache-friendly intents when enabled.

    The pipeline cache stage (CacheCheckStage) already short-circuits on hit
    regardless of intent. This hint is informational — it lets downstream
    observability / future cache-tier logic know the router expected a
    cacheable query. Minimal: only adds the key when the flag is on.
    """
    if not getattr(settings, "intent_prerouter_cache_hint_enabled", False):
        return {}
    if intent in ("FACTUAL", "CASUAL"):
        return {"cache_preferred": True}
    return {}


def _map_router_route_to_intent(route_name: str) -> tuple[str, str, bool] | None:
    """Map a SemanticRouter route label to the (intent, query_tier, needs_web_search) tuple
    that the rest of the pipeline expects.

    Keeping this mapping here (and small) is the only Python-side bridge between
    the data-driven YAML and the graph's intent vocabulary. Adding a new route
    requires (a) one line in this function, (b) the YAML definition. No other code change.
    """
    mapping = {
        "SAFETY_VIOLATION":  ("SAFETY_VIOLATION", "tier2_simple", False),
        "DISTRESS":          ("DISTRESS",         "tier2_simple", False),
        "MEDITATION":        ("MEDITATION",       "tier2_simple", False),
        "ADVERSARIAL":       ("ADVERSARIAL",      "tier3_complex", False),
        "TEMPORAL":          ("FACTUAL",          "tier3_complex", True),
        "CASUAL":            ("CASUAL",           "tier2_simple", False),
        "CAPABILITY":        ("FACTUAL",          "tier2_simple", False),
        "FACTUAL":           ("FACTUAL",          "tier2_simple", False),
    }
    return mapping.get(route_name)


@trace_rag_node("intent_router")
@log_metrics
async def intent_router(state: GraphState, config: dict = None) -> dict:
    """Classify user message -> DISTRESS / QUERY / CASUAL / ADVERSARIAL / SAFETY_VIOLATION."""
    try:
        return await _intent_router_impl(state, config)
    except Exception:
        logger.exception("Intent router failed, falling back to safe default")
        question = state.get("question", "")
        lower_q = question.lower()
        needs_web_search = False
        query_tier = "tier2_simple"
        intent = "FACTUAL"
        # Check distress keywords before defaulting to FACTUAL (finding #47)
        try:
            from services.serene_mind_engine import DistressLevel
            serene_mind = _services._serene_mind
            if serene_mind is not None:
                keyword_assessment = serene_mind.assess_distress(question, state.get("chat_history", []))
                if keyword_assessment.level >= DistressLevel.MODERATE:
                    intent = "DISTRESS"
                    query_tier = "tier2_simple"
        except Exception as e:
            logger.warning("Serene Mind distress check failed in fallback: %s", e)
            crisis_keywords = {
                "suicide", "suicidal", "kill myself", "want to die", "end my life", 
                "harm myself", "self harm", "depressed", "worthless", "hopeless", 
                "slit my wrist", "overdose", "jump off"
            }
            if any(kw in lower_q for kw in crisis_keywords):
                logger.warning("Crisis keyword matched in fallback-of-fallback. Routing to DISTRESS.")
                intent = "DISTRESS"
                query_tier = "tier2_simple"
        if any(pat in lower_q for pat in _TEMPORAL_PATTERNS):
            needs_web_search = True
            query_tier = "tier3_complex"
            logger.info("Intent Router Fallback: temporal pattern detected, enabling web search")
        return {
            "intent": intent,
            "query_tier": query_tier,
            "confidence_tier": "medium",
            "needs_web_search": needs_web_search,
            **_cache_hint(intent),
            "evaluation_trace": _trace_update(
                state, intent=intent, query_tier=query_tier,
                routing_reason="intent_fallback_with_distress_check",
                needs_web_search=needs_web_search
            ),
        }


# Out-of-corpus logistics queries — schedules, dates, prices, or registration for programs
# and events — have no answer in the teaching corpus, so the RAG path returns filler (the
# "upcoming programs from Ekam" failure). Detect them deterministically and short-circuit to a
# short honest pointer to ekam.org. A query must name an event/program noun AND a logistics cue
# to qualify, so teaching questions ("what is the beautiful state", "how do I practice soul
# sync") are never misrouted.
_LOGISTICS_EVENT_RE = re.compile(
    r"\b(programs?|events?|retreats?|workshops?|courses?|seminars?|webinars?|sessions?|classes|class)\b",
    re.I,
)
_LOGISTICS_CUE_RE = re.compile(
    r"\b(upcoming|schedules?|dates?|register|registration|signup|tickets?|price|pricing|cost|fees?|enrol|enroll|calendar)\b"
    r"|sign\s*up|when\s+(is|are|will)|how\s+much|book\s+a|next\s+\w",
    re.I,
)
_LOGISTICS_ANSWER = (
    "🙏 I don't have current schedules, dates, or prices for Ekam's programs and events — "
    "these change often, so I'd rather point you to the official source than guess. You'll "
    "find the latest on ekam.org. If it helps, I'm happy to share a teaching or practice to "
    "explore in the meantime."
)


def _is_logistics_query(question: str) -> bool:
    """True when the query asks about program/event logistics (not the teachings)."""
    return bool(_LOGISTICS_EVENT_RE.search(question) and _LOGISTICS_CUE_RE.search(question))


def _early_filter(
    question: str,
    lower_q: str,
    state: GraphState,
    serene_mind,
    meditation_step: int,
) -> dict | None:
    """1.14: Merge Serene Mind distress check, temporal check, and regex prerouter
    into a single early-exit helper so _intent_router_impl stays flat.

    Returns a routing dict if any fast-path fires, else None to continue.
    """
    # ---- Serene Mind Distress Check (Stage 1 keyword-only) ----
    if serene_mind is not None:
        chat_history = state.get("chat_history", [])
        try:
            from services.serene_mind_engine import DistressLevel
            keyword_assessment = serene_mind.assess_distress(question, chat_history)
            if keyword_assessment.level >= DistressLevel.MODERATE:
                logger.info(
                    "Intent Router: Serene Mind keyword detected %s distress "
                    "(confidence=%.2f), routing to DISTRESS",
                    keyword_assessment.level.name, keyword_assessment.confidence,
                )
                return {
                    "intent": "DISTRESS",
                    "query_tier": "tier2_simple",
                    "confidence_tier": "high",
                    "evaluation_trace": _trace_update(
                        state, intent="DISTRESS", query_tier="tier2_simple",
                        routing_reason="serene_mind_keyword_distress",
                        distress_level=keyword_assessment.level.name,
                        distress_confidence=keyword_assessment.confidence,
                        distress_signals=keyword_assessment.detected_signals,
                    ),
                }
        except Exception as e:
            logger.warning("Serene Mind keyword distress check failed: %s", e)
            crisis_keywords = {
                "suicide", "suicidal", "kill myself", "want to die", "end my life", 
                "harm myself", "self harm", "depressed", "worthless", "hopeless", 
                "slit my wrist", "overdose", "jump off"
            }
            if any(kw in lower_q for kw in crisis_keywords):
                logger.warning("Crisis keyword matched in fallback-of-fallback. Routing to DISTRESS.")
                return {
                    "intent": "DISTRESS",
                    "query_tier": "tier2_simple",
                    "confidence_tier": "high",
                    "evaluation_trace": _trace_update(
                        state, intent="DISTRESS", query_tier="tier2_simple",
                        routing_reason="fallback_of_fallback_keyword_distress",
                    ),
                }

    # ---- Temporal / Real-Time Query Check ----
    if any(pat in lower_q for pat in _TEMPORAL_PATTERNS):
        logger.info(
            "Intent Router: temporal query detected, flagging for web search: %s...",
            question[:60],
        )
        return {
            "intent": "FACTUAL",
            "query_tier": "tier3_complex",
            "confidence_tier": "low",
            "needs_web_search": True,
            "evaluation_trace": _trace_update(
                state, intent="FACTUAL", query_tier="tier3_complex",
                routing_reason="temporal_query_heuristic",
                needs_web_search=True,
            ),
        }

    # ---- Regex Pre-Router Check ----
    from rag.intent_prerouter import preroute_intent
    pre_intent = preroute_intent(question)
    if pre_intent:
        logger.info("Intent Router: Regex Pre-Router matched intent: %s", pre_intent)
        mapped_intent = "FACTUAL" if pre_intent == "QUERY" else pre_intent
        query_tier = "tier2_simple"
        return {
            "intent": mapped_intent,
            "query_tier": query_tier,
            "confidence_tier": "high" if mapped_intent != "CASUAL" else "medium",
            **_cache_hint(mapped_intent),
            "evaluation_trace": _trace_update(
                state, intent=mapped_intent, query_tier=query_tier,
                routing_reason="regex_prerouter",
            ),
        }

    return None


def _is_followup_heuristic(question: str, chat_history: list) -> bool:
    """Detect follow-up queries via pronoun/reference matching — no LLM call.

    Returns True when the current question looks like a reference to previous
    turns (pronouns, continuations, short referential queries) and there is
    enough conversation history to warrant treating it as a follow-up.
    """
    if not chat_history:
        return False

    lower_q = question.lower().strip()
    if not lower_q:
        return False

    # Follow-up phrases — multi-word patterns that strongly signal continuation
    followup_phrases = [
        "tell me more", "what about", "how about", "explain more",
        "go deeper", "say more", "tell me about that", "more about",
        "what does that mean", "what do you mean", "why is that",
        "how is that", "what about that", "can you elaborate",
        "can you tell me more", "elaborate on that", "tell me about it",
        "explain that", "tell me more about", "further explain",
        "go into more detail",
    ]
    for phrase in followup_phrases:
        if phrase in lower_q:
            return True

    # Referential single words — pronouns and deictic markers
    referential_words = {
        "it", "that", "this", "these", "those", "they", "them",
        "there", "more", "also", "further",
    }

    words = set(lower_q.split())
    ref_count = sum(1 for w in words if w in referential_words)

    # Short query (<= 8 words) with at least one referential word → likely follow-up
    if ref_count >= 1 and len(words) <= 8:
        return True

    # Query starts with a referential word + space → likely follow-up
    if lower_q.startswith(("that ", "this ", "those ", "these ", "it ", "they ")):
        return True

    return False


def _compute_complexity_score(question: str, chat_history: list[dict]) -> float:
    """Pure-Python multi-signal complexity score (0.0-1.0). <1ms, no LLM.

    Signals: question count, causal markers, entity density, word count,
    conversation depth. Sits at the entry boundary — augments, does not
    replace, the LLM classify_intent_and_complexity call.
    """
    words = question.split()
    word_count = min(len(words) / 20.0, 1.0)
    q_count = min((question.count("?") + question.count(";")) / 3.0, 1.0)
    lower_q = question.lower()
    causal_markers = ("why ", "how does", "how do ", "compare", "relationship between", "versus", "distinguish")
    causal = 1.0 if any(m in lower_q for m in causal_markers) else 0.0
    doctrine_entities = ("deeksha", "ekam", "soul sync", "four sacred secrets", "beautiful state",
                         "sri preethaji", "sri krishnaji", "aham", "golden light", "manifest 2026",
                         "universal intelligence", "spiritual vision", "inner truth", "oneness")
    entity_density = min(sum(1 for e in doctrine_entities if e in lower_q) / 3.0, 1.0)
    conv_depth = min(len(chat_history or []) / 10.0, 1.0)
    score = 0.20 * q_count + 0.35 * causal + 0.20 * entity_density + 0.10 * word_count + 0.15 * conv_depth
    return round(min(max(score, 0.0), 1.0), 3)


async def _intent_router_impl(state: GraphState, config: dict = None) -> dict:
    """Internal implementation of the intent router."""
    from rag.nodes.utils import emit_status
    await emit_status(config, "Understanding your question...")

    question = state["question"]
    lower_q = question.lower()
    complexity_score = _compute_complexity_score(question, state.get("chat_history", []))

    # Out-of-corpus logistics queries short-circuit BEFORE the pre-classified-intent echo
    # below: the pipeline coordinator's on-device classifier tags them FACTUAL, which sends
    # them into RAG and returns filler (the "upcoming programs from Ekam" failure). Return a
    # deterministic honest pointer to ekam.org instead.
    if _is_logistics_query(question):
        logger.info(
            "Intent Router: logistics/out-of-corpus query — honest pointer to ekam.org: %s",
            question[:60],
        )
        return {
            "intent": "CASUAL",
            "query_tier": "tier2_simple",
            "confidence_tier": "high",
            "complexity_score": complexity_score,
            "final_answer": _LOGISTICS_ANSWER,
            "evaluation_trace": _trace_update(
                state, intent="CASUAL", query_tier="tier2_simple",
                routing_reason="logistics_out_of_corpus", complexity_score=complexity_score,
            ),
        }

    # Pre-classified intent: pipeline_coordinator already ran on-device classifier
    pre_intent = state.get("intent")
    if pre_intent:
        _qt = state.get("query_tier", "tier2_simple")
        return {
            "intent": pre_intent,
            "query_tier": _qt,
            "complexity_score": complexity_score,
            "confidence_tier": (
                "high" if _qt in ("tier2_simple", "fast") and pre_intent != "CASUAL"
                else "low" if _qt == "tier3_complex"
                else "medium"
            ),
            **_cache_hint(pre_intent),
            "evaluation_trace": _trace_update(
                state, intent=pre_intent, query_tier=_qt,
                routing_reason="pre_classified_from_pipeline_coordinator",
                complexity_score=complexity_score
            ),
        }
    ollama = _services._ollama

    # Check if we're in an active meditation session (state machine check)
    raw_meditation_step = state.get("meditation_step", 0)
    try:
        meditation_step = int(raw_meditation_step)
    except (TypeError, ValueError):
        meditation_step = 0
    if meditation_step > 0:
        if is_meditation_complete(meditation_step):
            return {"intent": "CASUAL", "meditation_step": 0, "complexity_score": complexity_score}
        if should_start_meditation(question):
            return {"intent": "MEDITATION_CONTINUE", "meditation_step": meditation_step, "complexity_score": complexity_score}
        return {"intent": "CASUAL", "meditation_step": 0, "complexity_score": complexity_score}

    serene_mind = _services._serene_mind

    # ---- 1.14 Simplified Early Filter (merges Serene Mind + Temporal + Regex) ----
    early = _early_filter(question, lower_q, state, serene_mind, meditation_step)
    if early:
        early["complexity_score"] = complexity_score
        et = early.get("evaluation_trace")
        if isinstance(et, dict):
            et["complexity_score"] = complexity_score
        return early

    # ---- Heuristic Follow-up Detection (saves 1 LLM call per follow-up query) ----
    # When rag_heuristic_followup is True, detect pronouns/references to previous
    # queries using a cheap regex check instead of an LLM call. If detected,
    # assign FACTUAL/tier2_simple without going through the classifier.
    if (
        getattr(settings, "rag_heuristic_followup", False)
        and state.get("chat_history")
    ):
        followup = _is_followup_heuristic(question, state["chat_history"])
        if followup:
            logger.info(
                "Intent Router: heuristic follow-up detected — "
                "skipping LLM classifier, assigning FACTUAL/tier2_simple"
            )
            return {
                "intent": "FACTUAL",
                "query_tier": "tier2_simple",
                "complexity_score": complexity_score,
                "confidence_tier": "high",
                "follow_up_detected": True,
                **_cache_hint("FACTUAL"),
                "evaluation_trace": _trace_update(
                    state, intent="FACTUAL", query_tier="tier2_simple",
                    routing_reason="heuristic_followup",
                    follow_up_detected=True,
                    complexity_score=complexity_score,
                ),
            }

    # ---- YAML-driven Semantic Router (Phase A — replaces hardcoded keyword lists) ----
    # The SemanticRouter consults backend/config/router_routes.yaml: utterance
    # embeddings + regex safety nets + imperative/interrogative gates. It
    # subsumes the previous _CAPABILITY_PATTERNS, _SIMPLE_QUERY_PATTERNS, and
    # _TEMPORAL_PATTERNS hardcoded lists in this file by returning the right
    # intent + tier without any pattern matching in Python code.
    if getattr(settings, "use_semantic_router", True):
        try:
            from services.semantic_router import IntentSemanticRouter

            router = IntentSemanticRouter.get_default()
            router_match = router.classify(question, meditation_step=meditation_step)
        except Exception as exc:  # noqa: BLE001 — never block routing over a router error
            logger.debug("SemanticRouter classification failed (%s); falling back.", exc)
            router_match = None

        if router_match is not None:
            mapped = _map_router_route_to_intent(router_match.route)
            if mapped is not None:
                mapped_intent, query_tier, needs_web = mapped
                logger.info(
                    "Intent Router: SemanticRouter matched %s (score=%.3f, reason=%s) -> intent=%s",
                    router_match.route, router_match.score, router_match.reason, mapped_intent,
                )
                return {
                    "intent": mapped_intent,
                    "query_tier": query_tier,
                    "complexity_score": complexity_score,
                    "confidence_tier": (
                        "high" if query_tier in ("tier2_simple", "fast") and mapped_intent != "CASUAL"
                        else "low" if query_tier == "tier3_complex"
                        else "medium"
                    ),
                    "needs_web_search": needs_web,
                    **_cache_hint(mapped_intent),
                    "evaluation_trace": _trace_update(
                        state,
                        intent=mapped_intent,
                        query_tier=query_tier,
                        routing_reason=f"semantic_router_{router_match.reason}",
                        router_route=router_match.route,
                        router_score=router_match.score,
                        needs_web_search=needs_web,
                        complexity_score=complexity_score,
                    ),
                }

    # ---- Heuristic fast-path #1: capability / meta questions ----
    if any(kw in lower_q for kw in _CAPABILITY_PATTERNS):
        logger.info("Intent Router: heuristic fast-path — capability/meta question, fast")
        return {
            "intent": "FACTUAL",
            "query_tier": "tier2_simple",
            "complexity_score": complexity_score,
            "confidence_tier": "high",
            **_cache_hint("FACTUAL"),
            "evaluation_trace": _trace_update(
                state, intent="FACTUAL", query_tier="tier2_simple",
                routing_reason="heuristic_capability",
                complexity_score=complexity_score
            ),
        }

    # ---- Heuristic fast-path #2: pattern-based simple factual ----
    for pattern in _SIMPLE_QUERY_PATTERNS:
        if re.search(pattern, lower_q):
            logger.info(f"Intent Router: heuristic fast-path — simple factual match ({pattern}), fast")
            return {
                "intent": "FACTUAL",
                "query_tier": "tier2_simple",
                "complexity_score": complexity_score,
                "confidence_tier": "high",
                **_cache_hint("FACTUAL"),
                "evaluation_trace": _trace_update(
                    state, intent="FACTUAL", query_tier="tier2_simple",
                    routing_reason="heuristic_simple",
                    complexity_score=complexity_score
                ),
            }



    # ---- Cache check ----
    cache_key = lower_q.strip()
    if cache_key in _intent_classification_cache:
        entry = _intent_classification_cache[cache_key]
        cached_intent, cached_complexity, cached_ts = entry
        if _time.time() - cached_ts > _INTENT_CACHE_TTL:
            del _intent_classification_cache[cache_key]
        else:
            _intent_classification_cache.move_to_end(cache_key)  # LRU access
            if cached_intent == "QUERY":
                cached_intent = "FACTUAL"
            tier = "tier2_simple" if cached_complexity == "simple" else "tier3_complex"
            if cached_intent == "FACTUAL":
                logger.info(f"Intent Router: cache hit — {cached_intent} | {tier}")
            return {
                "intent": cached_intent,
                "query_tier": tier,
                "complexity_score": complexity_score,
                "confidence_tier": (
                    "high" if tier in ("tier2_simple", "fast") and cached_intent != "CASUAL"
                    else "low" if tier == "tier3_complex"
                    else "medium"
                ),
                **_cache_hint(cached_intent),
                "evaluation_trace": _trace_update(
                    state, intent=cached_intent, query_tier=tier,
                    routing_reason="cache_hit",
                    complexity_score=complexity_score
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
                "complexity_score": complexity_score,
                "confidence_tier": (
                    "high" if tier in ("tier2_simple", "fast") and intent != "CASUAL"
                    else "low" if tier == "tier3_complex"
                    else "medium"
                ),
                **_cache_hint(intent),
                "evaluation_trace": _trace_update(
                    state, intent=intent, query_tier=tier,
                    routing_reason=routing_reason,
                    complexity_score=complexity_score
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

    # ---- Meditation Hijack Guard (Phase A1.1) ----
    # An LLM-classified MEDITATION intent should only fire when the user is *actually*
    # asking to start (or continue) a meditation session. Interrogative queries that
    # merely *mention* meditation nouns ("Can I practice Soul Sync on Mars?",
    # "What is Serene Mind?", "Mera mind kaise badlu?") were leaking into the
    # meditation flow with step=0 and returning the misleading literal string
    # "The meditation is complete. Thank you for practicing with me." This guard
    # demotes MEDITATION → FACTUAL when there is no active session AND the user
    # message is not imperative.
    demote_enabled = getattr(settings, "intent_demote_meditation_on_interrogative", True)
    active_meditation = meditation_step > 0
    if intent == "MEDITATION" and demote_enabled and not active_meditation:
        if not is_meditation_imperative(question):
            logger.info(
                "Intent Router: demoting LLM-classified MEDITATION to FACTUAL "
                "(no active session, query is interrogative or non-imperative): '%s...'",
                question[:80],
            )
            intent = "FACTUAL"
            complexity = complexity or "simple"

    query_tier = None
    if intent == "FACTUAL":
        if complexity == "simple":
            query_tier = "tier2_simple"
        else:
            query_tier = "tier3_complex"

    # Store in cache
    # Store in cache with TTL timestamp
    _intent_classification_cache[cache_key] = (intent, complexity, _time.time())
    if len(_intent_classification_cache) > _INTENT_CACHE_MAX:
        _intent_classification_cache.popitem(last=False)  # FIFO eviction for OrderedDict

    logger.info(
        f"Intent Router: classified '{question[:80]}...' -> {intent} | tier -> {query_tier} (question_len={len(question)})"
    )
    return {
        "intent": intent,
        "query_tier": query_tier,
        "complexity_score": complexity_score,
        "confidence_tier": (
            "high" if query_tier in ("tier2_simple", "fast") and intent != "CASUAL"
            else "low" if query_tier == "tier3_complex"
            else "medium"
        ),
        **_cache_hint(intent),
        "evaluation_trace": _trace_update(
            state, intent=intent, query_tier=query_tier, routing_reason="classifier",
            complexity_score=complexity_score
        ),
    }


@trace_rag_node("handle_casual")
async def handle_casual(state: GraphState, config: dict = None) -> dict:
    """Handle casual conversation with multi-turn awareness.

    Belt-and-suspenders guard: if the query contains spiritual practice
    or doctrinal keywords, redirect to FACTUAL pipeline instead of
    returning a casual greeting. This prevents greeting responses for
    queries like "how do i practice soul sync" if LLM misclassifies.
    """
    if state.get("final_answer"):
        return {}  # answer already produced — write nothing (returning full state collides with parallel writers)

    _SPIRITUAL_PRACTICE_SIGNALS = [
        r"\bpractice\b", r"\bpracticing\b", r"\bhow\s+(do|can|should)\s+i\b",
        r"\bsoul\s+sync\b", r"\bdeeksha\b", r"\bmeditat", r"\bbeautiful\s+state\b",
        r"\bsacred\s+secret", r"\bconsciousness", r"\benlightenment\b",
        r"\boneness", r"\bekam\b", r"\bpreethaji\b", r"\bkrishnaji\b",
        r"\bteach\b", r"\bguide\b", r"\bguideline\b", r"\binstruction",
        r"\bstep", r"\bmethod\b", r"\bprocess\b", r"\bhow\s+to\b",
    ]
    lower = state.get("question", "").lower()
    if any(re.search(p, lower, re.I) for p in _SPIRITUAL_PRACTICE_SIGNALS):
        logger.info("handle_casual guard: query contains spiritual practice signals, redirecting to FACTUAL")
        return {
            "intent": "FACTUAL",
            "query_tier": "tier2_simple",
            "confidence_tier": "high",
            "evaluation_trace": _trace_update(
                state,
                handle_casual="redirected_to_factual",
                casual_redirect_reason="spiritual_practice_signals_detected"
            ),
        }

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


@trace_rag_node("handle_distress")
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
            f"[Source: {doc.get('title', 'Unknown')}]\n{doc_text(doc)}" for doc in relevant_docs[:3]
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


@trace_rag_node("handle_distress_check")
async def handle_distress_check(state: GraphState, config: dict = None) -> dict:
    """Lightweight keyword-based distress check running in parallel with intent_router."""
    question = state.get("question", "")
    serene_mind = _services._serene_mind
    if serene_mind is None:
        return {"parallel_distress_found": False}
    try:
        assessment = serene_mind.assess_distress(question, state.get("chat_history", []))
        if assessment.level >= DistressLevel.MODERATE:
            return {
                "parallel_distress_found": True,
                "parallel_distress_level": assessment.level.name,
            }
        return {"parallel_distress_found": False}
    except Exception:
        logger.warning("handle_distress_check failed", exc_info=True)
        return {"parallel_distress_found": False}


@trace_rag_node("handle_meditation")
async def handle_meditation(state: GraphState, config: dict = None) -> dict:
    """Continue an active meditation session, start a new one, or gracefully bail.

    Phase A1.1 fix — three-state behaviour:
      1. step <= 0 AND query is an imperative-to-start with a script keyword
         (soul sync / serene mind / generic meditation): emit the full script.
      2. step in [1, MAX_STEP]: advance the guided flow one step.
      3. step > MAX_STEP: emit the canonical "complete" close exactly once and
         reset the session.

    Crucially, if `step <= 0` AND no script keyword matched (i.e. the user is NOT
    actually asking to begin a meditation — they were mis-classified by the LLM),
    we DO NOT emit the legacy "The meditation is complete..." sentinel. Instead we
    set `_meditation_misroute=True` so the pipeline coordinator can fall back to the
    FACTUAL/QUERY path. This preserves the no-misleading-answer guarantee.
    """
    from rag.nodes.utils import emit_status
    await emit_status(config, "Guiding you into the practice...")

    raw_step = state.get("meditation_step", 0)
    try:
        step = int(raw_step)
    except (TypeError, ValueError):
        step = 0
    question = state.get("question", "").lower()
    from rag.meditation import MEDITATION_SCRIPTS

    start_step = getattr(settings, "meditation_start_step", 1)
    safe_fallback = getattr(settings, "meditation_safe_fallback", True)

    # ---- Case 1: starting a fresh meditation by name ------------------------
    # The script-keyword fast paths previously required step == 1 which made
    # them dead code on the first turn (step is 0 on fresh sessions). Accept
    # step <= start_step so the script fires on the very first invocation.
    fresh = step <= start_step
    from rag.meditation import _INTERROGATIVE_STEMS_EN, _INTERROGATIVE_STEMS_HINGLISH
    is_interrogative = question.endswith("?") or any(
        stem in question[:40] for stem in _INTERROGATIVE_STEMS_EN + _INTERROGATIVE_STEMS_HINGLISH
    )

    if fresh and not is_interrogative:
        if "soul sync" in question:
            script = MEDITATION_SCRIPTS["soul_sync"]
            response = f"**{script['title']}**\n\n" + "\n".join(
                f"{i + 1}. {s}" for i, s in enumerate(script["steps"])
            )
            return {"final_answer": response, "meditation_step": 0}

        if "serene mind" in question:
            script = MEDITATION_SCRIPTS["serene_mind"]
            response = f"**{script['title']}**\n\n" + "\n".join(
                f"{i + 1}. {s}" for i, s in enumerate(script["steps"])
            )
            return {"final_answer": response, "meditation_step": 0}

        if "meditation" in question:
            script = MEDITATION_SCRIPTS["serene_mind"]
            response = f"**{script['title']}**\n\n" + "\n".join(
                f"{i + 1}. {s}" for i, s in enumerate(script["steps"])
            )
            return {"final_answer": response, "meditation_step": 0}

    # ---- Case 2: step is within an active flow (1..MAX_STEP) ----------------
    formatted = format_meditation_response(step)
    if formatted is not None:
        return {
            "final_answer": formatted,
            "meditation_step": step + 1,
        }

    # ---- Case 3: step > MAX_STEP — session legitimately complete ------------
    if step > start_step:
        logger.info(
            "Meditation session complete (step=%s). Emitting canonical close.", step
        )
        return {
            "final_answer": get_meditation_complete_message(),
            "meditation_step": 0,
        }

    # ---- Case 4: step <= 0, no script keyword, no imperative ----------------
    # This is the Soul-Sync-on-Mars / hostile-takeover / Hinglish suffering hijack
    # path: an interrogative or off-domain query was mis-classified as MEDITATION
    # and reached this handler with no active session. Refuse to emit the
    # misleading "meditation is complete" sentinel.
    #
    # In normal operation the demote layer in `_intent_router_impl` catches these
    # queries before they reach this handler, so reaching this branch is itself a
    # signal of a routing bug. We log it loudly, emit a graceful clarifying
    # message that stays in character, and flag `_meditation_misroute=True` so
    # the pipeline coordinator can attribute the event to a routing failure.
    logger.warning(
        "Meditation handler reached with step<=0 and no script keyword. "
        "Query='%s...'. Signalling _meditation_misroute=True. This indicates "
        "the intent-router demote layer missed a non-imperative query.",
        question[:80],
    )
    if not safe_fallback:
        # Legacy behaviour gated behind a settings flag for backwards-compatibility.
        return {
            "final_answer": get_meditation_complete_message(),
            "meditation_step": 0,
        }
    soft_fallback = (
        "Beloved, I'm here with you. Would you like to share what's on your "
        "heart — a teaching you'd like to explore, or a guided practice to "
        "begin together? I am ready for either."
    )
    return {
        "final_answer": soft_fallback,
        "meditation_step": 0,
        "intent": "FACTUAL",
        "_meditation_misroute": True,
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
        "GUIDED_TOUR",
    ]:
        return "query"
    elif intent in ["ERROR"]:
        return "casual"
    else:
        return "casual"


def route_after_grading(state: GraphState) -> str:
    """Route after CRAG grading (merged with context sufficiency check)."""
    relevant = state.get("relevant_docs", [])
    rewrite_count = state.get("rewrite_count", 0)
    intent = state.get("intent", "FACTUAL")
    context_sufficient = state.get("_context_sufficient", True)

    if intent == "DISTRESS":
        return "distress"

    if intent in ["SAFETY_VIOLATION", "ADVERSARIAL"]:
        return "relevant"

    if relevant:
        if not context_sufficient and rewrite_count < settings.rag_max_rewrites:
            return "rewrite"
        return "relevant"
    elif rewrite_count < settings.rag_max_rewrites:
        return "rewrite"
    else:
        return "fallback"

