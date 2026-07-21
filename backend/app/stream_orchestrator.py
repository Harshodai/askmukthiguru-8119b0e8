"""Mukthi Guru — Chat Stream Request Orchestrator (thin wrapper)

Delegates non-streaming work (cache, guardrails, graph result assembly)
to PipelineCoordinator. Keeps SSE streaming logic for real-time tokens.
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
from app.dependencies import ServiceContainer
from app.orchestrator import _coerce_citations_to_str
from app.pipeline import PipelineCoordinator
from app.schemas import ChatRequest
from app.telemetry_sink import SupabaseTelemetrySink
from rag.memory import normalize_session_id
from rag.nodes.generation import _clean_inline_citations

logger = logging.getLogger(__name__)


class ChatStreamRequestOrchestrator:
    """Thin orchestrator that delegates pipeline work to PipelineCoordinator."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.coordinator = PipelineCoordinator(container)
        self.telemetry_sink = SupabaseTelemetrySink()

    async def orchestrate_stream(
        self,
        request: Request,
        chat_body: ChatRequest,
        background_tasks: BackgroundTasks,
        user: dict,
    ) -> StreamingResponse:
        """Execute streaming conversation pipeline."""
        user_msg = chat_body.user_message.strip()
        preferred_lang = chat_body.language or "en"
        user_id = user.get("id", "anonymous") if user else "anonymous"
        assistant_slug = (
            chat_body.assistant.slug if chat_body.assistant else None
        )
        is_benchmark = request.headers.get("X-Test-Key") == settings.jwt_secret

        if not user_msg:
            async def _empty():
                yield "event: error\ndata: Message cannot be empty\n\n"
            return StreamingResponse(_empty(), media_type="text/event-stream")

        if len(user_msg) > settings.max_input_length:
            msg = f"Message too long. Please keep it under {settings.max_input_length} characters."
            async def _too_long():
                yield f"event: error\ndata: {msg}\n\n"
            return StreamingResponse(_too_long(), media_type="text/event-stream")

        # Create an asyncio.Queue to receive streaming events
        stream_queue = asyncio.Queue()
        session_id = normalize_session_id(chat_body.session_id, user_id)

        # Run execute as a background task
        pipeline_task = asyncio.create_task(
            self.coordinator.execute(
                user_msg=user_msg,
                preferred_lang=preferred_lang,
                chat_body=chat_body,
                meditation_step=chat_body.meditation_step,
                session_id=chat_body.session_id,
                user=user,
                is_benchmark=is_benchmark,
                stream_queue=stream_queue,
            )
        )

        # Stream result as SSE
        async def _sse():
            tokens_streamed = 0
            _ttft_recorded = False
            _t0 = asyncio.get_event_loop().time()
            try:
                yield "event: status\ndata: Query received, starting pipeline…\n\n"

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
                                return_when=asyncio.FIRST_COMPLETED
                            )
                            if get_task in done:
                                heartbeat.cancel()
                                item = get_task.result()
                            elif heartbeat in done:
                                get_task.cancel()
                                try:
                                    await get_task
                                except asyncio.CancelledError:
                                    pass
                                if tokens_streamed == 0:
                                    yield "event: status\ndata: The Guru is connecting with the teachings...\n\n"
                                continue
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

                    # Process streaming item
                    if isinstance(item, dict):
                        event_type = item.get("event", "status")
                        event_data = item.get("data", "")
                        yield f"event: {event_type}\ndata: {event_data}\n\n"
                    elif isinstance(item, str):
                        if not _ttft_recorded:
                            try:
                                from app.metrics import TTFT_SECONDS
                                TTFT_SECONDS.labels(provider="stream").observe(
                                    asyncio.get_event_loop().time() - _t0
                                )
                            except Exception:
                                pass
                            _ttft_recorded = True
                        # Emit raw token as-is: whitespace and newlines are
                        # significant for readability during streaming.
                        # Final answer cleanup runs on the assembled text
                        # in generation.py (_clean_inline_citations there).
                        if not item:
                            continue
                        tokens_streamed += len(item)
                        escaped = item.replace("\n", "\\n")
                        yield f"event: token\ndata: {escaped}\n\n"

                # Pipeline task completed
                result = await pipeline_task
            except asyncio.TimeoutError:
                logger.error(f"Pipeline timeout for user {user_id}: message='{user_msg[:60]}...'")
                yield "event: error\ndata: The Guru took too long to respond. Please try again.\n\n"
                return
            except Exception as e:
                logger.error(f"Pipeline execution failed: {e}")
                yield f"event: error\ndata: Internal server error\n\n"
                return
            finally:
                if not pipeline_task.done():
                    pipeline_task.cancel()
                    try:
                        await pipeline_task
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        pass

            # If blocked, emit only done
            if result.blocked:
                yield f"event: token\ndata: {result.final_answer}\n\n"
                meta = json.dumps({
                    "blocked": True,
                    "block_reason": result.block_reason,
                    "intent": result.intent,
                })
                yield f"event: done\ndata: {meta}\n\n"
                return

            # Simulate streaming if no real-time tokens were received (e.g. cache hit)
            if tokens_streamed == 0:
                final = result.final_answer
                for i in range(0, len(final), 20):
                    chunk = final[i : i + 20]
                    escaped = chunk.replace("\n", "\\n")
                    yield f"event: token\ndata: {escaped}\n\n"
                    await asyncio.sleep(0.01)

            # Done event with metadata
            meta = json.dumps({
                "intent": result.intent,
                "citations": _coerce_citations_to_str(result.citations),
                "meditation_step": result.meditation_step,
                "proactive_serene_mind": result.proactive_serene_mind,
                "trace_id": result.trace_id,
                "latency_ms": result.latency_ms,
                "model_used": result.model_used,
                "model_provider": result.model_provider,
                "route_decision": result.route_decision,
                "query_tier": result.query_tier,
                "cache_hit": result.cache_hit,
                "faithfulness_score": result.faithfulness_score,
                "hallucination_flag": result.hallucination_flag,
                "follow_up_suggestions": result.follow_up_suggestions,
                "confidence_score": result.confidence_score,
            })
            yield f"event: done\ndata: {meta}\n\n"

            # Log telemetry in background
            background_tasks.add_task(
                self._log_telemetry, result, user_id, session_id, user_msg, assistant_slug
            )

        return StreamingResponse(_sse(), media_type="text/event-stream")

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
                citations_verified=result.citations_verified,
                orphan_citations_stripped=result.orphan_citations_stripped,
            )
        except Exception as e:
            logger.warning(f"Telemetry logging failed (non-fatal): {e}")
