"""Mukthi Guru — Chat Request Orchestrator (thin wrapper)

Design Patterns:
  - Facade: Delegates all pipeline logic to PipelineCoordinator
  - Telemetry: Adds background trace logging after coordinator result
"""

from __future__ import annotations

import asyncio
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
        assistant_slug = (
            chat_body.assistant.slug if chat_body.assistant else None
        )

        if not user_msg:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        if len(user_msg) > settings.max_input_length:
            raise HTTPException(
                status_code=400,
                detail=f"Message too long. Please keep it under {settings.max_input_length} characters.",
            )

        is_benchmark = request.headers.get("X-Test-Key") == settings.jwt_secret

        try:
            result = await self.coordinator.execute(
                user_msg=user_msg,
                preferred_lang=preferred_lang,
                chat_body=chat_body,
                meditation_step=chat_body.meditation_step,
                session_id=chat_body.session_id,
                user=user,
                is_benchmark=is_benchmark,
            )
        except asyncio.TimeoutError:
            logger.error(f"Pipeline timeout for user {user_id}: message='{user_msg[:60]}...'")
            raise HTTPException(
                status_code=504,
                detail="The Guru took too long to respond. Please try again.",
            )

        # Telemetry background logging
        background_tasks.add_task(
            self._log_telemetry,
            result=result,
            user_id=user_id,
            session_id=session_id,
            user_msg=user_msg,
            assistant_slug=assistant_slug,
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
        assistant_slug: Optional[str] = None,
    ) -> None:
        """Log query trace to telemetry sink."""
        try:
            await self.telemetry_sink.log_query_trace(
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
                assistant_slug=assistant_slug,
            )
        except Exception as e:
            logger.warning(f"Telemetry logging failed (non-fatal): {e}")


# ── Job Queue Worker Factory ─────────────────────────────────────────────


async def queue_worker_factory(
    request_data: dict,
    is_stream: bool,
    job_id: str,
) -> dict:
    """Called by JobQueueService workers to execute pipeline jobs.

    Reconstructs orchestrator state from serialized request_data.
    """
    from app.dependencies import get_container
    from app.schemas import ChatRequest
    container = get_container()
    user = request_data.get("user", {})
    chat_body = ChatRequest(**request_data.get("chat_body", {}))

    if is_stream:
        from app.stream_orchestrator import ChatStreamRequestOrchestrator
        orch = ChatStreamRequestOrchestrator(container)
        stream_queue: asyncio.Queue = asyncio.Queue()
        pipeline_task = asyncio.create_task(
            orch.coordinator.execute(
                user_msg=chat_body.user_message.strip(),
                preferred_lang=chat_body.language or "en",
                chat_body=chat_body,
                meditation_step=chat_body.meditation_step,
                session_id=chat_body.session_id,
                user=user,
                is_benchmark=False,
                stream_queue=stream_queue,
            )
        )
        drain_task = asyncio.create_task(
            _drain_stream_to_redis(stream_queue, pipeline_task, job_id, container)
        )
        try:
            await pipeline_task
        except Exception:
            pass
        await drain_task
        return {"job_id": job_id, "status": "streamed"}

    orch = ChatRequestOrchestrator(container)
    try:
        from unittest.mock import MagicMock
        fake_request = MagicMock()
        fake_request.headers.get.return_value = None
        from fastapi import BackgroundTasks
        fake_bg = BackgroundTasks()
        response = await orch.orchestrate(fake_request, chat_body, fake_bg, user)
        await fake_bg()
        return _response_to_dict(response)
    except HTTPException as exc:
        return {"error": exc.detail, "status_code": exc.status_code}
    except Exception as exc:
        logger.error(f"Queue worker: job {job_id} failed: {exc}")
        return {"error": str(exc)}


async def _drain_stream_to_redis(
    stream_queue: asyncio.Queue,
    pipeline_task: asyncio.Task,
    job_id: str,
    container: ServiceContainer,
) -> None:
    """Drain SSE events from stream_queue into Redis Stream, best-effort."""
    try:
        import json
        r = None
        if container.job_queue:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
        stream_key = f"job:stream:{job_id}:events"
        HEARTBEAT_INTERVAL = 5.0
        while True:
            if pipeline_task.done() and stream_queue.empty():
                break
            try:
                if pipeline_task.done():
                    item = stream_queue.get_nowait()
                else:
                    get_task = asyncio.create_task(stream_queue.get())
                    heartbeat = asyncio.create_task(asyncio.sleep(HEARTBEAT_INTERVAL))
                    done, pending = await asyncio.wait(
                        [pipeline_task, get_task, heartbeat],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if get_task in done:
                        heartbeat.cancel()
                        item = get_task.result()
                    else:
                        get_task.cancel()
                        heartbeat.cancel()
                        try:
                            await get_task
                        except asyncio.CancelledError:
                            pass
                        if stream_queue.empty():
                            break
                        item = stream_queue.get_nowait()
            except (asyncio.QueueEmpty, ValueError):
                break
            if r:
                payload = json.dumps(item, default=str) if isinstance(item, dict) else item
                try:
                    await r.xadd(stream_key, {"data": payload}, maxlen=1000)
                except Exception:
                    pass
        if r:
            await r.xadd(stream_key, {"data": "__COMPLETE__"}, maxlen=1000)
            await r.expire(stream_key, 600)
            await r.close()
    except Exception as exc:
        logger.warning(f"Stream drain failed for {job_id}: {exc}")


def _response_to_dict(response) -> dict:
    """Convert ChatResponse to a JSON-serializable dict."""
    import dataclasses
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if hasattr(response, "dict"):
        return response.dict()
    if dataclasses.is_dataclass(response):
        return dataclasses.asdict(response)
    return {"response": str(response)}
