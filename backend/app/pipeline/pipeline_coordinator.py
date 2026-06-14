"""Mukthi Guru — Pipeline Coordinator

Extracts the shared conversational pipeline logic from both
ChatRequestOrchestrator and ChatStreamRequestOrchestrator.

Responsibilities (in order):
  1. Cache lookup (exact + semantic)
  2. Circuit-breaker pre-check
  3. Request-state preparation (language detection, translation, memory)
  4. Input guardrails
  5. Distress detection (Serene Mind)
  6. Proactive Serene Mind triggering
  7. LangGraph execution (fast / standard / deep)
  8. Post-processing (translation, memory saving, cache update)
  9. Output guardrails
  10. Telemetry data assembly

All spiritual-accuracy guarantees (guardrails, distress detection,
verification thresholds, doctrinal keyword injection) are preserved.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from typing import Any

from app.config import settings
from app.context import correlation_id_var
from app.dependencies import ServiceContainer
from app.metrics import REQUEST_COUNT, REQUEST_LATENCY
from app.orchestrator_utils import (
    cache_language_key,
    get_expected_keywords,
    prepare_request_state,
    select_graph_for_query,
)
from app.pipeline.result import PipelineResult
from app.telemetry.publisher import TelemetryPublisher
from langgraph.errors import GraphRecursionError
from rag.graph import create_initial_state
from rag.memory import normalize_session_id
from rag.timeout_utils import TimeoutBudget, budget_var
from services.serene_mind_engine import DistressAssessment, DistressLevel

logger = logging.getLogger(__name__)


class PipelineCoordinator:
    """Core pipeline shared between sync and streaming orchestrators."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.telemetry = TelemetryPublisher()

    async def _stage(
        self,
        name: str,
        trace_id: str,
        *,
        start_ns: int = 0,
        status: str = "success",
        error_type: str = None,
        metadata: dict = None,
    ) -> None:
        """Emit a StageCompleted telemetry event."""
        latency_ms = int((time.time_ns() - start_ns) / 1_000_000) if start_ns else 0
        await self.telemetry.stage_complete(
            name, trace_id, latency_ms=latency_ms, status=status, error_type=error_type, metadata=metadata
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        *,
        user_msg: str,
        preferred_lang: str,
        chat_body: Any,
        meditation_step: int = 0,
        session_id: str | None = None,
        user: dict | None = None,
        is_benchmark: bool = False,
    ) -> PipelineResult:
        """Execute the full pipeline and return a PipelineResult.

        Parameters
        ----------
        user_msg:
            Stripped user message (already validated by orchestrator).
        preferred_lang:
            User's preferred language code.
        chat_body:
            ChatRequest or ChatStreamRequest object (for state preparation).
        meditation_step:
            Current meditation step if applicable.
        session_id:
            Session ID for memory / cache correlation.
        user:
            Authenticated user dict (or None for anonymous).
        is_benchmark:
            Whether this is a benchmark request (affects circuit-breaker behaviour).

        Returns
        -------
        PipelineResult:
            Immutable result object with all pipeline outputs.
        """
        start_time = time.time()
        cache_key = cache_language_key(user_msg, preferred_lang)
        is_indic = preferred_lang and not preferred_lang.startswith("en")
        user_id = user.get("id", "anonymous") if user else "anonymous"
        stable_session_id = normalize_session_id(session_id, user_id)

        # Extract messages list for downstream use
        chat_body_messages = [m.model_dump() for m in chat_body.messages] if hasattr(chat_body, "messages") else []

        trace_id = str(uuid.uuid4())

        # ------------------------------------------------------------------
        # 1. Cache Check
        # ------------------------------------------------------------------
        _s = time.time_ns()
        cached_result = await self._check_cache(cache_key, is_indic, preferred_lang)
        await self._stage("cache_check", trace_id, start_ns=_s, status="cached" if cached_result else "success")
        if cached_result is not None:
            latency_ms = int((time.time() - start_time) * 1000)
            return cached_result.with_latency(latency_ms)

        # ------------------------------------------------------------------
        # 2. Circuit Breaker
        # ------------------------------------------------------------------
        _s = time.time_ns()
        circuit_open = self._is_circuit_open()
        await self._stage("circuit_breaker", trace_id, start_ns=_s, status="error" if circuit_open else "success")
        if circuit_open:
            return self._circuit_open_result(is_benchmark, start_time)

        # ------------------------------------------------------------------
        # 3. Request State Preparation
        # ------------------------------------------------------------------
        _s = time.time_ns()
        state = await prepare_request_state(self.container, chat_body, preferred_lang, user=user)
        user_msg_en = state["user_msg_en"]
        chat_history_en = state["chat_history_en"]
        memory_context = state["memory_context"]
        lang_detection = state["lang_detection"]
        await self._stage("request_state", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 4. Input Guardrails
        # ------------------------------------------------------------------
        _s = time.time_ns()
        input_check = await self._run_input_guardrails(user_msg_en)
        await self._stage("input_guardrails", trace_id, start_ns=_s, status="error" if input_check["blocked"] else "success")
        if input_check["blocked"]:
            blocked_resp = input_check["response"]
            if is_indic:
                blocked_resp = await self.container.translation.translate_text(
                    text=blocked_resp, source_lang="en", target_lang=preferred_lang
                )
            return PipelineResult(
                final_answer=blocked_resp,
                intent="ERROR",
                blocked=True,
                block_reason=input_check["reason"],
                latency_ms=int((time.time() - start_time) * 1000),
                trace_id=trace_id,
                model_used=getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None),
                model_provider=getattr(settings, "llm_provider", None),
                route_decision="blocked",
            )

        # ------------------------------------------------------------------
        # 5. Distress Detection
        # ------------------------------------------------------------------
        _s = time.time_ns()
        assessment = await self._detect_distress(user_msg_en, state)
        await self._stage("distress_detection", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 6. Proactive Serene Mind
        # ------------------------------------------------------------------
        _s = time.time_ns()
        proactive_data = await self._maybe_trigger_proactive_serene_mind(
            assessment, user_id, chat_body, state
        )
        if proactive_data:
            state["proactive_serene_mind"] = proactive_data
        await self._stage("proactive_serene_mind", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 7. LangGraph Execution
        # ------------------------------------------------------------------
        _s = time.time_ns()
        graph_result, graph_latency = await self._run_graph(
            user_msg_en,
            chat_history_en,
            meditation_step,
            lang_detection,
            memory_context,
            state.get("proactive_serene_mind"),
        )
        await self._stage("langgraph", trace_id, start_ns=_s)

        final_answer = graph_result.get("final_answer", "I apologize, something went wrong.")
        intent = graph_result.get("intent", "CASUAL")
        if intent == "FACTUAL":
            intent = "QUERY"
        med_step = graph_result.get("meditation_step", 0)
        citations = graph_result.get("citations", [])

        # ------------------------------------------------------------------
        # 8. Translation (post-graph)
        # ------------------------------------------------------------------
        _s = time.time_ns()
        if is_indic:
            final_answer = await self.container.translation.translate_text(
                text=final_answer, source_lang="en", target_lang=preferred_lang
            )
        await self._stage("translation", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 9. Memory Saving
        # ------------------------------------------------------------------
        _s = time.time_ns()
        await self._save_memory(
            user_id,
            stable_session_id,
            chat_body_messages,
            user_msg,
            final_answer,
            intent,
            med_step,
            citations,
            distress_level=assessment.level.value if assessment else 0,
        )
        await self._stage("memory_save", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 10. Cache Update
        # ------------------------------------------------------------------
        _s = time.time_ns()
        await self._update_cache(cache_key, final_answer, intent, med_step, citations)
        await self._stage("cache_update", trace_id, start_ns=_s)

        # ------------------------------------------------------------------
        # 11. Output Guardrails
        # ------------------------------------------------------------------
        _s = time.time_ns()
        output_check = await self.container.guardrails.check_output(final_answer)
        if output_check["blocked"]:
            logger.info(f"Output moderated: {output_check['reason']}")
            final_answer = output_check["moderated_response"]
        await self._stage("output_guardrails", trace_id, start_ns=_s, status="error" if output_check["blocked"] else "success")

        # ------------------------------------------------------------------
        # 12. Result Assembly
        # ------------------------------------------------------------------
        latency_ms = int((time.time() - start_time) * 1000)

        retrieval_meta = self._build_retrieval_meta(citations)
        trigger_events = self._build_trigger_events(assessment)
        safety_events = self._build_safety_events(input_check, output_check)
        spans = self._build_spans(graph_result)
        response_data = self._build_response_data(graph_result, intent)

        return PipelineResult(
            final_answer=final_answer,
            intent=intent,
            meditation_step=med_step,
            citations=citations,
            trace_id=str(uuid.uuid4()),
            latency_ms=latency_ms,
            model_used=getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None),
            model_provider=getattr(settings, "llm_provider", None),
            route_decision=intent.lower(),
            query_tier=state.get("query_tier"),
            blocked=False,
            cache_hit=False,
            proactive_serene_mind=state.get("proactive_serene_mind"),
            faithfulness_score=response_data["faithfulness"],
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
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _check_cache(self, cache_key: str, is_indic: bool, preferred_lang: str) -> PipelineResult | None:
        """Return a PipelineResult if cache hit, else None."""
        cached = self.container.exact_cache.get(cache_key)
        if cached is None:
            cached = await asyncio.to_thread(self.container.semantic_cache.get, cache_key)

        if cached is not None:
            REQUEST_COUNT.labels(status="cache_hit").inc()
            cached_response = cached["response"]
            output_check = await self.container.guardrails.check_output(cached_response)
            final_response = output_check["moderated_response"] if output_check["blocked"] else cached_response

            if is_indic and final_response != cached_response:
                final_response = await self.container.translation.translate_text(
                    text=final_response, source_lang="en", target_lang=preferred_lang
                )

            return PipelineResult(
                final_answer=final_response,
                intent=cached.get("intent"),
                meditation_step=cached.get("meditation_step", 0),
                citations=cached.get("citations", []),
                trace_id=str(uuid.uuid4()),
                latency_ms=0,
                model_used=getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None),
                model_provider=getattr(settings, "llm_provider", None),
                route_decision="semantic_cache",
                cache_hit=True,
            )
        return None

    def _is_circuit_open(self) -> bool:
        """Check if the circuit breaker is open."""
        if not settings.is_sarvam_cloud:
            return False
        underlying = self.container.ollama
        if hasattr(underlying, "_service"):
            underlying = underlying._service
        circuit = getattr(underlying, "_circuit", None)
        return circuit is not None and not circuit.can_execute()

    def _circuit_open_result(self, is_benchmark: bool, start_time: float) -> PipelineResult:
        """Return an error PipelineResult when the circuit is open."""
        model = getattr(settings, "sarvam_cloud_model", None) or getattr(settings, "ollama_model", None)
        msg = "I apologize, but the service is temporarily unavailable. Please try again in a moment."
        latency_ms = int((time.time() - start_time) * 1000)
        return PipelineResult(
            final_answer=msg,
            intent="ERROR",
            trace_id=str(uuid.uuid4()),
            latency_ms=latency_ms,
            model_used=model,
            model_provider=getattr(settings, "llm_provider", None),
            route_decision="error",
        )

    async def _run_input_guardrails(self, user_msg_en: str) -> dict:
        """Run input guardrails and return the check result."""
        with REQUEST_LATENCY.labels(stage="guardrails").time():
            return await self.container.guardrails.check_input(user_msg_en)

    async def _detect_distress(self, user_msg_en: str, state: dict) -> DistressAssessment | None:
        """Run Serene Mind distress detection. Returns None on failure (non-fatal)."""
        try:
            if self.container.serene_mind:
                distress_history = state.get("distress_history", [])
                assessment_history = (
                    [{"role": "system", "content": f"Previous distress history: {distress_history}"}]
                    if distress_history
                    else []
                )
                assessment = await self.container.serene_mind.analyze_with_history(
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
        assessment: DistressAssessment | None,
        user_id: str,
        chat_body: Any,
        state: dict,
    ) -> dict | None:
        """Check if proactive Serene Mind should be triggered."""
        try:
            if not (self.container.serene_mind and self.container.user_profile):
                return None

            current = assessment or DistressAssessment(
                level=DistressLevel.NONE,
                confidence=0.0,
                detected_signals=[],
                language_detected=state.get("lang_detection", {}).get("primary", {}).get("value"),
                recommended_response_type="normal",
            )

            proactive = await self.container.serene_mind.analyze_distress_trend(
                user_id=user_id,
                current_assessment=current,
                user_profile_service=self.container.user_profile,
            )

            if not proactive:
                return None

            _client_ts = getattr(chat_body, "last_serene_mind_at", None) or 0.0
            _now = time.time()
            _COOLDOWN = 15 * 60
            _skip = (_now - _client_ts) < _COOLDOWN

            if not _skip:
                _db_ts = await self.container.user_profile.get_last_meditation_session(user_id)
                if _db_ts and (_now - _db_ts) < _COOLDOWN:
                    _skip = True

            if _skip:
                logger.info(f"Proactive Serene Mind skipped for {user_id} — within 15-min cooldown.")
                return None

            logger.info(f"Proactive Serene Mind triggered for user {user_id}: level={proactive.level.name}, confidence={proactive.confidence:.2f}")
            return {
                "triggered": True,
                "level": proactive.level.name,
                "confidence": proactive.confidence,
                "signals": proactive.detected_signals,
                "suggested_response": self.container.serene_mind.get_response(proactive),
                "teachings_prelude": (
                    "Sri Krishnaji and Preethaji teach us that suffering is not the truth of who you are. "
                    "Every moment of pain is also a doorway to awakening. "
                    "You are not alone in this — Mukti Guru is here with you. "
                    "Before we continue, let's pause together in a moment of Serene Mind."
                ),
            }
        except Exception as e:
            logger.warning(f"Proactive Serene Mind analysis failed (non-fatal): {e}")
        return None

    async def _run_graph(
        self,
        user_msg_en: str,
        chat_history_en: list,
        meditation_step: int,
        lang_detection: Any,
        memory_context: str,
        proactive_data: dict | None,
    ) -> tuple[dict, int]:
        """Run the LangGraph pipeline and return (result, latency_ms)."""
        import random

        from app.coalescer import build_coalescer

        coalescer = build_coalescer(redis_url=getattr(settings, "redis_url", None), ttl=60.0)

        async def run():
            initial_state = create_initial_state(
                question=user_msg_en,
                chat_history=chat_history_en,
                meditation_step=meditation_step,
                request_id=correlation_id_var.get(),
            )
            initial_state["detected_language"] = lang_detection.primary.value if lang_detection else "en"
            initial_state["memory_context"] = memory_context
            initial_state["expected_keywords"] = get_expected_keywords(user_msg_en)
            if proactive_data:
                initial_state["proactive_serene_mind"] = proactive_data

            if settings.ab_testing_enabled and random.random() < settings.ab_testing_ratio:
                initial_state["ab_model"] = "krutrim"
            else:
                initial_state["ab_model"] = "primary"

            budget = TimeoutBudget(total_budget=settings.pipeline_timeout)
            token = budget_var.set(budget)
            graph_variant = await select_graph_for_query(user_msg_en, container=self.container)
            initial_state["query_tier"] = graph_variant

            # OpenRouter fast path: skip graph for simple queries (Phase 2.4 will remove this)
            if graph_variant == "fast" and getattr(settings, "use_openrouter_for_simple", False):
                try:
                    openrouter = getattr(self.container, "openrouter", None)
                    if openrouter and openrouter.is_available:
                        logger.info("OpenRouter fast path: bypassing graph for simple factual query")
                        answer = await openrouter.generate(
                            system_prompt="You are a helpful spiritual guide...",
                            user_prompt=user_msg_en,
                            timeout=30.0,
                        )
                        logger.info("OpenRouter fast path: success")
                        return {**initial_state, "final_answer": answer, "intent": "QUERY", "citations": []}
                except Exception as e:
                    logger.warning(f"OpenRouter fast path failed ({e}), falling through to graph pipeline")

            selected_graph = getattr(self.container, f"{graph_variant}_graph")
            try:
                return await selected_graph.ainvoke(initial_state, config={"recursion_limit": 60})
            except GraphRecursionError as e:
                logger.warning(f"Graph recursion limit reached ({e}). Returning fallback response.")
                return {
                    **initial_state,
                    "final_answer": "I apologize, but this question requires broader context than I can gather right now...",
                    "intent": "QUERY",
                    "citations": [],
                }
            finally:
                budget_var.reset(token)

        history_hash = hashlib.md5(str([m["content"] for m in chat_history_en[-4:]]).encode()).hexdigest()[:8]
        start_lat = time.time()
        try:
            result = await asyncio.wait_for(
                coalescer.get_or_run(f"{lang_detection.primary.value if lang_detection else 'en'}:{user_msg_en}:{history_hash}", run),
                timeout=settings.pipeline_timeout,
            )
        except asyncio.TimeoutError:
            raise
        graph_latency = int((time.time() - start_lat) * 1000)
        return result, graph_latency

    async def _save_memory(
        self,
        user_id: str,
        stable_session_id: str,
        chat_body_messages: list,
        user_msg: str,
        final_answer: str,
        intent: str,
        med_step: int,
        citations: list,
        distress_level: int = 0,
    ) -> None:
        """Save conversation memory asynchronously."""
        if not self.container.user_profile:
            return
        try:
            from services.user_profile_service import ConversationMemory

            memory = ConversationMemory(
                session_id=stable_session_id,
                user_id=user_id,
                started_at=time.time(),
                messages=[
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": final_answer},
                ],
                key_insights=[c if isinstance(c, str) else c.get("title", "") for c in citations],
                emotional_arc=[
                    {
                        "timestamp": time.time(),
                        "distress_level": distress_level,
                        "provoked": False,
                        "topic": intent,
                    }
                ],
                follow_up_suggestions=[],
            )
            await self.container.user_profile.save_conversation_memory(memory)
        except Exception as e:
            logger.warning(f"Memory save failed (non-fatal): {e}")

        if settings.feature_memory_write and getattr(self.container, "memory_service", None):
            try:
                full_msgs = chat_body_messages + [
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": final_answer},
                ]
                await self.container.memory_service.extract_and_write(user_id, stable_session_id, full_msgs)
            except Exception as e:
                logger.warning(f"Memory extraction failed (non-fatal): {e}")

    async def _update_cache(self, cache_key: str, final_answer: str, intent: str, med_step: int, citations: list) -> None:
        """Update exact and semantic caches."""
        if intent in ["QUERY", "CASUAL", "FACTUAL"]:
            try:
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
            except Exception as e:
                logger.warning(f"Cache update failed (non-fatal): {e}")

    # ------------------------------------------------------------------
    # Metadata builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_retrieval_meta(citations: list) -> dict | None:
        if not citations:
            return None
        return {
            "chunk_ids": [c.get("id") if isinstance(c, dict) else "" for c in citations],
            "source_docs": [c.get("source_url") if isinstance(c, dict) else c for c in citations],
            "scores": [c.get("score", 0.0) if isinstance(c, dict) else 1.0 for c in citations],
            "top_k": len(citations),
            "hit": len(citations) > 0,
        }

    @staticmethod
    def _build_trigger_events(assessment: DistressAssessment | None) -> list[dict]:
        if assessment and assessment.level.value >= 2:
            return [
                {
                    "name": "DISTRESS",
                    "metadata": {
                        "level": assessment.level.name,
                        "confidence": assessment.confidence,
                        "signals": assessment.detected_signals,
                    },
                }
            ]
        return []

    @staticmethod
    def _build_safety_events(input_check: dict, output_check: dict) -> list[dict]:
        events = []
        if input_check.get("blocked"):
            events.append({
                "event_type": "INPUT_GUARDRAIL",
                "decision": "BLOCKED",
                "reason": input_check.get("reason") or "Harmful input detected",
            })
        if output_check.get("blocked"):
            events.append({
                "event_type": "OUTPUT_GUARDRAIL",
                "decision": "BLOCKED",
                "reason": output_check.get("reason") or "Harmful output detected",
            })
        return events

    @staticmethod
    def _build_spans(result: dict) -> list[dict]:
        metrics = result.get("metrics")
        if not metrics:
            return []
        return [
            {"span_name": name, "start_ms": 0, "duration_ms": int(duration * 1000)}
            for name, duration in metrics.items()
        ]

    @staticmethod
    def _build_response_data(result: dict, intent: str) -> dict:
        is_rag = intent == "QUERY"
        return {
            "faithfulness": result.get("faithfulness_score", 0.0) if is_rag else 1.0,
            "answer_relevancy": 1.0,
            "context_precision": 1.0,
            "context_recall": 1.0,
            "hallucination_flag": not result.get("is_faithful") if (is_rag and result.get("is_faithful") is not None) else False,
            "judge_reasoning": result.get("verification_reason", "") if is_rag else "",
        }
