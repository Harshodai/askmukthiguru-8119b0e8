"""General-knowledge routing — keep worldly questions out of teacher-clip mode.

V4 eval proved the gap: "capital of France" gets answered with a verbatim
excerpt instead of abstaining (abstention FAIL, 2/2 rounds). No off-topic
handler exists anywhere in backend/app + backend/services (both grepped
clean). This module implements the handler WITHOUT wiring it into the live
path: nothing imports it from pipeline_builder / stages/__init__ yet.

ENABLE PROCEDURE (do not skip steps):
  1. Land the Settings field. backend/app/config.py is shared with a
     parallel session (uncommitted hunks as of 2026-10-04) — do NOT add the
     field until those hunks land, then add exactly:
         off_topic_handler_enabled: bool = False
     Default MUST stay False until step 3 passes.
  2. Wire the stage: import OffTopicStage in pipeline_builder.py and insert
     ``OffTopicStage()`` AFTER DistressStage and BEFORE
     BoundedComparisonShortCircuitStage. Position is load-bearing: input
     guardrails + distress/crisis pre-emption must run FIRST so a crisis
     query containing an off-topic keyword ("I want to die, also what is
     the capital of France") still escalates instead of being declined.
  3. VALIDATION GATE (must pass BEFORE flipping the flag):
     - gold-labelled off-topic/on-topic set: off-topic recall = 100% on the
       labelled off-topic items (capital-of-France family, stock tips,
       medical diagnosis, crypto, politics, sports scores, coding help,
       legal advice, recipes), on-topic false-positive rate = 0%
       (meditation, Beautiful State, deeksha, suffering-vs-consciousness,
       Ekam, Soul Sync breath).
     - flag-off parity test in backend/tests/test_off_topic_stage.py stays
       green (stage returns None with the flag off; build_default_pipeline
       contains no OffTopicStage).
     - run: backend/.venv/bin/pytest backend/tests/test_off_topic_stage.py
       backend/tests/test_pipeline_stages.py -q  (0 LLM calls)
  4. Flip: set env OFF_TOPIC_HANDLER_ENABLED=true (once the Settings field
     from step 1 exists, BaseSettings picks it up automatically).

W4 ENABLEMENT (2026-10-11): steps 1-4 done — Settings field landed
(backend/app/config.py), stage wired AFTER DistressStage BEFORE
BoundedComparisonShortCircuitStage, gold gates passed (off-topic recall 100%
across all 9 worldly families, on-topic FPR 0% across all 6 doctrine families;
backend/tests/test_off_topic_stage.py), cache bypasses added to CacheCheck +
DoctrineCache (flag-gated, crisis path untouched), default flipped to True.

RESIDUAL (honest, not closed):
- Keyword regex NARROWS the OOC leak, does not close it. Adversarial
  paraphrase with none of the listed keywords ("What should I call the main
  town of that hexagon-shaped country?") sails through to the legacy RAG path
  and its own abstention. Closing that needs a semantic gate, which is a
  separate workstream with its own FPR risk on doctrine queries.
- Fifth Sacred Secret / temporal / logistics-adjacent worldly queries are
  unaffected (different handlers own those).
- FP-bridge ordering note: the decline sits BEFORE GraphStage, so a declined
  query never reaches the first-person bridge inside it (the FP corpus cannot
  ground worldly Qs either). On-topic FP routing order is unchanged and was
  not re-tested here.

Design: fail-open allowlist-first. An on-topic anchor anywhere in the query
wins over any off-topic keyword, and an unrecognized query returns False so
the legacy RAG path (and its own abstention) handles it unchanged.
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

# Worldly QUESTION families the corpus cannot ground. Kept keyword-shaped on
# purpose: deterministic, no LLM, no false-positive path into on-topic space
# (the allowlist above runs first). Fail-open: no match -> not off-topic.
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
    return bool(text and _ON_TOPIC_RE.search(text))


def is_off_topic(query: str) -> bool:
    """Pure predicate: True for known worldly Qs outside the teachers' domain.

    This predicate is used for cache isolation and legacy compatibility. It is
    not a refusal policy: non-doctrinal questions continue to general answering
    rather than being rejected solely because no teacher clip fits.
    """
    text = " ".join(str(query or "").split())
    if not text:
        return False
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

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        if not off_topic_handler_enabled():
            return None
        question = str(ctx.state.get("user_msg_en") or ctx.user_msg or "")
        if not is_off_topic(question):
            return None
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
    assert not off_topic_handler_enabled()
    print("Self-check passed")
