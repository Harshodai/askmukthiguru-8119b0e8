"""Lightweight domain routing for conversational answering.

Known worldly-query patterns mark a turn for general-knowledge mode so the
teacher-clip route cannot misattribute a retrieved passage as an answer. The
rule-based classifier is deliberately cheap and fail-open; it is a routing
hint, not a semantic safety classifier. Input safety and distress run before
this stage. Unknown requests still route to the general graph unless a
recognized teaching-domain cue specifically selects the first-person lane.
"""

from __future__ import annotations

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
    r"\b(write|draft|proofread|translate|summari[sz]e|rewrite|debug|troubleshoot|"
    r"fix|implement|build|create|generate|calculate|solve|code|program|script|"
    r"python|java|javascript|typescript|sql|trino|flink|pinot|kafka|docker|kubernetes|"
    r"api|http|json|yaml|github|git|stock\w*|share market|invest\w*|trading|"
    r"upcoming|schedule|schedules|register|registration|retreat|program dates|event dates|"
    r"crypto|bitcoin|mutual fund|portfolio|nifty|sensex|forex|loan|mortgage|tax|"
    r"diagnos\w*|prescrib\w*|dosage|antibiotic\w*|chemotherapy|election\w*|"
    r"president of|cricket|football|ipl|world cup|recipe|cook|flight booking|"
    r"hotel booking|weather|current price|latest news)\b",
    re.IGNORECASE,
)
_EXPLICIT_TEACHING_CUE_RE = re.compile(
    r"\b(what do the teachings say|what does .{0,40} teach|according to|as taught by|"
    r"recorded discourse|verbatim|exact quote|quote .{0,30} (?:krishnaji|preethaji)|"
    r"teachings? of sri|sri (?:krishnaji|preethaji)|krishnaji|preethaji)\b",
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


def should_skip_long_term_memory(query: str) -> bool:
    """Skip persistent profile/vault reads for plainly general, non-personal asks.

    Thread history remains available separately. Spiritual questions, explicit
    memory commands, personal-context requests, and terse referential follow-ups
    still receive cross-session memory. General coding/factual requests avoid
    DB/vault round trips that cannot plausibly personalize the answer.
    """
    text = " ".join(str(query or "").split())
    if not text:
        return False
    if _EXPLICIT_MEMORY_RE.search(text):
        return False
    if _GENERAL_TASK_RE.search(text) and not _EXPLICIT_TEACHING_CUE_RE.search(text):
        # A personal request for recommendations/preferences is memory-relevant;
        # ordinary task ownership ("fix my Python code") is not by itself.
        if re.search(r"\b(for me|based on my|my preference|my goal|my background|my job)\b", text, re.I):
            return False
        return True
    # Unknown asks and spiritual questions keep profile context, including
    # questions whose meaning depends on the user's practice or personal state.
    return False


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
        question = str(ctx.state.get("user_msg_en") or ctx.user_msg or "")
        if is_spiritual_domain_query(question) and not is_off_topic(question):
            return None
        # Unknown and non-doctrinal requests are general questions by default.
        # Only an explicit teaching request should enter the first-person route.
        ctx.state["general_knowledge_mode"] = True
        ctx.route_metadata.update({
            "requested_variant": "general_knowledge",
            "selected_variant": "general_knowledge",
            "decision_method": "off_topic_domain_router",
        })
        record_routing_decision(
            ctx,
            RoutingProvenance(
                layer="GENERAL_KNOWLEDGE_ROUTER",
                decision="general_knowledge",
                method="off_topic_domain_router",
                confidence=1.0,
                reason="Recognized non-doctrinal query routed to grounded general answering",
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
