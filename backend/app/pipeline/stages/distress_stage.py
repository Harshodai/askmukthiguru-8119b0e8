"""Distress stage — Serene Mind detection + proactive trigger.

Bodies extracted verbatim from PipelineCoordinator._detect_distress and
_maybe_trigger_proactive_serene_mind, plus the distress-keyword pre-screen
and proactive-state glue that lived inline in ``execute()``.
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

from app.pipeline.stages.base import Stage
from services.serene_mind_engine import DistressAssessment, DistressLevel

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

# Distress keyword pre-screen — only triggers full analysis when present.
_DISTRESS_KEYWORD_RE = re.compile(
    r"\b(suicid|kill\s*my|want\s*to\s*die|end\s*my\s*life|hurt\s*my|self[-\s]*harm|"
    r"hopeless|crying|panic|anxiety|depress|grief|alone|miserable|worthless|"
    r"helpless|nobody\s*cares|no\s*point|give\s*up|can'?t\s*go\s*on|overwhelm|"
    r"suffering|pain|afraid|scared|terrif|agony|desper|broken|tut\s*chuk|"
    r"akela|kashtam|dukh|takleef|udas)\b",
    re.IGNORECASE,
)


class DistressStage(Stage):
    """Run distress detection (conditional on keyword pre-screen) and
    proactive Serene Mind triggering. Never short-circuits."""

    name = "distress_detection"

    async def run(self, ctx: "PipelineContext") -> "PipelineResult | None":
        user_msg_en = ctx.state["user_msg_en"]
        state = ctx.state

        # ponytail: distress-keyword pre-screen from execute() verbatim
        ctx.has_distress_keywords = bool(_DISTRESS_KEYWORD_RE.search(user_msg_en))

        if ctx.has_distress_keywords:
            assessment = await self._detect_distress(ctx, user_msg_en, state)
        else:
            assessment = None
        ctx.assessment = assessment

        # ponytail: proactive Serene Mind block from execute() verbatim
        # Check an already-distressed conversation even when its latest turn
        # uses no keyword. This avoids dropping a persistent trend while
        # keeping expensive semantic detection keyword-gated.
        proactive_data = None
        if ctx.has_distress_keywords or state.get("distress_history"):
            proactive_data = await self._maybe_trigger_proactive_serene_mind(
                ctx, assessment, ctx.user_id, ctx.request, state
            )
        if proactive_data:
            state["proactive_serene_mind"] = proactive_data
        ctx.proactive_data = proactive_data
        return None

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
