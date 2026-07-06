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

        # ponytail: body of _run_input_guardrails verbatim
        with REQUEST_LATENCY.labels(stage="guardrails").time():
            input_check = await container.guardrails.check_input(user_msg_en)

        ctx.input_check = input_check
        if input_check["blocked"]:
            ctx.last_stage_status = "error"
            blocked_resp = input_check["response"]
            if is_indic:
                blocked_resp = await container.translation.translate_text(
                    text=blocked_resp, source_lang="en", target_lang=preferred_lang
                )
            # Crisis/self-harm blocks already contain compassionate helpline responses.
            # Report DISTRESS intent so the benchmark sees the correct routing label
            # instead of a generic ERROR.
            is_self_harm = "self_harm" in (input_check.get("reason") or "")
            intent = "DISTRESS" if is_self_harm else "ERROR"
            route_decision = "distress" if is_self_harm else "blocked"
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
            ctx.last_stage_status = "error"
        ctx.is_blocked = is_blocked
        return None