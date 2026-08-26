"""Guardrail stages — input check, output moderation, circuit-breaker pre-check.

Input/Output stages extract ``PipelineCoordinator._run_input_guardrails`` and
the inline output-guardrail block from ``execute()``. CircuitBreakerStage wraps
the coordinator's ``_is_circuit_open`` helper (kept on the coordinator per plan).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from app.config import settings
from app.language_utils import guardrail_text_for, is_non_english_message
from app.metrics import REQUEST_LATENCY
from app.pipeline.result import PipelineResult
from app.pipeline.stages.base import Stage
from app.release_manifest import get_release_manifest

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)


class CircuitBreakerStage(Stage):
    """Short-circuit if the LLM provider circuit breaker is open."""

    name = "circuit_breaker"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        if ctx.coordinator._is_circuit_open():
            ctx.last_stage_status = "error"
            result = ctx.coordinator._circuit_open_result(
                ctx.is_benchmark, ctx.start_time, trace_id=ctx.trace_id
            )
            # This stage short-circuits before TranslationStage ever runs -- an
            # Indic user would otherwise get the English fallback verbatim.
            if getattr(ctx, "is_indic", False):
                import dataclasses

                translation_timeout = max(1.0, settings.node_timeout_fast + 2.0)
                try:
                    translated = await asyncio.wait_for(
                        ctx.container.translation.translate_text(
                            text=result.final_answer,
                            source_lang="en",
                            target_lang=ctx.preferred_lang,
                        ),
                        timeout=translation_timeout,
                    )
                    result = dataclasses.replace(result, final_answer=translated)
                except TimeoutError:
                    logger.warning(
                        "Circuit-breaker Indic translation timed out; preserving English fallback"
                    )
                except Exception as e:
                    logger.warning("Circuit-breaker Indic translation failed: %s", e)
            return result
        return None


class InputGuardrailStage(Stage):
    """Run input guardrails; short-circuit with a blocked result if blocked."""

    name = "input_guardrails"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
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
                guardrail_text = await guardrail_text_for(
                    raw, container.translation, preferred_lang
                )

        # ponytail: body of _run_input_guardrails verbatim
        with REQUEST_LATENCY.labels(stage="guardrails").time():
            input_check = await container.guardrails.check_input(guardrail_text)

        # A client may supply assistant.system_prompt (AssistantContext) — it is
        # instruction text that reaches generation as the system persona, so it
        # must clear the same rail as the user message. Without this it was the
        # one instruction channel that met no guardrail at all.
        assistant = getattr(ctx.request, "assistant", None)
        persona = getattr(assistant, "system_prompt", None) if assistant else None
        if isinstance(persona, str) and persona.strip() and not input_check["blocked"]:
            persona_check = await container.guardrails.check_input(persona)
            if persona_check["blocked"]:
                input_check = persona_check

        # M3: server-side persona allowlist. The slug is client-supplied; if it
        # is not in the registry, the client-supplied system_prompt is dropped so
        # the honesty guard in rag/nodes/generation stays ON and no attacker
        # persona replaces the guru. slug/knowledge_tags only scope retrieval and
        # stay. The anonymous-user gate in GraphStage still runs after this and
        # would drop the prompt regardless; this gate covers an authenticated
        # user carrying an injected slug.
        if assistant is not None:
            from app.assistant_registry import validate_assistant_slug

            if validate_assistant_slug(getattr(assistant, "slug", None)) is None:
                if getattr(assistant, "system_prompt", None) is not None:
                    logger.info(
                        "Clearing client-supplied assistant.system_prompt for "
                        "non-allowlisted slug %r (M3).",
                        getattr(assistant, "slug", None),
                    )
                    assistant.system_prompt = None

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
                release_manifest=get_release_manifest().to_dict(),
            )
        return None


class OutputGuardrailStage(Stage):
    """Moderate the final answer post-graph. Never short-circuits."""

    name = "output_guardrails"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        container = ctx.container
        # The output rail (guardrails/lightweight_handler._handle_output) is an
        # English literal-phrase regex list, but TranslationStage runs BEFORE this
        # stage — so for an Indic seeker ctx.final_answer is already translated and
        # the English patterns never match (a live no-op). Moderate the
        # pre-translation English answer instead: the graph generates in English and
        # TranslationStage never touches ctx.graph_result, so graph_result[
        # "final_answer"] is that English text. English seekers keep moderating the
        # served (tone-adapted) answer exactly as before.
        text_to_moderate = ctx.final_answer
        if ctx.is_indic and ctx.graph_result:
            text_to_moderate = ctx.graph_result.get("final_answer") or ctx.final_answer
        output_check = await container.guardrails.check_output(text_to_moderate)
        ctx.output_check = output_check
        is_blocked = output_check["blocked"]
        if is_blocked:
            logger.info(f"Output moderated: {output_check['reason']}")
            moderated = output_check["moderated_response"]
            # moderated_response is English; the seeker's answer was already
            # translated, so translate the replacement too or an Indic user gets an
            # untranslated block message.
            if ctx.is_indic:
                moderated = await container.translation.translate_text(
                    text=moderated, source_lang="en", target_lang=ctx.preferred_lang
                )
            ctx.final_answer = moderated
            # "moderated" distinguishes deliberate safety intervention from system failure.
            # Using "error" here caused false-positive error rate inflation in telemetry.
            ctx.last_stage_status = "moderated"
        ctx.is_blocked = is_blocked
        return None
