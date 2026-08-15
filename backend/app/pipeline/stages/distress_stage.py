"""Distress stage — Serene Mind detection + proactive trigger.

Bodies extracted verbatim from PipelineCoordinator._detect_distress and
_maybe_trigger_proactive_serene_mind, plus the distress-keyword pre-screen
and proactive-state glue that lived inline in ``execute()``.
"""

from __future__ import annotations

from app.pipeline.result import PipelineResult
import logging
import re
import time
from typing import TYPE_CHECKING

from app.pipeline.stages.base import Stage
from services.serene_mind_engine import (
    DISTRESS_RESPONSES,
    DistressAssessment,
    DistressLevel,
    get_crisis_resource,
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
    r"afraid|scared|terrif|agony|desper|broken|tut\s*chuk|"
    r"akela|kashtam|dukh|takleef|udas)\b",
    re.IGNORECASE,
)

# Acute Indic self-harm / suicide keywords — deliberately narrow (suicide /
# self-harm intent), NOT vague pain/grief words. See _DISTRESS_KEYWORD_RE
# docstring for the keyword sources.
#
# Sources for Kannada/Malayalam additions:
#   - NIMHANS suicide prevention glossary (Kannada)
#   - iCall/Vandrevala Foundation crisis line materials (Malayalam)
#   - ICHI Mental Health Glossary updates 2025 (both scripts)
_INDIC_CRISIS_KEYWORDS = (
    # Hindi (Devanagari)
    "आत्महत्या",  # suicide
    "खुदकुशी",  # suicide (colloquial)
    "खुद को मार",  # kill myself
    # Marathi-specific (Devanagari)
    "जीव देणे",   # "give life" — Marathi idiom for suicide
    "जीव संपवणे",  # "end life" — Marathi
    # Bengali (Bengali script)
    "আত্মহত্যা",  # suicide
    "নিজেকে মেরে",  # kill myself
    # Tamil (Tamil script)
    "தற்கொலை",  # suicide
    "தற்கொலை செய்து",  # commit suicide
    # Telugu (Telugu script)
    "ఆత్మహత్య",  # suicide
    "ఆత్మహత్య చేసుకో",  # commit suicide
    # Kannada (Kannada script)
    "ಆತ್ಮಹತ್ಯೆ",   # suicide
    "ಆತ್ಮಹತ್ಯೆ ಮಾಡಿಕೊಳ್ಳ",  # commit suicide
    "ನನ್ನನ್ನು ಕೊಲ್ಲ",  # kill myself
    # Malayalam (Malayalam script)
    "ആത്മഹത്യ",   # suicide
    "ആത്മഹത്യ ചെയ്യ",  # commit suicide
    "എന്നെ കൊല്ല",   # kill myself
    # Gujarati (Gujarati script)
    "આત્મહત્યા",
    "જીવ આપવો",
    "મરી જવું",
    # Punjabi (Gurmukhi script)
    "ਆਤਮਹੱਤਿਆ",
    "ਖੁਦਕੁਸ਼ੀ",
    # Odia (Odia script)
    "ଆତ୍ମହତ୍ୟା",
    # Urdu (Arabic script)
    "خودکشی",
    "جان دینا",
    # Transliterated / Romanized Indic crisis phrases
    "marna chahta",
    "mar jana chahta",
    "jaan de dunga",
    "zindagi khatam",
    "chavali anipistundi",
    "chavalanukuntunna",
    "saaganum pola",
    "saayabeku",
    "jeev dyava vat-to",
    "marvu che",
    "morite chai",
)

_INDIC_CRISIS_KEYWORD_RE = re.compile("|".join(_INDIC_CRISIS_KEYWORDS), re.IGNORECASE)


class DistressStage(Stage):
    """Run deterministic distress detection and preempt severe/crisis paths.

    Moderate and mild distress can continue to the compassionate RAG path.
    Severe and crisis assessments terminate here so no retrieval, provider call,
    translation, memory write, or cache write can precede human support.
    """

    name = "distress_detection"

    async def run(self, ctx: "PipelineContext") -> "PipelineResult | None":
        user_msg_en = ctx.state["user_msg_en"]
        state = ctx.state

        # CRIT-5: pre-screen BOTH the translated EN text and the raw original
        # message, so an acute Indic crisis keyword is never missed because
        # translation softened it. raw falls back to user_msg_en (which is
        # already English for Indic-preferred users) when ctx.user_msg is
        # unavailable (e.g. direct stage tests use SimpleNamespace).
        raw = getattr(ctx, "user_msg", None) or user_msg_en
        has_en_keyword = bool(_DISTRESS_KEYWORD_RE.search(user_msg_en))
        has_indic_keyword = bool(_INDIC_CRISIS_KEYWORD_RE.search(raw))
        ctx.has_distress_keywords = has_en_keyword or has_indic_keyword

        # Assess unconditionally. Keyword-gating this let question-framed
        # ideation ("how do i stop wanting to die") skip detection entirely —
        # the pre-screen regex misses it exactly as the crisis phrasings did.
        # assess_distress is pure regex (<1ms), so running it every turn is cheap.
        assessment = await self._detect_distress(ctx, user_msg_en, state)
        ctx.assessment = assessment

        level_value = getattr(getattr(assessment, "level", None), "value", -1)
        if not isinstance(level_value, int):
            level_value = -1
        if assessment and level_value >= DistressLevel.SEVERE.value:
            return await self._crisis_preemption_result(ctx, assessment)
        # ponytail: proactive Serene Mind block from execute() verbatim.
        # Trigger on a keyword hit, a persistent distress trend, OR a positive
        # assessment this turn — so a crisis with no listed keyword still routes.
        proactive_data = None
        if ctx.has_distress_keywords or state.get("distress_history") or (
            assessment and level_value >= DistressLevel.MODERATE.value
        ):
            proactive_data = await self._maybe_trigger_proactive_serene_mind(
                ctx, assessment, ctx.user_id, ctx.request, state
            )
        if proactive_data:
            state["proactive_serene_mind"] = proactive_data
        ctx.proactive_data = proactive_data
        return None



    @staticmethod
    async def _crisis_preemption_result(
        ctx: "PipelineContext", assessment: DistressAssessment
    ) -> PipelineResult:
        """Return reviewed support before any model or persistence side effect."""
        level = assessment.level
        prefix = DISTRESS_RESPONSES.get(level, DISTRESS_RESPONSES[DistressLevel.CRISIS])
        resources = get_crisis_resource("global")
        next_step = (
            "If you are in immediate danger, please contact local emergency services "
            "or go to a safer place now. If you can, tell a trusted person nearby "
            "that you need support."
        )
        # Resources (helpline numbers/shortcodes) MUST appear in the first 200
        # characters of a SEVERE/CRISIS response (see docs/INTEGRATION_GUIDE.md,
        # evaluation/datasets/mukthi_guru_v1.yaml, evaluation/rubrics/
        # refusal_correctness.yaml) — DISTRESS_RESPONSES[SEVERE]'s prefix alone
        # runs well past 200 chars, so resources must lead, not follow.
        # Translate compassionate prose if Indic, but preserve the helpline resource block
        # in clean ASCII format so phone numbers and SMS shortcodes ("Text HOME to 741741")
        # are never mangled by machine translation.
        if getattr(ctx, "is_indic", False) and getattr(ctx, "container", None) and getattr(ctx.container, "translation", None):
            try:
                translated_prefix = await ctx.container.translation.translate_text(
                    text=prefix, source_lang="en", target_lang=ctx.preferred_lang
                )
                translated_next_step = await ctx.container.translation.translate_text(
                    text=next_step, source_lang="en", target_lang=ctx.preferred_lang
                )
                response = "\n\n".join(part for part in (resources, translated_prefix, translated_next_step) if part)
            except Exception:
                response = "\n\n".join(part for part in (resources, prefix, next_step) if part)
        else:
            response = "\n\n".join(part for part in (resources, prefix, next_step) if part)
        start_time = getattr(ctx, "start_time", time.time())
        return PipelineResult(
            final_answer=response,
            intent="DISTRESS",
            trace_id=getattr(ctx, "trace_id", ""),
            latency_ms=int((time.time() - start_time) * 1000),
            model_used=None,
            model_provider=None,
            route_decision="crisis_preempted",
            proactive_serene_mind={
                "triggered": False,
                "preempted": True,
                "level": level.name,
            },
            trigger_events=[{
                "type": "DISTRESS",
                "level": level.name,
                "preempted": True,
            }],
        )

    # -- extracted method bodies (verbatim, self -> ctx) --

    async def _detect_distress(self, ctx, user_msg_en: str, state: dict) -> DistressAssessment | None:
        """Run Serene Mind distress detection. Returns None on failure (non-fatal)."""
        try:
            if ctx.container.serene_mind:
                distress_history = state.get("distress_history", [])
                assessment_history = (
                    [{"role": "system", "content": f"Previous distress history: {distress_history}"}]
                    if distress_history
                    else []
                )
                assessment = await ctx.container.serene_mind.analyze_with_history(
                    user_msg_en, history=state.get("chat_history_en", []) + assessment_history
                )
                if assessment.level.value >= 2:
                    logger.info(f"Distress detected ({assessment.level.name}), passing to RAG pipeline for compassionate response.")
                return assessment
        except Exception as e:
            logger.warning(f"Serene Mind detection failed (non-fatal): {e}")
        return None

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
                logger.info(f"Proactive Serene Mind skipped for {user_id} — within 15-min cooldown.")
                return {"triggered": False}

            logger.info(f"Proactive Serene Mind triggered for user {user_id}: level={proactive.level.name}, confidence={proactive.confidence:.2f}")
            return {
                "triggered": True,
                "level": proactive.level.name,
                "confidence": proactive.confidence,
                "signals": proactive.detected_signals,
                "suggested_response": ctx.container.serene_mind.get_response(proactive),
                "teachings_prelude": (
                    "Sri Krishnaji and Preethaji teach us that suffering is not the truth of who you are. "
                    "Every moment of pain is also a doorway to awakening. "
                    "You are not alone in this — Mukti Guru is here with you. "
                    "Before we continue, let's pause together in a moment of Serene Mind."
                ),
            }
        except Exception as e:
            logger.warning(f"Proactive Serene Mind analysis failed (non-fatal): {e}")
        return {"triggered": False}
