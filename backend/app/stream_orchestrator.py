"""Mukthi Guru — Chat Stream Request Orchestrator

Design Patterns:
  - Command/Mediator: Orchestrates request pipeline stages for streaming
  - Dependency Injection: Consumes decoupled service container interfaces
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastapi import BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.context import correlation_id_var
from app.dependencies import ServiceContainer
from app.metrics import REQUEST_COUNT
from app.orchestrator_utils import (
    cache_language_key,
    get_expected_keywords,
    prepare_request_state,
    select_graph_for_query,
)
from app.schemas import ChatRequest
from app.telemetry_sink import SupabaseTelemetrySink
from rag.graph import create_initial_state
from rag.memory import normalize_session_id
from rag.timeout_utils import TimeoutBudget, budget_var
from services.serene_mind_engine import DistressAssessment, DistressLevel

logger = logging.getLogger(__name__)


class ChatStreamRequestOrchestrator:
    """Orchestrates the chat stream endpoint flow: safety checks -> RAG -> output moderation -> translation."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.telemetry_sink = SupabaseTelemetrySink()

    async def orchestrate_stream(
        self,
        request: Request,
        chat_body: ChatRequest,
        background_tasks: BackgroundTasks,
        user: dict,
    ) -> StreamingResponse:
        """Execute the streaming conversation request orchestration pipeline."""
        user_msg = chat_body.user_message.strip()
        preferred_lang = chat_body.language or "en"
        is_indic = preferred_lang and not preferred_lang.startswith("en")
        cache_key = cache_language_key(user_msg, preferred_lang)
        if not user_msg:
            async def error_stream():
                yield "event: error\ndata: Message cannot be empty\n\n"
            return StreamingResponse(error_stream(), media_type="text/event-stream")

        if len(user_msg) > settings.max_input_length:
            async def length_error_stream():
                yield f"event: error\ndata: Message too long. Please keep it under {settings.max_input_length} characters.\n\n"
            return StreamingResponse(length_error_stream(), media_type="text/event-stream")

        is_benchmark = request.headers.get("X-Test-Key") == settings.jwt_secret

        if settings.is_sarvam_cloud:
            underlying_service = self.container.ollama
            if hasattr(self.container.ollama, "_service"):
                underlying_service = self.container.ollama._service

            circuit = getattr(underlying_service, "_circuit", None)
            if circuit and not circuit.can_execute():
                logger.warning(
                    "Sarvam API circuit breaker is OPEN in ChatStreamRequestOrchestrator pre-check — failing fast"
                )
                if is_benchmark:
                    raise HTTPException(
                        status_code=503,
                        detail="Service temporarily unavailable - circuit breaker is OPEN",
                    )
                else:
                    async def circuit_error_stream():
                        yield "event: token\ndata: I apologize, but the service is temporarily unavailable. Please try again in a moment.\n\n"
                        meta = json.dumps({"intent": "ERROR", "citations": [], "meditation_step": 0})
                        yield f"event: done\ndata: {meta}\n\n"
                    return StreamingResponse(circuit_error_stream(), media_type="text/event-stream")

        async def generate_sse():
            from services.cost_tracker import TokenAccumulator, token_accumulator_var
            accumulator = TokenAccumulator()
            token = token_accumulator_var.set(accumulator)
            try:
                # IMMEDIATE status event on stream start
                yield "event: status\ndata: Query received, starting pipeline…\n\n"

                # Setup heartbeat worker
                heartbeat_queue = asyncio.Queue()
                processing_done = asyncio.Event()

                async def heartbeat_worker():
                    while not processing_done.is_set():
                        await asyncio.sleep(15.0)
                        if not processing_done.is_set():
                            heartbeat_sse = "event: status\ndata: Still processing…\n\n"
                            await heartbeat_queue.put(heartbeat_sse)

                heartbeat_task = asyncio.create_task(heartbeat_worker())
                stream_start_time = time.time()

                # === Cache check ===
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

                    escaped = final_response.replace("\n", "\\n")
                    yield f"event: token\ndata: {escaped}\n\n"
                    query_id = str(uuid.uuid4())
                    latency_ms = int((time.time() - stream_start_time) * 1000)
                    meta = json.dumps(
                        {
                            "intent": cached.get("intent"),
                            "citations": cached.get("citations", []),
                            "meditation_step": cached.get("meditation_step", 0),
                            "trace_id": query_id,
                            "cache_hit": True,
                            "route_decision": "semantic_cache",
                            "model_used": getattr(settings, "sarvam_cloud_model", None)
                            or getattr(settings, "ollama_model", None),
                            "model_provider": getattr(settings, "llm_provider", None),
                        }
                    )
                    yield f"event: done\ndata: {meta}\n\n"
                    processing_done.set()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass

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
                    return

                # Cache Miss -> Execute Pipeline
                user_id = user.get("id", "anonymous") if user else "anonymous"
                start_time = time.time()

                state = await prepare_request_state(self.container, chat_body, preferred_lang, user=user)
                user_msg_en = state["user_msg_en"]
                is_indic_detected = state["is_indic"]
                chat_history_en = state["chat_history_en"]
                memory_context = state["memory_context"]
                distress_history = state["distress_history"]
                lang_detection = state["lang_detection"]
                stable_session_id = state["stable_session_id"]
                chat_history = [m.model_dump() for m in chat_body.messages]

                # === Layer 1: Input rail ===
                yield "event: status\ndata: Checking message safety...\n\n"
                input_check = await self.container.guardrails.check_input(user_msg_en)

                if input_check["blocked"]:
                    blocked_resp = input_check["response"]
                    if is_indic_detected:
                        blocked_resp = await self.container.translation.translate_text(
                            text=blocked_resp, source_lang="en", target_lang=preferred_lang
                        )
                    yield f"event: token\ndata: {blocked_resp}\n\n"
                    meta = json.dumps({"blocked": True, "block_reason": input_check["reason"]})
                    yield f"event: done\ndata: {meta}\n\n"
                    processing_done.set()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                    return

                # === Distress check ===
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
                            user_msg_en,
                            history=chat_history_en + assessment_history,
                        )
                        if assessment.level.value >= 2:
                            logger.info(
                                f"Stream: Distress detected ({assessment.level.name}), passing to RAG pipeline."
                            )
                except Exception as e:
                    logger.warning(f"Serene Mind detection failed in stream (non-fatal): {e}")

                # === Proactive Serene Mind ===
                proactive_serene_mind = None
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
                                _db_ts = await self.container.user_profile.get_last_meditation_session(
                                    user_id
                                )
                                if _db_ts and (_now - _db_ts) < _COOLDOWN_SECS:
                                    _skip_cooldown = True

                            if not _skip_cooldown:
                                logger.info(
                                    f"Stream: Proactive Serene Mind triggered for user {user_id}: "
                                    f"level={proactive_assessment.level.name}, "
                                    f"confidence={proactive_assessment.confidence:.2f}"
                                )
                                proactive_serene_mind = {
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
                                    f"Stream: Proactive Serene Mind skipped for {user_id} — within 15-min cooldown."
                                )
                except Exception as e:
                    logger.warning(f"Proactive Serene Mind analysis failed in stream (non-fatal): {e}")

                # === RAG Pipeline ===
                yield "event: status\ndata: Understanding your question...\n\n"
                initial_state = create_initial_state(
                    question=user_msg_en,
                    chat_history=chat_history_en,
                    meditation_step=chat_body.meditation_step,
                    request_id=correlation_id_var.get(),
                )
                initial_state["detected_language"] = lang_detection.primary.value
                user_id = user.get("id", "anonymous") if user else "anonymous"
                initial_state["user_id"] = user_id
                initial_state["memory_context"] = memory_context
                initial_state["expected_keywords"] = get_expected_keywords(user_msg_en)

                import random
                if settings.ab_testing_enabled and random.random() < settings.ab_testing_ratio:
                    initial_state["ab_model"] = "krutrim"
                else:
                    initial_state["ab_model"] = "primary"

                queue = asyncio.Queue()
                config = {
                    "configurable": {"stream_queue": queue},
                }

                async def run_stream_pipeline():
                    budget = TimeoutBudget(total_budget=settings.pipeline_timeout)
                    token = budget_var.set(budget)
                    graph_variant = select_graph_for_query(user_msg_en)
                    initial_state["query_tier"] = graph_variant
                    selected_graph = getattr(self.container, f"{graph_variant}_graph")
                    try:
                        return await selected_graph.ainvoke(initial_state, config=config)
                    finally:
                        budget_var.reset(token)

                pipeline_task = asyncio.create_task(
                    asyncio.wait_for(
                        run_stream_pipeline(),
                        timeout=settings.pipeline_timeout,
                    )
                )

                has_streamed_tokens = False
                while not pipeline_task.done() or not queue.empty() or not heartbeat_queue.empty():
                    try:
                        item = None
                        item_source = None
                        if not queue.empty():
                            item = await asyncio.wait_for(queue.get(), timeout=0.01)
                            item_source = 'pipeline'
                        elif not heartbeat_queue.empty():
                            item = await asyncio.wait_for(heartbeat_queue.get(), timeout=0.01)
                            item_source = 'heartbeat'
                        else:
                            await asyncio.sleep(0.05)
                            continue

                        if isinstance(item, dict):
                            event_type = item.get("event", "token")
                            data = item.get("data", "")
                            if event_type == "status":
                                yield f"event: status\ndata: {data}\n\n"
                            elif event_type == "token" and not is_indic_detected:
                                has_streamed_tokens = True
                                escaped = data.replace("\n", "\\n")
                                yield f"event: token\ndata: {escaped}\n\n"
                        elif isinstance(item, str) and (item.startswith("data: ") or item.startswith("event: ")):
                            yield item
                        elif not is_indic_detected:
                            has_streamed_tokens = True
                            escaped = item.replace("\n", "\\n")
                            yield f"event: token\ndata: {escaped}\n\n"

                        if item_source == 'pipeline':
                            try:
                                queue.task_done()
                            except ValueError:
                                pass
                        elif item_source == 'heartbeat':
                            try:
                                heartbeat_queue.task_done()
                            except ValueError:
                                pass

                    except TimeoutError:
                        continue
                    except Exception:
                        continue

                result = await pipeline_task
                processing_done.set()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

                final_answer = result.get("final_answer", "I apologize, something went wrong.")
                intent = result.get("intent", "CASUAL")
                med_step = result.get("meditation_step", 0)
                citations = result.get("citations", [])

                if is_indic_detected:
                    yield "event: status\ndata: Translating spiritual response to your language...\n\n"
                    final_answer_native = await self.container.translation.translate_text(
                        text=final_answer, source_lang="en", target_lang=preferred_lang
                    )
                    logger.info(f"Stream: Translated final answer to {preferred_lang}: {final_answer_native}")

                    output_check = await self.container.guardrails.check_output(final_answer_native)
                    if output_check["blocked"]:
                        final_answer_native = output_check["moderated_response"]

                    final_answer = final_answer_native
                    for i in range(0, len(final_answer_native), 10):
                        chunk = final_answer_native[i : i + 10]
                        escaped = chunk.replace("\n", "\\n")
                        yield f"event: token\ndata: {escaped}\n\n"
                        await asyncio.sleep(0.01)
                else:
                    output_check = await self.container.guardrails.check_output(final_answer)
                    if output_check["blocked"]:
                        final_answer = output_check["moderated_response"]

                    if not has_streamed_tokens:
                        for i in range(0, len(final_answer), 20):
                            chunk = final_answer[i : i + 20]
                            escaped = chunk.replace("\n", "\\n")
                            yield f"event: token\ndata: {escaped}\n\n"
                            await asyncio.sleep(0.01)

                if intent in ["QUERY", "CASUAL", "FACTUAL"]:
                    self.container.exact_cache.put(
                        query=cache_key,
                        response=final_answer,
                        intent=intent,
                        citations=citations,
                        meditation_step=med_step,
                    )
                    await asyncio.to_thread(
                        self.container.semantic_cache.put,
                        query=cache_key,
                        response=final_answer,
                        intent=intent,
                        citations=citations,
                        meditation_step=med_step,
                    )

                REQUEST_COUNT.labels(status="success").inc()
                query_id = str(uuid.uuid4())
                latency_ms = int((time.time() - start_time) * 1000)
                approx_tokens = max(1, len(final_answer.split()))
                tokens_per_second = round(approx_tokens / max(latency_ms / 1000, 0.001), 2)
                model_used = (
                    result.get("model_used")
                    or getattr(settings, "sarvam_cloud_model", None)
                    or getattr(settings, "ollama_model", None)
                )
                model_provider = result.get("model_provider") or getattr(settings, "llm_provider", None)
                route_decision = result.get("route_decision")

                meta = json.dumps(
                    {
                        "intent": intent,
                        "citations": citations,
                        "meditation_step": med_step,
                        "proactive_serene_mind": proactive_serene_mind,
                        "trace_id": query_id,
                        "latency_ms": latency_ms,
                        "tokens_per_second": tokens_per_second,
                        "model_used": model_used,
                        "model_provider": model_provider,
                        "route_decision": route_decision,
                        "node_timings": result.get("node_timings"),
                        "evaluation_trace": result.get("evaluation_trace"),
                        "faithfulness_score": result.get("faithfulness_score"),
                        "relevancy_score": result.get("relevancy_score"),
                        "confidence_score": result.get("confidence_score"),
                        "verification": result.get("verification"),
                    }
                )
                yield f"event: done\ndata: {meta}\n\n"

                # ── Post-done work (must not cause event:error) ──
                try:
                    if self.container.user_profile and getattr(self.container, "user_profile", None):
                        from services.user_profile_service import ConversationMemory
                        memory = ConversationMemory(
                            session_id=stable_session_id,
                            user_id=user_id,
                            started_at=time.time(),
                            messages=[
                                {"role": "user", "content": user_msg},
                                {"role": "assistant", "content": final_answer},
                            ],
                            key_insights=[],
                            emotional_arc=[],
                            follow_up_suggestions=[],
                        )
                        background_tasks.add_task(self.container.user_profile.save_conversation_memory, memory)

                    if settings.feature_memory_write and getattr(self.container, "memory_service", None):
                        full_msgs = chat_history + [
                            {"role": "user", "content": user_msg},
                            {"role": "assistant", "content": final_answer}
                        ]
                        background_tasks.add_task(
                            self.container.memory_service.extract_and_write,
                            user_id,
                            stable_session_id,
                            full_msgs,
                        )
                except Exception as post_err:
                    logger.warning(f"Stream post-done work error (non-fatal): {post_err}")

                # Telemetry
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
                            {
                                "span_name": node_name,
                                "start_ms": 0,
                                "duration_ms": int(duration_sec * 1000),
                            }
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

                if self.telemetry_sink and getattr(self.telemetry_sink, "log_query_trace", None):
                    background_tasks.add_task(
                        self.telemetry_sink.log_query_trace,
                        query_id=query_id,
                        session_id=stable_session_id,
                        user_id=user_id,
                        query_text=user_msg,
                        model=model_used or "unknown",
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
                        provider=model_provider,
                        route_decision=intent.lower(),
                        cache_hit=False,
                        tokens_per_second=tokens_per_second,
                        evaluation_trace=result.get("evaluation_trace")
                        if "result" in locals() and isinstance(result, dict)
                        else None,
                    )

            except Exception as e:
                logger.error(f"Stream error: {e}", exc_info=True)
                yield "event: error\ndata: An unexpected error occurred.\n\n"

            finally:
                try:
                    token_accumulator_var.reset(token)
                except ValueError:
                    # Token may cross async generator contexts; safe to ignore
                    pass

        return StreamingResponse(generate_sse(), media_type="text/event-stream")
