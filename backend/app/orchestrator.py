"""Mukthi Guru — Chat Request Orchestrator (thin wrapper)

Design Patterns:
  - Facade: Delegates all pipeline logic to PipelineCoordinator
  - Telemetry: Adds background trace logging after coordinator result
"""

from __future__ import annotations

import time
import uuid
import logging

from fastapi import BackgroundTasks, HTTPException, Request

from app.config import settings
from app.dependencies import ServiceContainer
from app.pipeline import PipelineCoordinator
from app.schemas import ChatRequest, ChatResponse
from app.telemetry_sink import SupabaseTelemetrySink
from rag.memory import normalize_session_id

logger = logging.getLogger(__name__)


class ChatRequestOrchestrator:
    """Thin orchestrator that delegates pipeline work to PipelineCoordinator."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.coordinator = PipelineCoordinator(container)
        self.telemetry_sink = SupabaseTelemetrySink()

    async def orchestrate(
        self,
        request: Request,
        chat_body: ChatRequest,
        background_tasks: BackgroundTasks,
        user: dict,
    ) -> ChatResponse:
        """Execute full pipeline and log telemetry."""
        user_msg = chat_body.user_message.strip()
        preferred_lang = chat_body.language or "en"
        user_id = user.get("id", "anonymous") if user else "anonymous"
        session_id = normalize_session_id(chat_body.session_id, user_id)

        if not user_msg:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        if len(user_msg) > settings.max_input_length:
            raise HTTPException(
                status_code=400,
                detail=f"Message too long. Please keep it under {settings.max_input_length} characters.",
            )

        is_benchmark = request.headers.get("X-Test-Key") == settings.jwt_secret

        result = await self.coordinator.execute(
            user_msg=user_msg,
            preferred_lang=preferred_lang,
            chat_body=chat_body,
            meditation_step=chat_body.meditation_step,
            session_id=chat_body.session_id,
            user=user,
            is_benchmark=is_benchmark,
        )

        # Telemetry background logging
        background_tasks.add_task(
            self._log_telemetry,
            result=result,
            user_id=user_id,
            session_id=session_id,
            user_msg=user_msg,
        )

        return ChatResponse(
            response=result.final_answer,
            intent=result.intent,
            meditation_step=result.meditation_step,
            citations=result.citations,
            blocked=result.blocked,
            block_reason=result.block_reason,
            trace_id=result.trace_id,
            latency_ms=result.latency_ms,
            model_used=result.model_used,
            model_provider=result.model_provider,
            route_decision=result.route_decision,
            query_tier=result.query_tier,
            cache_hit=result.cache_hit,
            proactive_serene_mind=result.proactive_serene_mind,
            faithfulness_score=result.faithfulness_score,
            hallucination_flag=result.hallucination_flag,
        )

    async def _log_telemetry(
        self,
        result,
        user_id: str,
        session_id: str,
        user_msg: str,
    ) -> None:
        """Log query trace to telemetry sink."""
        try:
            self.telemetry_sink.log_query_trace(
                query_id=result.trace_id,
                session_id=session_id,
                user_id=user_id,
                query_text=user_msg,
                model=result.model_used or "unknown",
                latency_ms=result.latency_ms,
                status="ok" if result.intent != "ERROR" else "error",
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                response_text=result.final_answer,
                citations=result.citations,
                faithfulness=result.faithfulness_score,
                answer_relevancy=result.answer_relevancy,
                context_precision=result.context_precision,
                context_recall=result.context_recall,
                hallucination_flag=result.hallucination_flag,
                confidence_score=result.confidence_score,
                judge_reasoning=result.judge_reasoning,
                retrieval_metadata=result.retrieval_metadata,
                spans=result.spans,
                trigger_events=result.trigger_events,
                safety_events=result.safety_events,
                provider=result.model_provider,
                route_decision=result.route_decision,
                cache_hit=result.cache_hit,
                tokens_per_second=round(
                    max(1, len(result.final_answer.split())) / max(result.latency_ms / 1000, 0.001), 2
                ) if result.latency_ms else 0.0,
                evaluation_trace=result.evaluation_trace,
            )
        except Exception as e:
            logger.warning(f"Telemetry logging failed (non-fatal): {e}")
