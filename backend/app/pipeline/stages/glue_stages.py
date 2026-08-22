"""Glue stages — inline pipeline steps extracted from PipelineCoordinator.execute().

These are the steps that lived inline in ``execute()`` (request-state prep,
CASUAL short-circuit, post-graph translation, final result assembly). They
are kept here in one file to avoid file-count sprawl. The greeting regex and
warm-greeting list moved here from the coordinator (sole consumer).
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import re
import time
import uuid
from typing import TYPE_CHECKING

from app.config import settings
from app.evidence_support import evidence_support_label
from app.orchestrator_utils import prepare_request_state
from app.pipeline.result import (
    ActionStep,
    AnswerEvidence,
    GuidancePlan,
    PipelineResult,
    TeachingAttribution,
)
from app.pipeline.stages.base import Stage
from app.release_manifest import get_release_manifest

if TYPE_CHECKING:
    from app.pipeline.stages.context import PipelineContext

logger = logging.getLogger(__name__)


def _citation_value(citation: object, key: str) -> object | None:
    if not isinstance(citation, dict):
        return None
    value = citation.get(key)
    if value not in (None, ""):
        return value
    metadata = citation.get("metadata")
    if isinstance(metadata, dict):
        return metadata.get(key)
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        if result == result and result not in (float("inf"), float("-inf")):
            return result
    return None


def _citations_verified(graph_result: dict) -> bool | None:
    value = graph_result.get("citations_verified")
    if value is None:
        verification = graph_result.get("verification")
        if isinstance(verification, dict):
            value = verification.get("citations_verified")
    return value if isinstance(value, bool) else None


def _faithfulness_score(graph_result: dict, response_data: dict) -> float | None:
    score = graph_result.get("faithfulness_score")
    if graph_result.get("is_faithful") is None and score == 0.0:
        return None
    if score is not None:
        return score
    return response_data.get("faithfulness")


def _answer_evidence(
    ctx, graph_result: dict, citations: list, response_data: dict
) -> AnswerEvidence:
    """Build a provenance envelope without reading answer text or model output."""
    source_count = len(citations)
    scores = []
    versions = []
    for citation in citations:
        score = _number(_citation_value(citation, "score"))
        if score is not None:
            scores.append(score)
        version = _number(_citation_value(citation, "source_version"))
        if version is not None and version >= 1 and version.is_integer():
            versions.append(int(version))
    graph_version = _number(graph_result.get("corpus_release_version"))
    if graph_version is not None and graph_version >= 1 and graph_version.is_integer():
        versions.append(int(graph_version))
    corpus_id = ctx.state.get("corpus_id")
    if not isinstance(corpus_id, str) or not corpus_id.strip():
        corpus_id = settings.default_corpus_id
    confidence = response_data.get("confidence_score")
    return AnswerEvidence(
        corpus_id=corpus_id,
        release_version=max(versions) if versions else None,
        model_policy_id=settings.openrouter_policy_id,
        evidence_support_label=evidence_support_label(
            confidence,
            source_count=source_count,
        ),
        source_count=source_count,
        top_source_score=max(scores) if scores else None,
        citations_verified=_citations_verified(graph_result),
    )


def _text(value: object, limit: int) -> str | None:
    """Return bounded display text only from a structured pipeline field."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _guidance_plan(ctx, graph_result: dict, citations: list) -> GuidancePlan | None:
    """Build optional UI guidance without parsing or inventing answer content."""
    assessment = getattr(ctx, "assessment", None)
    response_type = str(getattr(assessment, "recommended_response_type", "") or "").lower()
    if response_type in {"crisis", "severe"}:
        return None
    preferences = getattr(getattr(ctx, "request", None), "response_preferences", None)
    response_mode = getattr(preferences, "mode", "balanced_guidance")
    include_practice = bool(getattr(preferences, "include_practice", True))
    include_reflection = bool(getattr(preferences, "include_reflection", True))
    action_depth = getattr(preferences, "action_depth", "one_step")

    practice = graph_result.get("daily_practice_card")
    action_step = None
    if isinstance(practice, dict):
        instruction = _text(
            practice.get("instruction") or practice.get("practice") or practice.get("description"),
            640,
        )
        if instruction:
            action_step = ActionStep(
                title=_text(practice.get("title"), 120) or "Try this now",
                instruction=instruction,
                safety_note=_text(practice.get("safety_note"), 240),
            )

    if not include_practice or action_depth == "none":
        action_step = None

    reflection_prompt = None
    suggestions = graph_result.get("follow_up_suggestions")
    if isinstance(suggestions, list):
        for suggestion in suggestions:
            reflection_prompt = _text(suggestion, 280)
            if reflection_prompt:
                break

    if not include_reflection:
        reflection_prompt = None

    language = _text(getattr(ctx, "preferred_lang", None), 32) or "en"
    source_backed = bool(citations)
    return GuidancePlan(
        response_mode=response_mode,
        language=language,
        attribution=TeachingAttribution(
            label=(
                "Guidance inspired by retrieved teachings"
                if source_backed
                else "Reflective guidance"
            ),
            source_backed=source_backed,
        ),
        action_step=action_step,
        reflection_prompt=reflection_prompt,
    )


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

# Pure greetings are deliberately handled without a provider call.  This keeps
# the sub-200ms short-circuit honest for supported Indic locales instead of
# paying the full translation tail for a canned response.  The map is only
# used after _GREETING_RE matches; full answer translation remains unchanged.
_INDIC_GREETING_RESPONSES = {
    "hi": "🙏 नमस्ते! मैं मुक्ति गुरु हूँ। आज आप किस ज्ञान को समझना चाहेंगे?",
    "te": "🙏 నమస్తే! నేను ముక్తి గురువును. ఈ రోజు మీరు ఏ జ్ఞానాన్ని అన్వేషించాలనుకుంటున్నారు?",
    "ta": "🙏 வணக்கம்! நான் முக்தி குரு. இன்று எந்த ஞானத்தை ஆராய விரும்புகிறீர்கள்?",
    "kn": "🙏 ನಮಸ್ಕಾರ! ನಾನು ಮುಕ್ತಿ ಗುರು. ಇಂದು ನೀವು ಯಾವ ಜ್ಞಾನವನ್ನು ಅನ್ವೇಷಿಸಲು ಬಯಸುತ್ತೀರಿ?",
    "ml": "🙏 നമസ്കാരം! ഞാൻ മുക്തി ഗുരുവാണ്. ഇന്ന് ഏത് ജ്ഞാനം അന്വേഷിക്കാൻ ആഗ്രഹിക്കുന്നു?",
    "mr": "🙏 नमस्कार! मी मुक्ति गुरु आहे. आज तुम्हाला कोणते ज्ञान जाणून घ्यायचे आहे?",
    "bn": "🙏 নমস্কার! আমি মুক্তি গুরু। আজ আপনি কোন জ্ঞান অন্বেষণ করতে চান?",
    "gu": "🙏 નમસ્તે! હું મુક્તિ ગુરુ છું. આજે તમે કયું જ્ઞાન જાણવા માંગો છો?",
    "pa": "🙏 ਨਮਸਤੇ! ਮੈਂ ਮੁਕਤੀ ਗੁਰੂ ਹਾਂ। ਅੱਜ ਤੁਸੀਂ ਕਿਹੜੀ ਸਿਆਣਪ ਖੋਜਣਾ ਚਾਹੁੰਦੇ ਹੋ?",
}


def _deterministic_greeting(preferred_lang: str | None) -> str | None:
    """Return a localized canned greeting, or None when no safe map exists."""
    language = str(preferred_lang or "").strip().lower().split("-", 1)[0]
    return _INDIC_GREETING_RESPONSES.get(language)


_COMPARISON_TERMS = ("difference between", "compare", "versus", " vs ", " vs.")


def _is_bounded_meditation_comparison(question: str) -> bool:
    lowered = " ".join(str(question or "").casefold().split())
    return bool(
        any(term in lowered for term in _COMPARISON_TERMS)
        and "meditation" in lowered
        and "contemplation" in lowered
        and len(lowered) <= 180
    )


def _bounded_meditation_comparison_answer() -> str:
    return (
        "Here is a general distinction, not a quoted teaching: meditation usually "
        "emphasizes stabilizing attention, while contemplation usually emphasizes "
        "sustained inquiry or reflection on a theme. They can overlap—meditation "
        "steadies the mind, and contemplation examines what becomes clear. I could "
        "not verify a direct teaching on this comparison from the retrieved sources."
    )


class BoundedComparisonShortCircuitStage(Stage):
    """Return a safe, clearly-labelled comparison without an unnecessary RAG round."""

    name = "bounded_comparison_short_circuit"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        # Use the normalized English query when available, but never require a
        # translation call for the fast path. InputGuardrailStage already ran.
        question = str(ctx.state.get("user_msg_en") or ctx.user_msg or "")
        preferred_lang = str(ctx.preferred_lang or "en").casefold().split("-", 1)[0]
        if preferred_lang != "en" or not _is_bounded_meditation_comparison(question):
            return None
        answer = _bounded_meditation_comparison_answer()
        return PipelineResult(
            final_answer=answer,
            intent="COMPARATIVE",
            trace_id=ctx.trace_id,
            latency_ms=int((time.time() - ctx.start_time) * 1000),
            model_used=None,
            model_provider=None,
            route_decision="bounded_comparison_short_circuit",
            query_tier="fast",
            faithfulness_score=0.0,
            hallucination_flag=True,
            verification={
                "passed": False,
                "method": "limited_comparison_fallback",
                "citations_verified": True,
            },
            citations_verified=True,
            confidence_score=0.0,
            release_manifest=get_release_manifest().to_dict(),
            guidance_plan=GuidancePlan(
                response_mode="balanced_guidance",
                language=str(ctx.preferred_lang or "en"),
                attribution=TeachingAttribution(
                    label="General information; not a quoted teaching",
                    source_backed=False,
                ),
            ),
        )


class RequestStateStage(Stage):
    """Prepare request state (language detection, translation, memory context)."""

    name = "request_state"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        # ponytail: inline block from execute() verbatim
        state = await prepare_request_state(
            ctx.container, ctx.request, ctx.preferred_lang, user=ctx.user
        )
        preferences = getattr(ctx.request, "response_preferences", None)
        if hasattr(preferences, "model_dump"):
            state["response_preferences"] = preferences.model_dump(mode="json")
        elif isinstance(preferences, dict):
            state["response_preferences"] = dict(preferences)
        ctx.state = state
        return None


class CasualShortCircuitStage(Stage):
    """Instant greeting short-circuit (<200ms, no LLM). Only fires for pure greetings."""

    name = "casual_short_circuit"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        # ponytail: inline block from execute() verbatim
        user_msg_en = ctx.state["user_msg_en"]
        is_indic = ctx.is_indic
        preferred_lang = ctx.preferred_lang

        if _GREETING_RE.match(user_msg_en):
            greeting = _deterministic_greeting(preferred_lang) if is_indic else None
            if greeting is None:
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
                release_manifest=get_release_manifest().to_dict(),
            )
        return None


class TranslationStage(Stage):
    """Translate the final answer to the user's preferred language if Indic and still in English. Never short-circuits."""

    name = "translation"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        if (
            ctx.is_indic
            and ctx.final_answer
            and getattr(ctx, "container", None)
            and getattr(ctx.container, "translation", None)
        ):
            from app.language_utils import detect_message_lang

            detected = detect_message_lang(ctx.final_answer)
            # Only translate if the model generated English despite the prompt suffix.
            # If the model already produced native Indic script, re-translating with source_lang="en"
            # causes grammar distortion, phrase duplication, and doubles request latency.
            if detected == "en":
                ctx.final_answer = await ctx.container.translation.translate_text(
                    text=ctx.final_answer, source_lang="en", target_lang=ctx.preferred_lang
                )
        return None


class ResultAssemblyStage(Stage):
    """Assemble the final PipelineResult from ctx. Always returns a result (terminal stage)."""

    name = "result_assembly"

    async def run(self, ctx: PipelineContext) -> PipelineResult | None:
        # ponytail: result-assembly block from execute() verbatim
        coordinator = ctx.coordinator
        graph_result = ctx.graph_result or {}
        latency_ms = int((time.time() - ctx.start_time) * 1000)

        retrieval_meta = coordinator._build_retrieval_meta(ctx.citations)
        trigger_events = coordinator._build_trigger_events(ctx.assessment)
        safety_events = coordinator._build_safety_events(
            ctx.input_check or {}, ctx.output_check or {}
        )
        spans = coordinator._build_spans(graph_result)
        response_data = coordinator._build_response_data(graph_result, ctx.intent)
        live_logistics_events = [
            doc["live_event"]
            for doc in graph_result.get("web_search_results", [])
            if isinstance(doc, dict) and isinstance(doc.get("live_event"), dict)
        ]

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
            query_tier=graph_result.get("query_tier")
            or ctx.state.get("query_tier")
            or ctx.detected_query_tier,
            blocked=False,
            cache_hit=False,
            proactive_serene_mind=ctx.state.get("proactive_serene_mind"),
            # Forward the score computed by verify_answer/format_final_answer.
            # A skipped verifier uses is_faithful=None; a zero placeholder in
            # that state means unknown, not a measured failure.
            faithfulness_score=_faithfulness_score(graph_result, response_data),
            hallucination_flag=response_data.get("hallucination_flag", False),
            # verify_answer (rag/nodes/verification.py) already returns this dict in
            # graph state ({"passed": is_valid, "details": ...}) -- it was never
            # forwarded past PipelineResult, so ChatResponse.verification was always
            # null regardless of whether verification actually ran.
            verification=graph_result.get("verification"),
            answer_relevancy=response_data.get("answer_relevancy", 0.0),
            context_precision=response_data.get("context_precision", 0.0),
            context_recall=response_data.get("context_recall", 0.0),
            confidence_score=response_data.get("confidence_score"),
            judge_reasoning=response_data.get("judge_reasoning", ""),
            citations_verified=_citations_verified(graph_result),
            orphan_citations_stripped=graph_result.get("orphan_citations_stripped"),
            evaluation_trace=graph_result.get("evaluation_trace"),
            retrieval_metadata=retrieval_meta,
            trigger_events=trigger_events,
            safety_events=safety_events,
            spans=spans,
            node_timings=graph_result.get("node_timings", {}),
            follow_up_suggestions=list(graph_result.get("follow_up_suggestions", []) or []),
            audio_url=graph_result.get("audio_url"),
            kg_concept_nodes=list(graph_result.get("kg_concept_nodes", []) or []),
            daily_practice_card=graph_result.get("daily_practice_card"),
            live_logistics_events=live_logistics_events,
            answer_evidence=_answer_evidence(
                ctx,
                graph_result,
                ctx.citations,
                response_data,
            ),
            guidance_plan=_guidance_plan(
                ctx,
                graph_result,
                ctx.citations,
            ),
            release_manifest=get_release_manifest().to_dict(),
            provenance_context=graph_result.get("provenance_context"),
        )

        # GDPR audit trail (Unit 24) -- previously wired for reads
        # (list_sessions_for_user) but never fed a single write, so the audit
        # trail was always empty. Same incognito boundary as telemetry/memory.
        if not ctx.incognito:
            try:
                from services.tenant_context import TenantContext

                compliance_logger = getattr(ctx.container, "compliance_logger", None)
                if compliance_logger is not None:
                    interaction_payload = {
                        "tenant_id": TenantContext.get() or "default",
                        "user_id": ctx.user_id,
                        "session_id": ctx.session_id or ctx.stable_session_id,
                        "action": "generate",
                        "model": ctx.result.model_used or "",
                        "system_prompt": "",
                        "user_prompt": ctx.user_msg,
                        "response": ctx.result.final_answer or "",
                        "latency_ms": ctx.result.latency_ms,
                        "status": "error" if ctx.last_stage_status == "error" else "ok",
                        # GDPR Art. 6/17 metadata. Consent receipt is None here:
                        # the chat pipeline has no consent ledger association —
                        # memory outbox receipts live in memory_outbox.py.
                        "legal_basis": settings.compliance_legal_basis,
                        "consent_receipt_id": None,
                        "retention_days": settings.compliance_retention_days,
                    }
                    # The logger's API is synchronous file I/O. Offload it so
                    # the event loop is not blocked while the audit record is
                    # written, and keep the write best-effort.
                    loop = asyncio.get_running_loop()
                    audit_timeout = max(1.0, settings.memory_background_task_timeout_seconds - 2.0)
                    if hasattr(compliance_logger, "log_interaction_async"):
                        await asyncio.wait_for(
                            compliance_logger.log_interaction_async(**interaction_payload),
                            timeout=audit_timeout,
                        )
                    else:
                        sync_call = functools.partial(
                            compliance_logger.log_interaction, **interaction_payload
                        )
                        await asyncio.wait_for(
                            loop.run_in_executor(None, sync_call),
                            timeout=audit_timeout,
                        )
            except Exception as exc:
                logger.debug("ComplianceLogger.log_interaction failed: %s", exc)

        return ctx.result
