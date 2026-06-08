"""Mukthi Guru — Chat Request Orchestrator

Design Patterns:
  - Command/Mediator: Orchestrates request pipeline stages
  - Dependency Injection: Consumes decoupled service container interfaces
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from typing import Any, Optional

from fastapi import BackgroundTasks, HTTPException, Request

from app.config import settings
from app.context import correlation_id_var
from app.dependencies import ServiceContainer
from app.language_utils import detect_and_prepare_language_info
from app.metrics import REQUEST_COUNT, REQUEST_LATENCY
from app.schemas import ChatRequest, ChatResponse, MessagePayload
from app.telemetry_sink import SupabaseTelemetrySink
from rag.graph import create_initial_state
from rag.memory import build_memory_context, normalize_session_id
from rag.timeout_utils import TimeoutBudget, budget_var
from services.sarvam_service import CircuitOpenException
from services.serene_mind_engine import DistressAssessment, DistressLevel
from app.coalescer import build_coalescer
from app.orchestrator_utils import (
    cache_language_key,
    select_graph_for_query,
    prepare_request_state,
)

logger = logging.getLogger(__name__)

coalescer = build_coalescer(redis_url=getattr(settings, "redis_url", None), ttl=60.0)


class ChatRequestOrchestrator:
    """Orchestrates the chat endpoint flow: guardrails -> RAG -> response assembly."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.telemetry_sink = SupabaseTelemetrySink()

    async def orchestrate(
        self,
        request: Request,
        chat_body: ChatRequest,
        background_tasks: BackgroundTasks,
        user: dict,
    ) -> ChatResponse:
        """Execute the full conversational request orchestration pipeline."""
        user_msg = chat_body.user_message.strip()
        preferred_lang = chat_body.language or "en"
        is_indic = preferred_lang and not preferred_lang.startswith("en")
        start_time = time.time()
        cache_key = cache_language_key(user_msg, preferred_lang)
        user_id = user.get("id", "anonymous") if user else "anonymous"
        stable_session_id = normalize_session_id(chat_body.session_id, user_id)

        if not user_msg:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        if len(user_msg) > settings.max_input_length:
            raise HTTPException(
                status_code=400,
                detail=f"Message too long. Please keep it under {settings.max_input_length} characters.",
            )

        is_benchmark = request.headers.get("X-Test-Key") == settings.jwt_secret

        # === Response Cache Check ===
        cached = self.container.exact_cache.get(cache_key)
        if cached is None:
            cached = await asyncio.to_thread(self.container.semantic_cache.get, cache_key)
        if cached is not None:
            REQUEST_COUNT.labels(status="cache_hit").inc()
            cached_response = cached["response"]
            output_check = await self.container.guardrails.check_output(cached_response)
            final_response = (
                output_check["moderated_response"] if output_check["blocked"] else cached_response
            )

            if is_indic and final_response != cached_response:
                final_response = await self.container.translation.translate_text(
                    text=final_response, source_lang="en", target_lang=preferred_lang
                )

            query_id = str(uuid.uuid4())
            latency_ms = int((time.time() - start_time) * 1000)
            user_id = user.get("id", "anonymous") if user else "anonymous"
            background_tasks.add_task(
                self.telemetry_sink.log_query_trace,
                query_id=query_id,
                session_id=normalize_session_id(chat_body.session_id, user_id),
                user_id=user_id,
                query_text=user_msg,
                model=getattr(settings, "sarvam_cloud_model", None)
                or getattr(settings, "ollama_model", None)
                or "cache",
                latency_ms=latency_ms,
                status="ok",
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                response_text=final_response,
                citations=cached.get("citations", []),
                provider=getattr(settings, "llm_provider", None),
                route_decision="semantic_cache",
                cache_hit=True,
            )
            return ChatResponse(
                response=final_response,
                intent=cached.get("intent"),
                meditation_step=cached.get("meditation_step", 0),
                citations=cached.get("citations", []),
                trace_id=query_id,
                latency_ms=latency_ms,
                model_used=getattr(settings, "sarvam_cloud_model", None)
                or getattr(settings, "ollama_model", None),
                model_provider=getattr(settings, "llm_provider", None),
                route_decision="semantic_cache",
            )

        if settings.is_sarvam_cloud:
            underlying_service = self.container.ollama
            if hasattr(self.container.ollama, "_service"):
                underlying_service = self.container.ollama._service

            circuit = getattr(underlying_service, "_circuit", None)
            if circuit and not circuit.can_execute():
                logger.warning(
                    "Sarvam API circuit breaker is OPEN in ChatRequestOrchestrator pre-check — failing fast"
                )
                if is_benchmark:
                    raise HTTPException(
                        status_code=503,
                        detail="Service temporarily unavailable - circuit breaker is OPEN",
                    )
                else:
                    return ChatResponse(
                        response="I apologize, but the service is temporarily unavailable. Please try again in a moment.",
                        intent="ERROR",
                        meditation_step=0,
                        citations=[],
                        trace_id=str(uuid.uuid4()),
                        latency_ms=0,
                        model_used=getattr(settings, "sarvam_cloud_model", None)
                        or getattr(settings, "ollama_model", None),
                        model_provider=getattr(settings, "llm_provider", None),
                        route_decision="error",
                    )

        try:
            state = await prepare_request_state(self.container, chat_body, preferred_lang, user=user)
            user_msg_en = state["user_msg_en"]
            is_indic = state["is_indic"]
            preferred_lang = state["preferred_lang"]
            user_id = state["user_id"]
            stable_session_id = state["stable_session_id"]
            chat_history = [m.model_dump() for m in chat_body.messages]
            chat_history_en = state["chat_history_en"]
            memory_context = state["memory_context"]
            distress_history = state["distress_history"]
            lang_detection = state["lang_detection"]

            # === Layer 1: NeMo Input Rail ===
            with REQUEST_LATENCY.labels(stage="guardrails").time():
                input_check = await self.container.guardrails.check_input(user_msg_en)

            if input_check["blocked"]:
                logger.info(f"Input blocked: {input_check['reason']}")
                REQUEST_COUNT.labels(status="blocked").inc()
                blocked_resp = input_check["response"]
                if is_indic:
                    blocked_resp = await self.container.translation.translate_text(
                        text=blocked_resp, source_lang="en", target_lang=preferred_lang
                    )
                return ChatResponse(
                    response=blocked_resp,
                    blocked=True,
                    block_reason=input_check["reason"],
                )

            # === Depression Detection ===
            try:
                if self.container.serene_mind:
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
                    assessment = await self.container.serene_mind.analyze_with_history(
                        user_msg_en, history=chat_history_en + assessment_history
                    )
                    if assessment.level.value >= 2:
                        logger.info(
                            f"Distress detected ({assessment.level.name}), passing to RAG pipeline for compassionate response."
                        )
            except Exception as e:
                logger.warning(f"Serene Mind detection failed (non-fatal): {e}")

            # === PROACTIVE SERENE MIND TRIGGERING ===
            try:
                if self.container.serene_mind and self.container.user_profile:
                    current_assessment = locals().get("assessment")
                    if current_assessment is None:
                        current_assessment = DistressAssessment(
                            level=DistressLevel.NONE,
                            confidence=0.0,
                            detected_signals=[],
                            language_detected=lang_detection.primary.value,
                            recommended_response_type="normal",
                        )

                    proactive_assessment = await self.container.serene_mind.analyze_distress_trend(
                        user_id=user_id,
                        current_assessment=current_assessment,
                        user_profile_service=self.container.user_profile,
                    )

                    if proactive_assessment:
                        _client_ts = chat_body.last_serene_mind_at or 0.0
                        _now = time.time()
                        _COOLDOWN_SECS = 15 * 60
                        _skip_cooldown = (_now - _client_ts) < _COOLDOWN_SECS

                        if not _skip_cooldown and self.container.user_profile:
                            _db_ts = await self.container.user_profile.get_last_meditation_session(user_id)
                            if _db_ts and (_now - _db_ts) < _COOLDOWN_SECS:
                                _skip_cooldown = True

                        if not _skip_cooldown:
                            logger.info(
                                f"Proactive Serene Mind triggered for user {user_id}: "
                                f"level={proactive_assessment.level.name}, "
                                f"confidence={proactive_assessment.confidence:.2f}"
                            )
                            state["proactive_serene_mind"] = {
                                "triggered": True,
                                "level": proactive_assessment.level.name,
                                "confidence": proactive_assessment.confidence,
                                "signals": proactive_assessment.detected_signals,
                                "suggested_response": self.container.serene_mind.get_response(
                                    proactive_assessment
                                ),
                                "teachings_prelude": (
                                    "Sri Krishnaji and Preethaji teach us that suffering is not the truth of who you are. "
                                    "Every moment of pain is also a doorway to awakening. "
                                    "You are not alone in this — Mukti Guru is here with you. "
                                    "Before we continue, let's pause together in a moment of Serene Mind."
                                ),
                            }
                        else:
                            logger.info(
                                f"Proactive Serene Mind skipped for {user_id} — within 15-min cooldown."
                            )
            except Exception as e:
                logger.warning(f"Proactive Serene Mind analysis failed (non-fatal): {e}")
        except CircuitOpenException:
            logger.warning(
                "Sarvam API circuit breaker is OPEN in ChatRequestOrchestrator outer check — failing fast"
            )
            if is_benchmark:
                raise HTTPException(
                    status_code=503, detail="Service temporarily unavailable - circuit breaker is OPEN"
                )
            else:
                return ChatResponse(
                    response="I apologize, but the service is temporarily unavailable. Please try again in a moment.",
                    intent="ERROR",
                    meditation_step=0,
                    citations=[],
                    trace_id=str(uuid.uuid4()),
                    latency_ms=int((time.time() - start_time) * 1000),
                    model_used=getattr(settings, "sarvam_cloud_model", None)
                    or getattr(settings, "ollama_model", None),
                    model_provider=getattr(settings, "llm_provider", None),
                    route_decision="error",
                )

        # === Layers 2-11: LangGraph RAG Pipeline ===
        try:
            async def run_pipeline():
                initial_state = create_initial_state(
                    question=user_msg_en,
                    chat_history=chat_history_en,
                    meditation_step=chat_body.meditation_step,
                    request_id=correlation_id_var.get(),
                )
                initial_state["detected_language"] = lang_detection.primary.value
                initial_state["user_id"] = user_id
                initial_state["memory_context"] = memory_context

                import random
                if settings.ab_testing_enabled and random.random() < settings.ab_testing_ratio:
                    initial_state["ab_model"] = "krutrim"
                else:
                    initial_state["ab_model"] = "primary"

                budget = TimeoutBudget(total_budget=settings.pipeline_timeout)
                token = budget_var.set(budget)
                graph_variant = select_graph_for_query(user_msg_en)
                initial_state["query_tier"] = graph_variant

                if graph_variant == "fast" and getattr(settings, "use_openrouter_for_simple", False):
                    try:
                        openrouter = getattr(self.container, "openrouter", None)
                        if openrouter and openrouter.is_available:
                            logger.info("OpenRouter fast path: bypassing graph for simple factual query")
                            answer = await openrouter.generate(
                                system_prompt=(
                                    "You are a helpful spiritual guide. Provide accurate, "
                                    "spiritual answers based on the teachings of Sri Preethaji "
                                    "and Sri Krishnaji. Keep answers concise and factual."
                                ),
                                user_prompt=user_msg_en,
                                timeout=30.0,
                            )
                            logger.info("OpenRouter fast path: success")
                            return {**initial_state, "final_answer": answer, "intent": "QUERY", "citations": []}
                    except Exception as e:
                        logger.warning(f"OpenRouter fast path failed ({e}), falling through to graph pipeline")

                selected_graph = getattr(self.container, f"{graph_variant}_graph")
                try:
                    return await selected_graph.ainvoke(initial_state)
                finally:
                    budget_var.reset(token)

            history_hash = hashlib.md5(str([m['content'] for m in chat_history_en[-4:]]).encode()).hexdigest()[:8]
            result = await asyncio.wait_for(
                coalescer.get_or_run(
                    f"{preferred_lang}:{user_msg_en}:{history_hash}",
                    run_pipeline,
                ),
                timeout=settings.pipeline_timeout,
            )

            final_answer = result.get("final_answer", "I apologize, something went wrong.")
            intent = result.get("intent", "CASUAL")
            if intent == "FACTUAL":
                intent = "QUERY"
            med_step = result.get("meditation_step", 0)
            citations = result.get("citations", [])
            REQUEST_COUNT.labels(status="success").inc()

            final_answer_native = final_answer
            if is_indic:
                final_answer_native = await self.container.translation.translate_text(
                    text=final_answer, source_lang="en", target_lang=preferred_lang
                )
                logger.info(f"Translated final answer to {preferred_lang}: {final_answer_native}")

            # Save conversation memory
            if self.container.user_profile:
                from services.user_profile_service import ConversationMemory

                memory = ConversationMemory(
                    session_id=stable_session_id,
                    user_id=user_id,
                    started_at=time.time(),
                    messages=[
                        {"role": "user", "content": user_msg},
                        {"role": "assistant", "content": final_answer_native},
                    ],
                    key_insights=[c if isinstance(c, str) else c.get("title", "") for c in citations],
                    emotional_arc=[
                        {
                            "timestamp": time.time(),
                            "distress_level": assessment.level.value if "assessment" in locals() else 0,
                            "topic": intent,
                        }
                    ],
                    follow_up_suggestions=[],
                )
                background_tasks.add_task(self.container.user_profile.save_conversation_memory, memory)

            if settings.feature_memory_write and getattr(self.container, "memory_service", None):
                full_msgs = chat_history + [
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": final_answer_native}
                ]
                background_tasks.add_task(
                    self.container.memory_service.extract_and_write,
                    user_id,
                    stable_session_id,
                    full_msgs
                )

            if intent in ["QUERY", "CASUAL", "FACTUAL"]:
                self.container.exact_cache.put(
                    query=cache_key,
                    response=final_answer_native,
                    intent=intent,
                    citations=citations,
                    meditation_step=med_step,
                )
                await asyncio.to_thread(
                    self.container.semantic_cache.put,
                    query=cache_key,
                    response=final_answer_native,
                    intent=intent,
                    citations=citations,
                    meditation_step=med_step,
                )

            final_answer = final_answer_native

        except TimeoutError:
            logger.error(f"Pipeline timeout after {settings.pipeline_timeout}s for: {user_msg[:100]}")
            REQUEST_COUNT.labels(status="timeout").inc()
            final_answer = (
                "I apologize, the process took too long. 🙏 Please try asking your question again."
            )
            if is_indic:
                final_answer = await self.container.translation.translate_text(
                    text=final_answer, source_lang="en", target_lang=preferred_lang
                )
            intent = "ERROR"
            med_step = 0
            citations = []
        except CircuitOpenException:
            logger.warning("Sarvam API circuit breaker is OPEN in ChatRequestOrchestrator — failing fast")
            REQUEST_COUNT.labels(status="circuit_open").inc()
            final_answer = "I apologize, but the service is temporarily unavailable. Please try again in a moment."
            if is_indic:
                final_answer = await self.container.translation.translate_text(
                    text=final_answer, source_lang="en", target_lang=preferred_lang
                )
            intent = "ERROR"
            med_step = 0
            citations = []
        except Exception as e:
            logger.error(f"Unexpected error in pipeline: {e}", exc_info=True)
            REQUEST_COUNT.labels(status="error").inc()
            final_answer = "I apologize, an unexpected error occurred. 🙏 Please try again."
            if is_indic:
                final_answer = await self.container.translation.translate_text(
                    text=final_answer, source_lang="en", target_lang=preferred_lang
                )
            intent = "ERROR"
            med_step = 0
            citations = []

        # === Layer 12: NeMo Output Rail ===
        output_check = await self.container.guardrails.check_output(final_answer)
        if output_check["blocked"]:
            logger.info(f"Output moderated: {output_check['reason']}")
            final_answer = output_check["moderated_response"]

        query_id = str(uuid.uuid4())
        latency_ms = int((time.time() - start_time) * 1000)

        # Collect retrieval metadata from result
        retrieval_meta = None
        if citations:
            retrieval_meta = {
                "chunk_ids": [c.get("id") if isinstance(c, dict) else "" for c in citations],
                "source_docs": [c.get("source_url") if isinstance(c, dict) else c for c in citations],
                "scores": [c.get("score", 0.0) if isinstance(c, dict) else 1.0 for c in citations],
                "top_k": len(citations),
                "hit": len(citations) > 0,
            }

        # Collect trigger events (Distress)
        trigger_events = []
        if "assessment" in locals() and assessment.level.value >= 2:
            trigger_events.append(
                {
                    "name": "DISTRESS",
                    "metadata": {
                        "level": assessment.level.name,
                        "confidence": assessment.confidence,
                        "signals": assessment.detected_signals,
                    },
                }
            )

        # Extract spans from LangGraph metrics
        spans_data = []
        if "result" in locals() and isinstance(result, dict) and result.get("metrics"):
            for node_name, duration_sec in result["metrics"].items():
                spans_data.append(
                    {"span_name": node_name, "start_ms": 0, "duration_ms": int(duration_sec * 1000)}
                )

        # Extract safety events
        safety_events = []
        if "input_check" in locals() and isinstance(input_check, dict) and input_check.get("blocked"):
            safety_events.append(
                {
                    "event_type": "INPUT_GUARDRAIL",
                    "decision": "BLOCKED",
                    "reason": input_check.get("reason") or "Harmful input detected",
                }
            )
        if "output_check" in locals() and isinstance(output_check, dict) and output_check.get("blocked"):
            safety_events.append(
                {
                    "event_type": "OUTPUT_GUARDRAIL",
                    "decision": "BLOCKED",
                    "reason": output_check.get("reason") or "Harmful output detected",
                }
            )

        is_rag = intent == "QUERY"
        response_data = {
            "faithfulness": result.get("faithfulness_score", 0.0)
            if is_rag and "result" in locals() and isinstance(result, dict)
            else 1.0,
            "answer_relevancy": 1.0,
            "context_precision": 1.0,
            "context_recall": 1.0,
            "hallucination_flag": not result.get("is_faithful", True)
            if is_rag and "result" in locals() and isinstance(result, dict)
            else False,
            "judge_reasoning": result.get("verification_reason", "")
            if is_rag and "result" in locals() and isinstance(result, dict)
            else "",
        }

        tokens_per_second = round(
            max(1, len(final_answer.split())) / max(latency_ms / 1000, 0.001), 2
        )

        # Log to telemetry
        background_tasks.add_task(
            self.telemetry_sink.log_query_trace,
            query_id=query_id,
            session_id=stable_session_id,
            user_id=user_id,
            query_text=user_msg,
            model=getattr(settings, "sarvam_cloud_model", None)
            or getattr(settings, "ollama_model", None)
            or "unknown",
            latency_ms=latency_ms,
            status="ok" if intent != "ERROR" else "error",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            response_text=final_answer,
            citations=citations,
            faithfulness=response_data["faithfulness"],
            answer_relevancy=response_data["answer_relevancy"],
            context_precision=response_data["context_precision"],
            context_recall=response_data["context_recall"],
            hallucination_flag=response_data["hallucination_flag"],
            confidence_score=result.get("confidence_score")
            if "result" in locals() and isinstance(result, dict)
            else None,
            judge_reasoning=response_data["judge_reasoning"],
            retrieval_metadata=retrieval_meta,
            spans=spans_data,
            trigger_events=trigger_events,
            safety_events=safety_events,
            provider=getattr(settings, "llm_provider", None),
            route_decision=intent.lower(),
            cache_hit=False,
            tokens_per_second=tokens_per_second,
            evaluation_trace=result.get("evaluation_trace")
            if "result" in locals() and isinstance(result, dict)
            else None,
        )

        return ChatResponse(
            response=final_answer,
            intent=intent,
            meditation_step=med_step,
            citations=citations,
            blocked=False,
            proactive_serene_mind=state.get("proactive_serene_mind") if "state" in locals() else None,
            trace_id=query_id,
            latency_ms=latency_ms,
            model_used=getattr(settings, "sarvam_cloud_model", None)
            or getattr(settings, "ollama_model", None),
            model_provider=getattr(settings, "llm_provider", None),
            route_decision=intent.lower(),
            query_tier=state.get("query_tier") if "state" in locals() else None,
        )


