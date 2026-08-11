"""Guardrail stages — input check, output moderation, circuit-breaker pre-check.

Input/Output stages extract ``PipelineCoordinator._run_input_guardrails`` and
the inline output-guardrail block from ``execute()``. CircuitBreakerStage wraps
the coordinator's ``_is_circuit_open`` helper (kept on the coordinator per plan).
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from app.config import settings
from app.language_utils import guardrail_text_for, is_non_english_message
from app.metrics import REQUEST_LATENCY
from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)


class CircuitBreakerStage(Stage):
    """Short-circuit if the LLM provider circuit breaker is open."""

    name = "circuit_breaker"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        if ctx.coordinator._is_circuit_open():
            ctx.last_stage_status = "error"
            return ctx.coordinator._circuit_open_result(ctx.is_benchmark, ctx.start_time)
        return None


class InputGuardrailStage(Stage):
    """Run input guardrails; short-circuit with a blocked result if blocked."""

    name = "input_guardrails"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        user_msg_en = ctx.state["user_msg_en"]
        is_indic = ctx.is_indic
        preferred_lang = ctx.preferred_lang
        container = ctx.container

        # CRIT-5: guardrails must see English for EVERY input. Indic-preferred
        # users are already covered — prepare_request_state translated to
        # user_msg_en, so do NOT re-translate them. The real gap is an
        # EN-preferred user typing in a non-EN script (Devanagari, Tamil, ...)
        # — should_translate was False, so user_msg_en is the raw non-EN text.
        # Detect on the original message and translate just that case.
        guardrail_text = user_msg_en
        if settings.multilingual_guardrails:
            raw = ctx.user_msg or user_msg_en
            if not is_indic and is_non_english_message(raw):
                guardrail_text = await guardrail_text_for(raw, container.translation, preferred_lang)

        # ponytail: body of _run_input_guardrails verbatim
        with REQUEST_LATENCY.labels(stage="guardrails").time():
            input_check = await container.guardrails.check_input(guardrail_text)

        ctx.input_check = input_check
        if input_check["blocked"]:
            ctx.last_stage_status = "error"
            blocked_resp = input_check["response"]
            if is_indic:
                blocked_resp = await container.translation.translate_text(
                    text=blocked_resp, source_lang="en", target_lang=preferred_lang
                )
            # Report the guardrail's actual detected category (from IntentType,
            # app/constants.py) instead of a blanket ERROR, which reads as a
            # system failure even when the block was a correct, deliberate
            # safety refusal (medical advice, harmful pattern, self-harm, etc).
            reason = input_check.get("reason") or ""
            if "self_harm" in reason or "Emotional wellness" in reason:
                intent, route_decision = "DISTRESS", "distress"
            elif "Medical advice" in reason or "Harmful pattern" in reason:
                intent, route_decision = "SAFETY_VIOLATION", "blocked"
            else:
                intent, route_decision = "ERROR", "blocked"
            return PipelineResult(
                final_answer=blocked_resp,
                intent=intent,
                blocked=True,
                block_reason=input_check["reason"],
                latency_ms=int((time.time() - ctx.start_time) * 1000),
                trace_id=ctx.trace_id,
                model_used=None,  # blocked before any model ran
                model_provider=None,
                route_decision=route_decision,
            )
        return None


class OutputGuardrailStage(Stage):
    """Moderate the final answer post-graph. Never short-circuits."""

    name = "output_guardrails"

    async def run(self, ctx: "PipelineContext") -> PipelineResult | None:
        container = ctx.container
        output_check = await container.guardrails.check_output(ctx.final_answer)
        ctx.output_check = output_check
        is_blocked = output_check["blocked"]
        if is_blocked:
            logger.info(f"Output moderated: {output_check['reason']}")
            ctx.final_answer = output_check["moderated_response"]
            # "moderated" distinguishes deliberate safety intervention from system failure.
            # Using "error" here caused false-positive error rate inflation in telemetry.
            ctx.last_stage_status = "moderated"
        ctx.is_blocked = is_blocked
        return None