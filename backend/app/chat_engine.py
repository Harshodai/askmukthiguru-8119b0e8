"""ChatEngine — Unified Chat Processing Facade (C3).

A deep-module additive facade over the existing orchestrator layer.
It exposes a small, stable surface (``chat``, ``chat_stream``,
``chat_advanced``, ``chat_advanced_stream``) and delegates ALL real work
to the EXISTING ``PipelineCoordinator`` (batch + streaming) via the
existing ``app.pipeline`` and ``app.stream_orchestrator`` entry points.

Nothing in ``orchestrator.py``, ``stream_orchestrator.py``, or
``pipeline_coordinator.py`` is modified — ChatEngine is a pure
convenience wrapper that can be A/B tested against the current
``/api/chat`` endpoint without risk.

Usage::

    from app.chat_engine import ChatEngine
    engine = ChatEngine(container)

    # 80% case — simplest possible API
    text = await engine.chat("What is meditation?", user_id="u123")

    # Streaming, simple API
    async for chunk in engine.chat_stream("What is meditation?", user_id="u123"):
        print(chunk.text)

    # 20% case — full control (matches production endpoint)
    result = await engine.chat_advanced(chat_request, user={"id": "u123"})
    async for chunk in engine.chat_advanced_stream(chat_request, user):
        ...
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from fastapi import HTTPException

from app.config import settings
from app.dependencies import ServiceContainer
from app.schemas import ChatRequest
from rag.memory import normalize_session_id

logger = logging.getLogger(__name__)


class UserContext:
    """Minimal user context for the simple API."""

    def __init__(self, user_id: str, email: str = "", tenant_id: str = "default"):
        self.user_id = user_id
        self.email = email
        self.tenant_id = tenant_id


class ChatResult:
    """Unified result — works for both batch and streaming."""

    def __init__(self) -> None:
        self.final_answer: str = ""
        self.intent: str = ""
        self.citations: list[str] = []
        self.blocked: bool = False
        self.block_reason: str = ""
        self.trace_id: str = ""
        self.latency_ms: int = 0
        self.model_used: str = ""
        self.model_provider: str = ""
        self.route_decision: str = ""
        self.query_tier: str = ""
        self.cache_hit: bool = False
        # PipelineResult.proactive_serene_mind is dict | None (trigger details),
        # not a bool — preserve the richer shape for callers.
        self.proactive_serene_mind: Any = None
        self.faithfulness_score: float = 0.0
        self.hallucination_flag: bool = False
        self.meditation_step: int = 0
        self.follow_up_suggestions: list[str] = []
        self.node_timings: dict = {}


class ChatChunk:
    """Single chunk from a streaming response."""

    def __init__(self, text: str = "", is_final: bool = False, citations: Optional[list[str]] = None):
        self.text = text
        self.is_final = is_final
        self.citations = citations or []


class ChatEngine:
    """Unified chat processing engine — deep-module facade.

    Hides:
      * Request validation + length cap
      * Intent classification / graph routing (delegated to pipeline)
      * Request coalescing (dedup of concurrent identical requests)
      * Response generation — batch or streaming
      * Telemetry logging (fire-and-forget)
      * Error handling and timeouts

    Delegates to the EXISTING ``PipelineCoordinator.execute`` for batch
    and streaming execution; ``ChatStreamRequestOrchestrator`` is used
    only as the host object that already wires a ``PipelineCoordinator``
    with the streaming queue contract.
    """

    # === Public API ===

    async def chat(self, message: str, user_id: str) -> str:
        """Simplest API — message + user_id, returns response text."""
        result = await self.chat_advanced(
            ChatRequest(user_message=message, messages=[]),
            user={"id": user_id, "tenant_id": "default"},
        )
        return result.final_answer

    async def chat_stream(self, message: str, user_id: str) -> AsyncIterator[ChatChunk]:
        """Simple streaming API — yields ChatChunk objects."""
        async for chunk in self._execute_stream(
            message=message,
            user={"id": user_id, "tenant_id": "default"},
            chat_request=ChatRequest(user_message=message, messages=[]),
        ):
            yield chunk

    async def chat_advanced(
        self,
        chat_request: ChatRequest,
        user: dict,
        is_benchmark: bool = False,
    ) -> ChatResult:
        """Full-control batch API."""
        return await self._execute_batch(chat_request, user, is_benchmark)

    async def chat_advanced_stream(
        self,
        chat_request: ChatRequest,
        user: dict,
    ) -> AsyncIterator[ChatChunk]:
        """Full-control streaming API."""
        async for chunk in self._execute_stream(
            message=chat_request.user_message,
            user=user,
            chat_request=chat_request,
        ):
            yield chunk

    # === Internal Implementation (hidden) ===

    def __init__(self, container: ServiceContainer) -> None:
        self._container = container
        self._coordinator: Any = None
        self._stream_coordinator: Any = None

    def _get_coordinator(self):
        """Lazy init of PipelineCoordinator (batch path)."""
        if self._coordinator is None:
            from app.pipeline import PipelineCoordinator
            self._coordinator = PipelineCoordinator(self._container)
        return self._coordinator

    def _get_stream_coordinator(self):
        """Lazy init of ChatStreamRequestOrchestrator (streaming host)."""
        if self._stream_coordinator is None:
            from app.stream_orchestrator import ChatStreamRequestOrchestrator
            self._stream_coordinator = ChatStreamRequestOrchestrator(self._container)
        return self._stream_coordinator

    def _validate(self, message: str) -> None:
        if not message or not message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        if len(message) > settings.max_input_length:
            raise HTTPException(
                status_code=400,
                detail=f"Message too long. Max {settings.max_input_length} characters.",
            )

    def _build_coalesce_key(
        self,
        message: str,
        user_id: str,
        session_id: str,
        assistant_slug: Optional[str],
        language: str,
    ) -> str:
        assistant_tag = assistant_slug or "default"
        msg_digest = hashlib.sha256(message.encode("utf-8")).hexdigest()[:16]
        return f"rag:v3:{language}:{assistant_tag}:{user_id}:{session_id}:{msg_digest}"

    async def _execute_batch(
        self,
        chat_request: ChatRequest,
        user: dict,
        is_benchmark: bool,
    ) -> ChatResult:
        start_time = time.time()
        message = chat_request.user_message.strip()
        user_id = user.get("id", "anonymous") if user else "anonymous"
        session_id = normalize_session_id(chat_request.session_id, user_id)
        assistant_slug = chat_request.assistant.slug if chat_request.assistant else None
        language = chat_request.language or "en"

        self._validate(message)

        coalesce_key = self._build_coalesce_key(
            message, user_id, session_id, assistant_slug, language
        )

        from app.coalescer import build_coalescer
        coalescer = build_coalescer(
            redis_url=getattr(settings, "redis_url", None), ttl=60.0
        )

        async def _run():
            coordinator = self._get_coordinator()
            return await coordinator.execute(
                user_msg=message,
                preferred_lang=language,
                chat_body=chat_request,
                meditation_step=chat_request.meditation_step,
                session_id=chat_request.session_id,
                user=user,
                is_benchmark=is_benchmark,
            )

        try:
            pipeline_result = await coalescer.get_or_run(coalesce_key, _run)
        except asyncio.TimeoutError:
            logger.error(f"Pipeline timeout for user {user_id}")
            raise HTTPException(
                status_code=504,
                detail="The Guru took too long to respond. Please try again.",
            )

        result = ChatResult()
        result.final_answer = pipeline_result.final_answer
        result.intent = pipeline_result.intent
        result.meditation_step = pipeline_result.meditation_step
        result.citations = self._coerce_citations(pipeline_result.citations)
        result.blocked = pipeline_result.blocked
        result.block_reason = pipeline_result.block_reason or ""
        result.trace_id = pipeline_result.trace_id
        result.latency_ms = pipeline_result.latency_ms or int((time.time() - start_time) * 1000)
        result.model_used = pipeline_result.model_used or ""
        result.model_provider = pipeline_result.model_provider or ""
        result.route_decision = pipeline_result.route_decision
        result.query_tier = pipeline_result.query_tier or ""
        result.cache_hit = pipeline_result.cache_hit
        result.proactive_serene_mind = pipeline_result.proactive_serene_mind
        result.faithfulness_score = pipeline_result.faithfulness_score
        result.hallucination_flag = pipeline_result.hallucination_flag
        result.follow_up_suggestions = list(pipeline_result.follow_up_suggestions or [])
        result.node_timings = dict(pipeline_result.node_timings or {})

        asyncio.create_task(self._log_telemetry(result, user_id, session_id, message))

        return result

    async def _execute_stream(
        self,
        message: str,
        user: dict,
        chat_request: ChatRequest,
    ) -> AsyncIterator[ChatChunk]:
        self._validate(message)

        user_id = user.get("id", "anonymous") if user else "anonymous"
        # normalize for logging/telemetry parity (not strictly required by execute)
        _ = normalize_session_id(chat_request.session_id, user_id)
        language = chat_request.language or "en"

        stream_coordinator = self._get_stream_coordinator()
        stream_queue: asyncio.Queue = asyncio.Queue()

        pipeline_task = asyncio.create_task(
            stream_coordinator.coordinator.execute(
                user_msg=message,
                preferred_lang=language,
                chat_body=chat_request,
                meditation_step=chat_request.meditation_step,
                session_id=chat_request.session_id,
                user=user,
                is_benchmark=False,
                stream_queue=stream_queue,
            )
        )

        try:
            while True:
                if pipeline_task.done() and stream_queue.empty():
                    break
                try:
                    item = await asyncio.wait_for(stream_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if pipeline_task.done():
                        break
                    continue
                if isinstance(item, dict):
                    yield ChatChunk(
                        text=item.get("text", "") or item.get("data", "") or "",
                        is_final=item.get("is_final", False),
                    )
                else:
                    yield ChatChunk(text=str(item))
        finally:
            if not pipeline_task.done():
                pipeline_task.cancel()
                try:
                    await pipeline_task
                except (asyncio.CancelledError, Exception):
                    pass

    async def _log_telemetry(
        self,
        result: ChatResult,
        user_id: str,
        session_id: str,
        user_msg: str,
    ) -> None:
        try:
            from app.telemetry_sink import SupabaseTelemetrySink
            sink = SupabaseTelemetrySink()
            await sink.log_query_trace(
                query_id=result.trace_id,
                session_id=session_id,
                user_id=user_id,
                query_text=user_msg,
                model=result.model_used or "unknown",
                latency_ms=result.latency_ms,
                status="ok",
                created_at=result.created_at if hasattr(result, 'created_at') else datetime.now(timezone.utc).isoformat(),
                response_text=result.final_answer,
                citations=result.citations,
                faithfulness=result.faithfulness_score,
            )
        except Exception as e:
            logger.warning(f"Telemetry logging failed (non-critical): {e}")

    @staticmethod
    def _coerce_citations(citations: Any) -> list[str]:
        if not citations:
            return []
        out: list[str] = []
        for c in citations:
            if isinstance(c, str):
                out.append(c)
            elif isinstance(c, dict):
                doc_id = c.get("doc_id") or c.get("source") or c.get("source_url")
                if doc_id and doc_id != "unknown":
                    out.append(str(doc_id))
                else:
                    quote = c.get("quote") or c.get("title") or ""
                    if quote:
                        out.append(str(quote)[:200])
            else:
                out.append(str(c))
        return out


if __name__ == "__main__":
    import asyncio
    import inspect
    from unittest.mock import MagicMock

    async def _self_check() -> None:
        dummy_container = MagicMock(spec=ServiceContainer)
        engine = ChatEngine(dummy_container)

        public = ["chat", "chat_stream", "chat_advanced", "chat_advanced_stream"]
        print("public methods:", ", ".join(public))

        assert hasattr(engine, "chat") and inspect.iscoroutinefunction(
            engine.chat
        ), "chat must be coroutine"
        assert hasattr(engine, "chat_advanced") and inspect.iscoroutinefunction(
            engine.chat_advanced
        ), "chat_advanced must be coroutine"
        assert inspect.isasyncgenfunction(
            engine.chat_stream
        ), "chat_stream must be async generator"
        assert inspect.isasyncgenfunction(
            engine.chat_advanced_stream
        ), "chat_advanced_stream must be async generator"

        print("C3 OK")

    asyncio.run(_self_check())