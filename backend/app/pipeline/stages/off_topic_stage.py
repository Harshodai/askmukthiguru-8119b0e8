"""Lightweight domain routing for conversational answering.

Known worldly-query patterns mark a turn for general-knowledge mode so the
teacher-clip route cannot misattribute a retrieved passage as an answer. The
rule-based classifier is deliberately cheap and fail-open; it is a routing
hint, not a semantic safety classifier. Input safety and distress run before
this stage. Unknown requests still route to the general graph unless a
recognized teaching-domain cue specifically selects the first-person lane.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from app.pipeline.stages.base import Stage
from app.route_taxonomy import RoutingProvenance, record_routing_decision

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

# Default True since W4 enablement (2026-10-11): gold gates passed, see module
# docstring. Kill via env OFF_TOPIC_HANDLER_ENABLED=false. The getattr fallback
# below only fires if Settings ever drops the field (fail-closed to False).
OFF_TOPIC_HANDLER_ENABLED_DEFAULT = True


def off_topic_handler_enabled() -> bool:
    """Read the kill-switch flag; False unless Settings declares it True.

    getattr-fallback (F2 pattern from rag/memory.py): backend/app/config.py
    is owned by a parallel session, so no field is added here. Missing
    attribute -> default False -> zero behavior change.
    """
    from app.config import settings

    return bool(getattr(settings, "off_topic_handler_enabled", OFF_TOPIC_HANDLER_ENABLED_DEFAULT))


# On-topic anchors: the teachers' recorded-discourse domain. Any match wins
# over off-topic keywords below (checked first in is_off_topic).
_ON_TOPIC_RE = re.compile(
    r"\b(meditat\w*|contemplat\w*|beautiful state|deeksha|diksha|consciousness|"
    r"awaken\w*|enlighten\w*|stillness|inner (peace|child|journey|stillness|"
    r"awareness|state|self)|soul sync|soulsync|ekam|serene mind|krishnaji|"
    r"preethaji|mukthi|moksha|karma|dharma|self[ -]realisation|self[ -]realization|"
    r"oneness|divine|sacred|mantra|chant\w*|pray\w*|guru|suffer\w*|calm\w*|"
    r"\bpeace\b|mindful\w*|breath\w*|awareness|presence|gratitude|forgiv\w*|"
    r"compassion|anxiety|stress|anger|fear|relationship\w*|purpose|meaning of life|"
    r"liberat\w*|spiritual\w*|seek\w*|wisdom|teachings?|discourse\w*|practice\w*)\b",
    re.IGNORECASE,
)

# Explicit task/domain cues that mean a user wants a general answer or an action,
# even if the text happens to mention meditation, peace, or another spiritual
# word. This prevents one incidental teaching keyword from hijacking mixed
# requests (e.g. "debug my meditation app" or "stocks for an Ekam visit").
_GENERAL_TASK_RE = re.compile(
    # Explicit non-spiritual subject domains override incidental words such as
    # fear, peace, stress, or meditation. Explicit requests for recorded
    # teacher content still win in is_spiritual_domain_query().
    r"\b(python|java|javascript|typescript|sql|trino|flink|pinot|kafka|docker|"
    r"kubernetes|api|http|json|yaml|github|git|code|coding|programming|software|"
    r"traceback|stack trace|bug|unit test|debugging|stocks?|stock market|share market|"
    r"invest\w*|trading|crypto|bitcoin|mutual fund|portfolio|nifty|sensex|forex|"
    r"loan|mortgage|tax|diagnos\w*|prescrib\w*|dosage|antibiotic\w*|"
    r"chemotherapy|election\w*|president of|cricket|football|ipl|world cup|recipe|"
    r"cook\w*|flight booking|hotel booking|travel itinerary|trip planning|weather|"
    r"current price|latest news|resume|curriculum vitae|cover letter|job application|"
    r"interview preparation|salary negotiation|career path|performance review|"
    r"email|spreadsheet|presentation|project plan|business plan|marketing campaign|"
    r"poem|poetry|short story|fiction|blog post|essay|report|document formatting|"
    r"psycholog\w*|mental health|cognitive behavio[u]?ral|\bcbt\b|\bdbt\b|"
    r"psychotherap\w*|therap\w*|counsell?ing|psychiatr\w*|\bptsd\b|\bocd\b|"
    r"\badhd\b|neuroscience|neurobiology|brain science|clinical trial|"
    r"scientific evidence|research paper|systematic review|medical research|"
    r"physiology|biology|statistics|statistical|economics|sociology|"
    r"nutrition|calories|meal plan|workout|exercise plan|sleep disorder|"
    r"medication|medicine|side effects|symptom checklist)\b"
    r"|\b(?:write|draft|proofread|translate|summari[sz]e|rewrite|debug|troubleshoot|"
    r"fix|implement|build|create|generate|calculate|solve|code|program|script)\b"
    r".{0,50}\b(?:code|script|program|app|application|website|api|query|function|"
    r"traceback|software|email|letter|resume|document|report|essay|presentation|"
    r"spreadsheet|project plan|business plan|blog post|poem|story|recipe|budget)\b",
    re.IGNORECASE,
)
_EXPLICIT_TEACHING_CUE_RE = re.compile(
    r"\b(what do the teachings say|what does .{0,40} teach|according to (?:the )?"
    r"(?:teachings|sri krishnaji|sri preethaji|the gurus)|as taught by|recorded discourse|"
    r"verbatim|exact quote|quote .{0,30} (?:krishnaji|preethaji)|teachings? of sri|"
    r"sri (?:krishnaji|preethaji)|krishnaji|preethaji)\b",
    re.IGNORECASE,
)
# Only the overlap between everyday emotional/health questions and spiritual
# vocabulary needs semantic adjudication. Ordinary factual/coding requests stay
# on the deterministic fast path; explicit teacher/recorded-teaching requests
# stay on the verified first-person path.
_AMBIGUOUS_DOMAIN_RE = re.compile(
    r"\b(meditat\w*|breath\w*|anxiety|anxious|stress\w*|fear|afraid|anger|angry|"
    r"relationship\w*|purpose|meaning of life|inner peace|peace|compassion|"
    r"sleep|calm|suffer\w*|overwhelmed|panic|grief|healing|emotion\w*|"
    r"mindfulness|mindful|loneliness|lonely|self-worth|self esteem)\b",
    re.IGNORECASE,
)
_GUIDED_PRACTICE_RE = re.compile(
    r"\b(guide me|lead me through|walk me through|start (?:a )?meditation|"
    r"let(?:'s| us) meditate|breathing exercise|practice with me|"
    r"begin (?:a )?meditation|meditate with me)\b",
    re.IGNORECASE,
)


_EXPLICIT_MEMORY_RE = re.compile(
    r"\b(remember|memory|memories|recall|forget|what do you know about me|"
    r"what have i told you|as i said|i told you|we discussed|last time|earlier you said|"
    r"my preference|my preferences|my goal|my goals|my name|my background|my job|"
    r"my family|based on what i|based on my|personaliz\w*|continue that|"
    r"what about (?:that|it|those|the same|him|her|them)|recommend\w* .{0,20}for me)\b",
    re.IGNORECASE,
)
_PERSONAL_CONTEXT_RE = re.compile(
    r"\b(i feel|i'm feeling|i am feeling|i'm struggling|i am struggling|"
    r"my symptoms|my health|my relationship|my partner|my career|my goals?|"
    r"my background|my family|my preferences?|my job|my name|i live|i work|"
    r"i prefer|i like|i dislike|based on my|according to my situation)\b",
    re.IGNORECASE,
)


def should_skip_long_term_memory(query: str) -> bool:
    """Skip persistent profile/vault reads for general questions without personal intent.

    Thread history remains available separately. Explicit memory commands,
    personal-context requests, and spiritual questions still receive cross-session
    memory. Plain general facts/coding tasks avoid irrelevant DB/vault round trips.
    """
    text = " ".join(str(query or "").split())
    if not text:
        return False
    if _EXPLICIT_MEMORY_RE.search(text) or _PERSONAL_CONTEXT_RE.search(text):
        return False
    if is_spiritual_domain_query(text):
        return False
    # Non-doctrinal and unclassified questions should not pay cross-session
    # memory cost unless their text indicates personal or referential relevance.
    return True


# Worldly QUESTION families the corpus cannot ground. Kept keyword-shaped on
# purpose: deterministic, no LLM. The general-task gate below takes precedence
# unless the user explicitly asks what a teacher said.
_OFF_TOPIC_RE = re.compile(
    r"\b(capital of|population of|tallest|longest river|which country|what country|"
    r"president of|prime minister of|stock\w*|share market|invest\w*|trading|"
    r"crypto|bitcoin|mutual fund|portfolio|nifty|sensex|intraday|forex|loan\b|"
    r"interest rate|tax filing|diagnos\w*|prescrib\w*|dosage|antibiotic\w*|"
    r"chemotherapy|tumou?r\b|cancer treatment|blood pressure|what disease|"
    r"election\w*|vote for|political party|\bbjp\b|congress\b|modi\b|trump\b|"
    r"parliament|minister\b|cricket|football\b|ipl\b|world cup|match score|"
    r"write (me )?code|debug\w*|sql query|javascript|python (code|script)|"
    r"leetcode|api error|lawsuit|\bsue\b|divorce law|property dispute|legal advice|"
    r"recipe\w*|cook\w*|movie\w*|celebrity|flight booking|hotel booking|"
    r"weather in|exam syllabus|math problem|homework|olympics)\b",
    re.IGNORECASE,
)


def is_spiritual_domain_query(query: str) -> bool:
    """Return whether a message contains a recognizable spiritual-teaching cue.

    This is a routing hint, not a safety classifier or a claim that the
    retrieved corpus can answer the question. Unknown/general questions must
    be allowed to use the general answer path.
    """
    text = " ".join(str(query or "").split())
    if not text:
        return False
    if _GENERAL_TASK_RE.search(text) and not _EXPLICIT_TEACHING_CUE_RE.search(text):
        return False
    return bool(_ON_TOPIC_RE.search(text))


def is_off_topic(query: str) -> bool:
    """Pure predicate: True for known worldly Qs outside the teachers' domain.

    This predicate is used for cache isolation and legacy compatibility. It is
    not a refusal policy: non-doctrinal questions continue to general answering
    rather than being rejected solely because no teacher clip fits.
    """
    text = " ".join(str(query or "").split())
    if not text:
        return False
    if _EXPLICIT_TEACHING_CUE_RE.search(text):
        return False
    if _GENERAL_TASK_RE.search(text):
        return True
    if _ON_TOPIC_RE.search(text):
        return False
    return bool(_OFF_TOPIC_RE.search(text))


def build_off_topic_response() -> str:
    """Honest refuse-and-redirect copy. No quoted teachings, no guessing."""
    return (
        "That is outside what I can speak to from the recorded discourses. "
        "The teachers have not spoken about this in the teachings I can verify, "
        "so I will not guess an answer here.\n\n"
        "Mukthi Guru shares the wisdom of Sri Preethaji and Sri Krishnaji on "
        "the inner journey \u2014 the Beautiful State, meditation and "
        "contemplation, deeksha, and living in calm awareness. If any of those "
        "would help, please ask, and I will answer from the verified teachings."
    )


class OffTopicStage(Stage):
    """Route recognized non-doctrinal questions to grounded general answering.

    Distress preemption runs before this stage. A worldly query is not itself
    a reason to refuse: flag it so the general graph can answer without the
    first-person teaching-clip router treating a topic match as teacher speech.
    """

    name = "off_topic_short_circuit"

    async def run(self, ctx: PipelineContext) -> None:
        if not off_topic_handler_enabled():
            return None

        question = str(ctx.state.get("user_msg_en") or ctx.user_msg or "").strip()
        explicit_teaching = bool(_EXPLICIT_TEACHING_CUE_RE.search(question))
        spiritual_candidate = is_spiritual_domain_query(question) and not is_off_topic(question)

        # Explicit source/teacher requests must never be redirected by the
        # semantic router. Guided-practice imperatives belong to the dedicated
        # meditation stage, and crisis detection already preempts this stage.
        if explicit_teaching or _GUIDED_PRACTICE_RE.search(question):
            ctx.route_metadata.setdefault("domain_route", "teaching" if explicit_teaching else "guided_practice")
            return None

        ambiguous = spiritual_candidate and bool(_AMBIGUOUS_DOMAIN_RE.search(question))
        if ambiguous:
            decision = None
            try:
                from app.config import settings

                if getattr(settings, "intent_router_ambiguous_domain_enabled", True):
                    from services.jev_router_service import JevRouterService

                    timeout_s = float(
                        getattr(settings, "intent_router_ambiguous_domain_timeout_s", 0.45)
                    )
                    router = JevRouterService(timeout_s=timeout_s)
                    decision = await asyncio.wait_for(router.classify(question), timeout=timeout_s)
            except Exception as exc:
                # A router failure is not permission to invent a teacher source.
                # Ambiguous non-explicit turns safely use the neutral answer lane.
                logger.info(
                    "Ambiguous-domain Jev fallback trace_id=%s reason=%s",
                    ctx.trace_id,
                    type(exc).__name__,
                )

            route = str((decision or {}).get("domain_route") or "")
            if route == "teaching":
                ctx.state["general_knowledge_mode"] = False
                ctx.state["domain_route"] = "teaching"
                ctx.route_metadata.update({
                    "requested_variant": "first_person",
                    "selected_variant": "first_person",
                    "decision_method": "jev_ambiguous_domain",
                    "router_confidence": (decision or {}).get("confidence"),
                })
                record_routing_decision(
                    ctx,
                    RoutingProvenance(
                        layer="GENERAL_KNOWLEDGE_ROUTER",
                        decision="teaching",
                        method="jev_ambiguous_domain",
                        confidence=float((decision or {}).get("confidence", 0.0)),
                        reason="Structured router selected the recorded-teaching domain",
                    ),
                )
                logger.info("Ambiguous-domain route=teaching trace_id=%s", ctx.trace_id)
                return None

            # Only general/live research can be accepted from a semantic decision.
            # A logistics-only decision is not allowed to open a disabled route.
            if route in {"general", "live_research"}:
                needs_web_search = bool((decision or {}).get("needs_web_search"))
                ctx.state["general_knowledge_mode"] = True
                ctx.state["domain_route"] = route
                ctx.state["needs_web_search"] = needs_web_search
                ctx.preclassified_intent = "FACTUAL"
                ctx.preclassified_tier = str((decision or {}).get("query_tier") or "tier2_simple")
                ctx.preclassified_reason = "jev_ambiguous_domain"
                ctx.route_metadata.update({
                    "requested_variant": "general_knowledge",
                    "selected_variant": "general_knowledge",
                    "decision_method": "jev_ambiguous_domain",
                    "domain_route": route,
                    "router_confidence": (decision or {}).get("confidence"),
                    "needs_web_search": needs_web_search,
                })
                record_routing_decision(
                    ctx,
                    RoutingProvenance(
                        layer="GENERAL_KNOWLEDGE_ROUTER",
                        decision=route,
                        method="jev_ambiguous_domain",
                        confidence=float((decision or {}).get("confidence", 0.0)),
                        reason="Structured router selected a neutral general-answer domain",
                    ),
                )
                logger.info(
                    "Ambiguous-domain route=%s trace_id=%s router_latency_ms=%s",
                    route,
                    ctx.trace_id,
                    (decision or {}).get("latency_ms"),
                )
                return None

            # Low confidence, missing API key, timeout, and unsupported intent
            # all fail closed to general knowledge for an ambiguous request.
            # This avoids assigning teacher attribution based on one keyword.
            route = "general"
            method = "ambiguous_domain_safe_fallback"
            ctx.state["general_knowledge_mode"] = True
            ctx.state["domain_route"] = route
            ctx.state["needs_web_search"] = False
            ctx.preclassified_intent = "FACTUAL"
            ctx.preclassified_tier = "tier2_simple"
            ctx.preclassified_reason = method
            ctx.route_metadata.update({
                "requested_variant": "general_knowledge",
                "selected_variant": "general_knowledge",
                "decision_method": method,
                "domain_route": route,
                "router_confidence": None,
                "needs_web_search": False,
            })
            record_routing_decision(
                ctx,
                RoutingProvenance(
                    layer="GENERAL_KNOWLEDGE_ROUTER",
                    decision=route,
                    method=method,
                    confidence=0.0,
                    reason="Ambiguous query had no usable semantic route; avoid unsupported teacher attribution",
                ),
            )
            return None

        if spiritual_candidate:
            ctx.route_metadata.setdefault("domain_route", "teaching")
            return None

        # Unknown and non-doctrinal requests use the general answer graph.
        ctx.state["general_knowledge_mode"] = True
        ctx.state.setdefault("domain_route", "general")
        ctx.route_metadata.update({
            "requested_variant": "general_knowledge",
            "selected_variant": "general_knowledge",
            "decision_method": "off_topic_domain_router",
            "domain_route": "general",
        })
        record_routing_decision(
            ctx,
            RoutingProvenance(
                layer="GENERAL_KNOWLEDGE_ROUTER",
                decision="general_knowledge",
                method="off_topic_domain_router",
                confidence=1.0,
                reason="Recognized non-doctrinal or unknown query routed to grounded general answering",
            ),
        )
        logger.info("General-knowledge route selected trace_id=%s", ctx.trace_id)
        return None


if __name__ == "__main__":
    assert is_off_topic("What is the capital of France?")
    assert is_off_topic("Give me stock tips for next week")
    assert is_off_topic("Can you diagnose my chest pain?")
    assert not is_off_topic("What is meditation?")
    assert not is_off_topic("What is the Beautiful State?")
    assert not is_off_topic("What is deeksha?")
    assert not is_off_topic("")
    assert is_spiritual_domain_query("What is meditation?")
    assert not is_spiritual_domain_query("How do I debug a Python traceback?")
    assert off_topic_handler_enabled()
    print("Self-check passed")
