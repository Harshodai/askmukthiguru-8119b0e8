"""Distress stage — Serene Mind detection + proactive trigger.

Bodies extracted verbatim from PipelineCoordinator._detect_distress and
_maybe_trigger_proactive_serene_mind, plus the distress-keyword pre-screen
and proactive-state glue that lived inline in ``execute()``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING

from app.config import settings
from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage
from app.release_manifest import get_release_manifest
from app.route_taxonomy import RoutingProvenance, record_routing_decision
from services.safety_telemetry import log_crisis_referral_shown, log_tier_escalation
from services.serene_mind_engine import (
    DISTRESS_RESPONSES,
    HINDI_CRISIS_COPY_STATUS,
    INDIC_CRISIS_RESPONSES,
    INDIC_NEXT_STEPS,
    SEVERE_IDEATION_CHECKIN_RESPONSE,
    THIRD_PARTY_CRISIS_RESPONSE,
    DistressAssessment,
    DistressLevel,
    SereneMindEngine,
    get_crisis_resource,
    get_non_english_crisis_patterns,
)

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

# Distress keyword pre-screen — only triggers full analysis when present.
# CRIT-5: `suffering`/`pain` removed (verified false positives on doctrinal
# queries — "What is the relationship between suffering and consciousness?"
# — and medical queries — "I feel a sharp pain in my chest").
# Indic acute crisis keywords added; sources:
#   - ICHI Mental Health Glossary (hi/ta/te/mr)
#   - AIIMS suicide-prevention resources (hi/te/mr)
#   - Bangladesh suicide-prevention helplines (bn)
#   - IndicNLP suicide/self-harm corpus keywords (hi/ta/mr/bn)
# Devanagari/Bengali/Tamil/Telugu marks (virama, nukta, matras) are not \w,
# so \b boundaries FAIL on Indic scripts — matched as plain substrings.
_DISTRESS_KEYWORD_RE = re.compile(
    r"\b(suicid|kill\s*my|want\s*to\s*die|end\s*my\s*life|hurt\s*my|self[-\s]*harm|"
    r"hopeless|crying|panic|anxiety|depress|grief|alone|miserable|worthless|"
    r"helpless|nobody\s*cares|no\s*point|give\s*up|can'?t\s*go\s*on|overwhelm|"
    # 2026-10-05: spelled-out negation and passive ideation (live rt5a/rt5b).
    r"can\s*not\s*go\s*on|cant\s*go\s*on|can\u2019t\s*go\s*on|disappear|vanish|"
    r"not\s*exist|take\s*it\s*any\s*more|"
    r"afraid|scared|terrif|agony|desper|broken|tut\s*chuk|"
    r"akela|kashtam|dukh|takleef|udas)\b",
    re.IGNORECASE,
)

# Acute Indic self-harm / suicide pre-screen.
#
# STRUCTURAL FIX (2026-09-27): this used to be its own hand-typed keyword
# tuple, maintained completely independently of
# services.serene_mind_engine._ALL_PATTERNS (the actual classifier). Two
# independently hand-maintained lists for the same phrases WILL drift — the
# concrete bug found: this list had the romanized Kannada spelling
# "saayabeku" (double-a), but serene_mind_engine's own `_KN_ROMANIZED_PATTERNS`
# only had "sayabeku" (single-a), so a message matching this pre-screen never
# actually escalated to CRISIS in assess_distress() — the pre-screen fired,
# `has_distress_keywords` was True, but the real classification silently
# disagreed. That class of divergence is now structurally impossible: this
# pre-screen is DERIVED from the exact same compiled CRISIS patterns
# assess_distress() itself uses (`get_non_english_crisis_patterns()`), so
# every crisis phrase the classifier recognizes is automatically covered
# here too, with no second edit and no way for the two to disagree.
#
# Original data-source note, preserved for provenance: the pre-screen
# keywords originally came from ICHI Mental Health Glossary (hi/ta/te/mr),
# AIIMS suicide-prevention resources (hi/te/mr), Bangladesh suicide-prevention
# helplines (bn), IndicNLP suicide/self-harm corpus keywords (hi/ta/mr/bn),
# NIMHANS suicide prevention glossary (Kannada), iCall/Vandrevala Foundation
# crisis line materials (Malayalam), ICHI Mental Health Glossary updates 2025
# — all of which now live directly in serene_mind_engine.py's per-language
# CRISIS pattern lists (the single source of truth) rather than duplicated
# here.
_INDIC_CRISIS_PATTERNS: tuple[re.Pattern, ...] = tuple(get_non_english_crisis_patterns())


def _indic_crisis_keyword_search(text: str) -> re.Match | None:
    for pattern in _INDIC_CRISIS_PATTERNS:
        match = pattern.search(text)
        if match:
            return match
    return None


def has_crisis_keywords(text: str) -> bool:
    """Cheap (<1ms) crisis-keyword pre-screen for use OUTSIDE the pipeline.

    Checks the same patterns DistressStage.run() uses as its pre-screen:
    `_DISTRESS_KEYWORD_RE` (English — broad, MILD-through-CRISIS distress
    words, not acute-only) OR'd with `_indic_crisis_keyword_search` (Indic
    scripts and romanized forms — the exact CRISIS patterns
    assess_distress() uses, see `get_non_english_crisis_patterns()`). A True
    result does NOT mean the message is actually crisis-level; it means
    DistressStage's own pre-screen would also fire, so an admission gate
    must not reject the request without giving DistressStage a chance to
    run its full assess_distress() and decide. Admission gates that reject a
    request BEFORE the pipeline runs (e.g. chat.py's conversation-context-limit
    check) must call this first and let a match through regardless of the
    rejection reason — the pipeline's own DistressStage is where the actual
    crisis-preemption response is built, and it must never be skippable by
    hitting an unrelated admission gate. Not a substitute for the full
    assess_distress() call DistressStage runs.
    """
    if _DISTRESS_KEYWORD_RE.search(text) or _indic_crisis_keyword_search(text):
        return True
    # 2026-10-08: the lists above drifted from assess_distress and missed 34 of
    # 38 implicit-ideation probes, so a cache hit or a 409 could pre-empt
    # DistressStage. Anything it would pre-empt (SEVERE+) trips this too.
    # Regex only, under 1 ms; fails closed.
    try:
        return SereneMindEngine().assess_distress(text).level >= DistressLevel.SEVERE
    except Exception:
        logger.exception("Crisis pre-screen assessment failed; treating as a match.")
        return True


_SEVERE_SECOND_OPINION_SYSTEM = (
    "You screen messages sent to a spiritual-teachings assistant. Decide whether the writer "
    "is describing THEIR OWN current emotional pain, hopelessness, feeling broken, or wanting "
    "to give up on life (answer PERSONAL), or is asking about a topic, a teaching, another "
    "person, or an object (answer TOPIC). If there is any doubt, answer PERSONAL. "
    "Reply with exactly one word: PERSONAL or TOPIC."
)

# 2026-09-28 (owner-approved "escalate-only + re-tier", Task 3). Used only by
# `_maybe_llm_escalate_below_crisis`, behind `distress_llm_escalation_enabled`
# (default False). AI-AUTHORED, PENDING-CLINICIAN-REVIEW.
_ESCALATION_SYSTEM_PROMPT = (
    "You are a careful multilingual safety classifier for a spiritual-teachings "
    "assistant. The message may be in any language, including Hindi, Marathi, Tamil, "
    "Telugu, Kannada, Malayalam, Bengali, Gujarati, Punjabi, or a romanized "
    "(Latin-script) version of any of these. Decide the level of suicide/self-harm "
    "risk the message expresses:\n"
    "CRISIS — a stated intent, plan, method, or timeframe for ending one's life or "
    "self-harm (e.g. naming a time like tonight/tomorrow, a method like pills, or a "
    'decisive plan verb like "I\'m going to" / "I will").\n'
    "SEVERE — clear passive suicidal ideation or hopelessness about living, with NO "
    'stated plan, method, or timeframe (e.g. "I wish I could just disappear").\n'
    "MODERATE — significant emotional distress without ideation.\n"
    "MILD — mild stress or discomfort.\n"
    "NONE — no distress signal (includes ordinary questions about doctrine, death, "
    'or the body that are not personal, e.g. "what does moksha mean").\n'
    "If there is genuine doubt between two levels, choose the HIGHER one. "
    "Reply with exactly one word: NONE, MILD, MODERATE, SEVERE, or CRISIS."
)


class DistressStage(Stage):
    """Run deterministic distress detection and preempt severe/crisis paths.

    Moderate and mild distress can continue to the compassionate RAG path.
    Severe and crisis assessments terminate here so no retrieval, provider call,
    translation, memory write, or cache write can precede human support.
    """

    name = "distress_detection"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        user_msg_en = ctx.state["user_msg_en"]
        state = ctx.state

        # CRIT-5: pre-screen BOTH the translated EN text and the raw original
        # message, so an acute Indic crisis keyword is never missed because
        # translation softened it. raw falls back to user_msg_en (which is
        # already English for Indic-preferred users) when ctx.user_msg is
        # unavailable (e.g. direct stage tests use SimpleNamespace).
        raw = getattr(ctx, "user_msg", None) or user_msg_en
        has_en_keyword = bool(_DISTRESS_KEYWORD_RE.search(user_msg_en))
        has_indic_keyword = bool(_indic_crisis_keyword_search(raw))
        # Fail-closed signal from InputGuardrailStage: its self_harm topic
        # rail (guardrails/lightweight_handler._BLOCKED_TOPICS["self_harm"])
        # already matched this message. That match is authoritative on its
        # own — it must NOT depend on assess_distress's own (different,
        # narrower) pattern set also matching, which is exactly the 2026-09-27
        # regression ("I am suicidal" etc. matched the guardrail but scored
        # DistressLevel.NONE here, silently downgrading to a helpline-less
        # response).
        guardrail_self_harm = bool(state.get("guardrail_self_harm_match"))
        ctx.has_distress_keywords = has_en_keyword or has_indic_keyword or guardrail_self_harm

        # Assess unconditionally. Keyword-gating this let question-framed
        # ideation ("how do i stop wanting to die") skip detection entirely —
        # the pre-screen regex misses it exactly as the crisis phrasings did.
        # assess_distress is pure regex (<1ms), so running it every turn is cheap.
        assessment = await self._detect_distress(ctx, user_msg_en, state)
        if raw != user_msg_en:
            # Translation can only soften acute Indic ideation, never add it: also
            # classify the seeker's own words and keep the higher level.
            try:
                raw_assessment = SereneMindEngine().assess_distress(raw)
                current = getattr(getattr(assessment, "level", None), "value", None)
                if assessment is None or (
                    isinstance(current, int) and int(raw_assessment.level) > current
                ):
                    assessment = raw_assessment
            except Exception:
                logger.warning("Raw-text distress assessment failed; keeping translated result.")
        if guardrail_self_harm:
            # Force CRISIS unconditionally — never downgraded, and the LLM
            # second opinion (which may only lower SEVERE->MODERATE) must
            # never see this assessment at all, so it can't touch it either.
            if assessment is None:
                assessment = DistressAssessment(
                    level=DistressLevel.CRISIS,
                    confidence=1.0,
                    detected_signals=["[guardrail] self_harm topic match"],
                    recommended_response_type="crisis",
                )
            elif assessment.level < DistressLevel.CRISIS:
                assessment.level = DistressLevel.CRISIS
                assessment.confidence = max(assessment.confidence, 1.0)
                assessment.recommended_response_type = "crisis"
                assessment.detected_signals.append("[guardrail] self_harm topic match")
        elif state.get("guardrail_block_deferred_to_distress"):
            # InputGuardrailStage deferred a topic block here because the
            # message scored SEVERE+. Keep it at SEVERE+ (no LLM downgrade):
            # falling below would send the blocked question on to the graph.
            if assessment is None or assessment.level < DistressLevel.SEVERE:
                assessment = DistressAssessment(
                    level=DistressLevel.SEVERE,
                    confidence=1.0,
                    detected_signals=["[guardrail] blocked topic deferred at SEVERE+"],
                    recommended_response_type="crisis",
                )
        else:
            assessment = await self._maybe_llm_downgrade_severe(ctx, user_msg_en, assessment, state)
            # Escalate-only (owner-approved 2026-09-28, Task 3), OFF by
            # default. Only reachable here because the guardrail_self_harm
            # branch above already returns/short-circuits its own CRISIS —
            # a regex-CRISIS message from either branch's outcome is caught
            # by the level check inside the method itself, so it never waits
            # on an LLM call.
            assessment = await self._maybe_llm_escalate_below_crisis(
                ctx, user_msg_en, assessment, state
            )
        ctx.assessment = assessment

        level_value = getattr(getattr(assessment, "level", None), "value", -1)
        if not isinstance(level_value, int):
            level_value = -1
        self._maybe_log_tier_escalation(ctx, assessment, level_value, state)
        if assessment and level_value >= DistressLevel.SEVERE.value:
            return await self._crisis_preemption_result(ctx, assessment)
        # ponytail: proactive Serene Mind block from execute() verbatim.
        # Trigger on a keyword hit, a persistent distress trend, OR a positive
        # assessment this turn — so a crisis with no listed keyword still routes.
        proactive_data = None
        if (
            ctx.has_distress_keywords
            or state.get("distress_history")
            or (assessment and level_value >= DistressLevel.MODERATE.value)
        ):
            proactive_data = await self._maybe_trigger_proactive_serene_mind(
                ctx, assessment, ctx.user_id, ctx.request, state
            )
        if proactive_data:
            state["proactive_serene_mind"] = proactive_data
        ctx.proactive_data = proactive_data
        return None

    @staticmethod
    def _maybe_log_tier_escalation(ctx, assessment, level_value: int, state: dict) -> None:
        """Log a safety event when this turn's level is higher than the last
        recorded one. Defensive: distress_history's shape is owned elsewhere
        (rag/states.py) and this must never raise on an unexpected entry —
        an observability gap is acceptable, a crashed safety stage is not.
        """
        if not assessment or level_value < 0:
            return
        history = state.get("distress_history") or []
        if not history:
            return
        try:
            prev_name = history[-1].get("level") if isinstance(history[-1], dict) else None
            if not prev_name:
                return
            prev_value = DistressLevel[prev_name].value
        except (KeyError, AttributeError, TypeError):
            return
        if level_value > prev_value:
            log_tier_escalation(
                trace_id=getattr(ctx, "trace_id", ""),
                from_level=prev_name,
                to_level=assessment.level.name,
            )

    @staticmethod
    async def _crisis_preemption_result(
        ctx: PipelineContext, assessment: DistressAssessment
    ) -> PipelineResult:
        """Return reviewed support before any model or persistence side effect."""
        level = assessment.level
        response_type = getattr(assessment, "recommended_response_type", None)
        if response_type == "third_party_crisis":
            # AI-AUTHORED, PENDING-CLINICIAN-REVIEW (see W2 review packet):
            # a helper-oriented response — never "are you safe right now",
            # which is meaningless addressed to someone worried about a
            # THIRD party, not themselves.
            prefix = THIRD_PARTY_CRISIS_RESPONSE
            next_step = (
                "If you're not sure whether it's urgent, it's always okay to "
                "err on the side of reaching out for help — you don't have to "
                "carry this alone either."
            )
        elif response_type == "severe_ideation_checkin":
            # 2026-09-28 (owner-approved re-tier, Task 1). AI-AUTHORED,
            # PENDING-CLINICIAN-REVIEW (see W2 review packet): passive
            # ideation / ambiguous spiritual framing with no stated plan,
            # method, or timeframe gets a gentle check-in, not the full
            # "are you safe right now" CRISIS-style copy.
            prefix = SEVERE_IDEATION_CHECKIN_RESPONSE
            next_step = (
                "If at any point you feel unsafe or the thought of harming "
                "yourself gets stronger, please reach out to one of the "
                "numbers shown above right away — I'm still here with you."
            )
        else:
            prefix = DISTRESS_RESPONSES.get(level, DISTRESS_RESPONSES[DistressLevel.CRISIS])
            next_step = (
                "If you are in immediate danger, please contact local emergency services "
                "or go to a safer place now. If you can, tell a trusted person nearby "
                "that you need support."
            )
        resources = get_crisis_resource("global")
        # Resources (helpline numbers/shortcodes) MUST appear in the first 200
        # characters of a SEVERE/CRISIS response (see docs/INTEGRATION_GUIDE.md,
        # evaluation/datasets/mukthi_guru_v1.yaml, evaluation/rubrics/
        # refusal_correctness.yaml) — DISTRESS_RESPONSES[SEVERE]'s prefix alone
        # runs well past 200 chars, so resources must lead, not follow.
        #
        # 2026-09-28 (owner decision, translation safety check): this used to
        # run `prefix`/`next_step` through ctx.container.translation.translate_text()
        # for Indic-preferred users. Since the other session made translation
        # real on LLM_PROVIDER=openrouter (gemini_translation_enabled=True by
        # default, live via Gemini-through-OpenRouter), that meant this
        # safety-critical copy — "Are you safe right now, or are you thinking
        # about harming yourself?" — was being rewritten by a live,
        # nondeterministic LLM call with no review gate, every single time.
        # Owner decision: crisis/SEVERE/third-party copy is ALWAYS the fixed,
        # reviewed English string — never runtime LLM translation, for any
        # seeker, any language. The helpline resource block was already never
        # translated (kept in clean ASCII so phone numbers and SMS shortcodes
        # like "Text HOME to 741741" are never mangled); now the compassionate
        # prose gets the same guarantee. See
        # tests/test_crisis_copy_never_llm_translated.py.
        # 2026-10-09 (Failure Injection FI-17): Indic seekers (hi, te, ta, kn, mr) get
        # authentic native-language referral copy and next steps with Tele-MANAS (14416)
        # and emergency (112) guidance deterministically prepended before the English
        # prefix. ZERO runtime LLM calls.
        indic_prefix = ""
        indic_next_step = ""
        pref_lang = str(getattr(ctx, "preferred_lang", "") or "").lower()
        if pref_lang in INDIC_CRISIS_RESPONSES:
            lang_key = (
                response_type
                if response_type in ("third_party_crisis", "severe_ideation_checkin")
                else ("crisis" if level == DistressLevel.CRISIS else "severe")
            )
            lang_copy = INDIC_CRISIS_RESPONSES[pref_lang]
            if isinstance(lang_copy, dict):
                indic_prefix = lang_copy.get(lang_key, lang_copy.get("crisis", ""))
            else:
                indic_prefix = str(lang_copy)

            lang_steps = INDIC_NEXT_STEPS.get(pref_lang, "")
            if isinstance(lang_steps, dict):
                indic_next_step = lang_steps.get(lang_key, lang_steps.get("crisis", ""))
            else:
                indic_next_step = str(lang_steps)

        parts = [resources]
        if indic_prefix:
            parts.append(indic_prefix)
        if indic_next_step:
            parts.append(indic_next_step)
        parts.append(prefix)
        parts.append(next_step)
        response = "\n\n".join(part for part in parts if part)
        start_time = getattr(ctx, "start_time", time.time())
        decision_method = (
            "serene_mind_keyword"
            if getattr(ctx, "has_distress_keywords", False)
            else "serene_mind_assessment"
        )
        log_crisis_referral_shown(
            trace_id=getattr(ctx, "trace_id", ""),
            level=level.name if hasattr(level, "name") else str(level),
            region=None,  # get_crisis_resource("global") above — unfiltered by design
        )
        record_routing_decision(
            ctx,
            RoutingProvenance(
                layer="DISTRESS_STAGE",
                decision="crisis_preempted",
                method=decision_method,
                confidence=1.0,
                reason=f"Acute distress preemption (level={getattr(level, 'name', str(level))})",
            ),
        )
        return PipelineResult(
            final_answer=response,
            intent="DISTRESS",
            trace_id=getattr(ctx, "trace_id", ""),
            latency_ms=int((time.time() - start_time) * 1000),
            model_used=None,
            model_provider=None,
            route_decision="crisis_preempted",
            route_metadata={
                "requested_variant": "distress",
                "selected_variant": "crisis_preempted",
                "decision_method": decision_method,
                "distress_level": level.name if hasattr(level, "name") else str(level),
                **({"crisis_copy_indic": pref_lang} if indic_prefix else {}),
                **({"crisis_copy_hindi": HINDI_CRISIS_COPY_STATUS} if pref_lang == "hi" else {}),
                "routing_chain": list(getattr(ctx, "routing_chain", [])),
            },
            proactive_serene_mind={
                "triggered": False,
                "preempted": True,
                "level": level.name,
            },
            trigger_events=[
                {
                    "type": "DISTRESS",
                    "level": level.name,
                    "preempted": True,
                }
            ],
            release_manifest=get_release_manifest().to_dict(),
        )

    # -- extracted method bodies (verbatim, self -> ctx) --

    async def _detect_distress(
        self, ctx, user_msg_en: str, state: dict
    ) -> DistressAssessment | None:
        """Run Serene Mind distress detection. Returns None on failure (non-fatal)."""
        try:
            if ctx.container.serene_mind:
                distress_history = state.get("distress_history", [])
                assessment_history = (
                    [
                        {
                            "role": "system",
                            "content": f"Previous distress history: {distress_history}",
                        }
                    ]
                    if distress_history
                    else []
                )
                assessment = await ctx.container.serene_mind.analyze_with_history(
                    user_msg_en, history=state.get("chat_history_en", []) + assessment_history
                )
                if assessment.level.value >= 2:
                    logger.info(
                        "Distress detected (%s), passing to RAG pipeline for "
                        "compassionate response.",
                        assessment.level.name,
                    )
                return assessment
        except Exception as e:
            logger.warning(f"Serene Mind detection failed; falling back to regex: {e}")
        # Fail closed: a crash (or a missing engine) in the full check must never
        # switch crisis pre-emption off. The regex stage is pure and cannot fail.
        return SereneMindEngine().assess_distress(user_msg_en)

    @staticmethod
    def _has_prior_distress(state: dict) -> bool:
        if state.get("distress_history"):
            return True
        engine = SereneMindEngine()
        for msg in (state.get("chat_history_en") or [])[-6:]:
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
            text = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
            if role == "user" and engine._quick_distress_check(text or ""):
                return True
        return False

    async def _maybe_llm_downgrade_severe(
        self, ctx, user_msg_en: str, assessment: DistressAssessment | None, state: dict
    ) -> DistressAssessment | None:
        """Optional LLM second opinion that may ONLY lower SEVERE to MODERATE.

        Asymmetric by design: CRISIS is never consulted, nothing is raised here, and
        every uncertain outcome (flag off, prior distress, timeout, error, missing
        provider, or any reply other than exactly "TOPIC") keeps SEVERE.
        """
        if (
            not settings.distress_llm_downgrade_enabled
            or assessment is None
            or assessment.level != DistressLevel.SEVERE
            or self._has_prior_distress(state)
            # 2026-09-28 (owner-approved re-tier, Task 1): a SEVERE reached
            # via genuine ideation/spiritual-framing signals (the new
            # "severe_ideation_checkin" tag) must never be eligible for this
            # downgrade path, regardless of the flag — the flag stays OFF in
            # production, but this guard makes the exclusion structural
            # rather than incidental, so enabling the flag for some other
            # SEVERE reason in the future cannot silently start downgrading
            # ideation too.
            or getattr(assessment, "recommended_response_type", None) == "severe_ideation_checkin"
        ):
            return assessment
        llm = getattr(getattr(ctx, "container", None), "ollama", None)
        if llm is None:
            return assessment
        try:
            raw = await asyncio.wait_for(
                llm._generate_fast(_SEVERE_SECOND_OPINION_SYSTEM, user_msg_en[:512]),
                timeout=settings.distress_llm_downgrade_timeout_s,
            )
        except Exception as e:  # includes asyncio.TimeoutError
            logger.warning("Distress LLM second opinion unavailable; keeping SEVERE: %s", e)
            return assessment
        # Only an exact one-word "TOPIC" lowers the level. Empty, None, extra words,
        # "PERSONAL" or anything unparseable keeps SEVERE. The shared
        # classify_distress_structured is NOT used: its failure fallback returns a
        # "not distress" verdict, which would turn an outage into a downgrade.
        verdict = (raw or "").strip().strip(".").upper()
        if verdict == "TOPIC":
            assessment.level = DistressLevel.MODERATE
            assessment.recommended_response_type = "meditation"
            assessment.detected_signals.append(
                "[LLM second opinion] SEVERE->MODERATE: topic, not personal distress"
            )
            logger.info("Distress LLM second opinion lowered SEVERE to MODERATE")
        return assessment

    async def _maybe_llm_escalate_below_crisis(
        self, ctx, user_msg_en: str, assessment: DistressAssessment | None, state: dict
    ) -> DistressAssessment | None:
        """Escalate-only LLM second opinion (owner-approved 2026-09-28, "escalate-only + re-tier").

        Regex is the floor and is NEVER lowered by this — it may only raise
        NONE/MILD/MODERATE to SEVERE/CRISIS, or SEVERE to CRISIS. Runs ONLY
        when the regex-derived level is already below CRISIS, so a
        regex-CRISIS message never waits on an LLM call and the instant
        crisis response is never delayed. Timeout, error, malformed, or
        missing output leaves the regex level unchanged (fail-closed toward
        the regex result, not toward NONE). Entirely separate from
        `_maybe_llm_downgrade_severe` (which stays OFF and is unaffected by
        this flag or method).

        Sync-bounded (awaited here with `asyncio.wait_for`), not fire-and-
        forget async: DistressStage is a gate in the pipeline that must
        decide, before it returns, whether to short-circuit into
        `_crisis_preemption_result` — the caller (`run()`) reads
        `assessment.level` immediately after this returns to make that
        routing decision, so there is no point later in the request where a
        background escalation could still change the route. This mirrors
        the existing `_maybe_llm_downgrade_severe` precedent exactly (same
        `asyncio.wait_for` + bounded timeout pattern), for the same reason.
        """
        if not settings.distress_llm_escalation_enabled or assessment is None:
            return assessment
        if assessment.level >= DistressLevel.CRISIS:
            return assessment
        if assessment.recommended_response_type == "third_party_crisis":
            # Third-party already has its own dedicated response; there is
            # nothing more specific to escalate it to.
            return assessment
        llm = getattr(getattr(ctx, "container", None), "ollama", None)
        if llm is None:
            return assessment
        try:
            raw = await asyncio.wait_for(
                llm._generate_fast(_ESCALATION_SYSTEM_PROMPT, user_msg_en[:512]),
                timeout=settings.distress_llm_escalation_timeout_s,
            )
        except Exception as e:  # includes asyncio.TimeoutError
            logger.warning("Distress LLM escalation unavailable; keeping regex level: %s", e)
            return assessment
        verdict = (raw or "").strip().strip(".").upper()
        try:
            llm_level = DistressLevel[verdict]
        except KeyError:
            logger.warning(
                "Distress LLM escalation returned an unparseable verdict %r; keeping regex level",
                raw,
            )
            return assessment
        if llm_level > assessment.level:
            assessment.level = llm_level
            assessment.confidence = max(assessment.confidence, 0.7)
            assessment.detected_signals.append(f"[LLM escalation] raised to {llm_level.name}")
            if llm_level == DistressLevel.CRISIS:
                assessment.recommended_response_type = "crisis"
            elif llm_level == DistressLevel.SEVERE:
                # An LLM-only escalation (nothing in regex matched) is, by
                # construction, an ambiguous signal rather than a confirmed
                # plan/method/timeframe — route it to the gentler check-in,
                # not the full CRISIS-adjacent SEVERE template.
                assessment.recommended_response_type = "severe_ideation_checkin"
            logger.info("Distress LLM escalation raised level to %s", llm_level.name)
        return assessment

    async def _maybe_trigger_proactive_serene_mind(
        self,
        ctx,
        assessment: DistressAssessment | None,
        user_id: str,
        chat_body,
        state: dict,
    ) -> dict:
        """Check if proactive Serene Mind should be triggered."""
        try:
            if not (ctx.container.serene_mind and ctx.container.user_profile):
                return {"triggered": False}

            current = assessment or DistressAssessment(
                level=DistressLevel.NONE,
                confidence=0.0,
                detected_signals=[],
                language_detected=state.get("lang_detection", {}).get("primary", {}).get("value"),
                recommended_response_type="normal",
            )

            proactive = await ctx.container.serene_mind.analyze_distress_trend(
                user_id=user_id,
                current_assessment=current,
                user_profile_service=ctx.container.user_profile,
            )

            if not proactive:
                return {"triggered": False}

            _client_ts = getattr(chat_body, "last_serene_mind_at", None) or 0.0
            _now = time.time()
            _COOLDOWN = 15 * 60
            _skip = (_now - _client_ts) < _COOLDOWN

            if not _skip:
                _db_ts = await ctx.container.user_profile.get_last_meditation_session(user_id)
                if _db_ts and (_now - _db_ts) < _COOLDOWN:
                    _skip = True

            if _skip:
                logger.info(
                    f"Proactive Serene Mind skipped for {user_id} — within 15-min cooldown."
                )
                return {"triggered": False}

            logger.info(
                "Proactive Serene Mind triggered for user %s: level=%s, confidence=%.2f",
                user_id,
                proactive.level.name,
                proactive.confidence,
            )
            return {
                "triggered": True,
                "level": proactive.level.name,
                "confidence": proactive.confidence,
                "signals": proactive.detected_signals,
                "suggested_response": ctx.container.serene_mind.get_response(proactive),
                "requires_consent": True,
                "offer_reason": (
                    "A brief grounding practice may help you reconnect with the present moment."
                    if proactive.level < DistressLevel.SEVERE
                    else "A gentle practice is available if you would like support after this teaching."
                ),
                "duration_seconds": 225,
                "teachings_prelude": (
                    "I’m sorry this feels heavy. You do not need to interpret or solve it "
                    "spiritually right now. "
                    "If it feels helpful, you may try a brief, optional grounding practice; "
                    "you can also continue chatting or seek human support."
                ),
            }
        except Exception as e:
            logger.warning(f"Proactive Serene Mind analysis failed (non-fatal): {e}")
        return {"triggered": False}
