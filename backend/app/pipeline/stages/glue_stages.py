"""Glue stages — inline pipeline steps extracted from PipelineCoordinator.execute().

These are the steps that lived inline in ``execute()`` (request-state prep,
CASUAL short-circuit, post-graph translation, final result assembly). They
are kept here in one file to avoid file-count sprawl. The greeting regex and
warm-greeting list moved here from the coordinator (sole consumer).
"""

from __future__ import annotations

import logging
import random
import re
import time
import uuid
from typing import TYPE_CHECKING

from app.config import settings
from app.orchestrator_utils import prepare_request_state
from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)

# ---- Kill #3: instant CASUAL greeting short-circuit (moved from coordinator) ----
_WARM_GREETINGS = [
    "\U0001f64f Namaste, dear seeker! I am Mukthi Guru, here to walk with you on the path of awakening. What wisdom would you like to explore today?",
    "\U0001f64f Welcome, dear friend! I am here to share the timeless wisdom of Sri Preethaji and Sri Krishnaji. How may I serve your journey?",
    "\U0001f64f Namaste! A beautiful state begins with a single question. What's on your heart today?",
    "\U0001f64f Hello, beloved seeker! Every moment is an invitation to awaken. What would you like to explore together?",
    "\U0001f64f Pranam! I am Mukthi Guru, your companion on the path of inner peace. What question brings you here today?",
    "\U0001f64f Welcome! As Sri Preethaji teaches, every encounter is an opportunity for connection. How can I guide you today?",
    "\U0001f64f Namaste! May our conversation bring you closer to the Beautiful State. What would you like to know?",
    "\U0001f64f Hello, dear one! I am here with the wisdom of the ancient teachings and the vision of Sri Krishnaji. Ask me anything.",
    "\U0001f64f Welcome back! The path of awakening continues with each new question. What shall we explore?",
    "\U0001f64f Namaste, dear seeker! Like a Soul Sync breath, let us begin with presence. What is in your heart?",
]

_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|namaste|pranam|namaskar|namasthe|greetings|"
    r"good\s*(morning|afternoon|evening|night)|howdy|yo|hola|\U0001f64f)\s*[!.?]*\s*$",
    re.IGNORECASE,
)


class RequestStateStage(Stage):
    """Prepare request state (language detection, translation, memory context)."""

    name = "request_state"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        # ponytail: inline block from execute() verbatim
        state = await prepare_request_state(ctx.container, ctx.request, ctx.preferred_lang, user=ctx.user)
        ctx.state = state
        return None


class CasualShortCircuitStage(Stage):
    """Instant greeting short-circuit (<200ms, no LLM). Only fires for pure greetings."""

    name = "casual_short_circuit"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        # ponytail: inline block from execute() verbatim
        user_msg_en = ctx.state["user_msg_en"]
        is_indic = ctx.is_indic
        preferred_lang = ctx.preferred_lang

        if _GREETING_RE.match(user_msg_en):
            greeting = random.choice(_WARM_GREETINGS)
            if is_indic:
                greeting = await ctx.container.translation.translate_text(
                    text=greeting, source_lang="en", target_lang=preferred_lang
                )
            latency_ms = int((time.time() - ctx.start_time) * 1000)
            logger.info(f"Instant greeting short-circuit: {latency_ms}ms")
            return PipelineResult(
                final_answer=greeting,
                intent="CASUAL",
                trace_id=ctx.trace_id,
                latency_ms=latency_ms,
                model_used=None,  # canned greeting — no LLM ran
                model_provider=None,
                route_decision="instant_greeting",
                cache_hit=False,
            )
        return None


class TranslationStage(Stage):
    """Translate the final answer to the user's preferred language if Indic. Never short-circuits."""

    name = "translation"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        # ponytail: inline block from execute() verbatim
        if ctx.is_indic:
            ctx.final_answer = await ctx.container.translation.translate_text(
                text=ctx.final_answer, source_lang="en", target_lang=ctx.preferred_lang
            )
        return None


class ResultAssemblyStage(Stage):
    """Assemble the final PipelineResult from ctx. Always returns a result (terminal stage)."""

    name = "result_assembly"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        # ponytail: result-assembly block from execute() verbatim
        coordinator = ctx.coordinator
        graph_result = ctx.graph_result or {}
        latency_ms = int((time.time() - ctx.start_time) * 1000)

        retrieval_meta = coordinator._build_retrieval_meta(ctx.citations)
        trigger_events = coordinator._build_trigger_events(ctx.assessment)
        safety_events = coordinator._build_safety_events(ctx.input_check or {}, ctx.output_check or {})
        spans = coordinator._build_spans(graph_result)
        response_data = coordinator._build_response_data(graph_result, ctx.intent)

        ctx.result = PipelineResult(
            final_answer=ctx.final_answer,
            intent=ctx.intent,
            meditation_step=ctx.med_step,
            citations=ctx.citations,
            trace_id=str(uuid.uuid4()),
            latency_ms=latency_ms,
            # The generation node records which gateway/model actually produced
            # the answer (rag/nodes/generation.py route_metadata) — report that,
            # never the configured default, which can silently diverge from reality.
            model_used=graph_result.get("model_used"),
            model_provider=graph_result.get("model_provider"),
            route_decision=(ctx.intent.lower() if ctx.intent else "error"),
            # Use graph_result as the source of truth for tier/score because it is
            # the output of the LangGraph execution; ctx.state holds the pre-graph
            # input state and may still carry the initial None placeholder.
            query_tier=graph_result.get("query_tier") or ctx.state.get("query_tier") or ctx.detected_query_tier,
            blocked=False,
            cache_hit=False,
            proactive_serene_mind=ctx.state.get("proactive_serene_mind"),
            # Forward the score computed by verify_answer/format_final_answer;
            # fall back to the coordinator-derived value only when missing.
            faithfulness_score=graph_result.get("faithfulness_score", response_data["faithfulness"]),
            hallucination_flag=response_data["hallucination_flag"],
            answer_relevancy=response_data["answer_relevancy"],
            context_precision=response_data["context_precision"],
            context_recall=response_data["context_recall"],
            confidence_score=response_data.get("confidence_score"),
            judge_reasoning=response_data["judge_reasoning"],
            evaluation_trace=graph_result.get("evaluation_trace"),
            retrieval_metadata=retrieval_meta,
            trigger_events=trigger_events,
            safety_events=safety_events,
            spans=spans,
            follow_up_suggestions=graph_result.get("follow_up_suggestions", []),
        )
        return ctx.result