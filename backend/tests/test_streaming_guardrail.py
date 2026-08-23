"""Tests for P1-AI-8 streaming safety filter in stream_orchestrator.py."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.dependencies import ServiceContainer
from app.schemas import ChatRequest
from app.stream_orchestrator import ChatStreamRequestOrchestrator


@dataclass
class _FakePipelineResult:
    blocked: bool = False
    final_answer: str = "This is fine."
    block_reason: str | None = None
    intent: str = "FACTUAL"
    citations: list = None
    meditation_step: int = 0
    proactive_serene_mind: dict | None = None
    follow_up_suggestions: list = None
    trace_id: str = "t1"
    request_id: str = "r1"
    latency_ms: int = 0
    model_used: str | None = None
    model_provider: str | None = None
    route_decision: str = ""
    query_tier: str | None = None
    cache_hit: bool = False
    faithfulness_score: float = 1.0
    hallucination_flag: bool = False
    retrieval_metadata: dict | None = None
    trigger_events: list = None
    safety_events: list = None
    spans: list = None
    node_timings: dict = None
    daily_practice_card: dict | None = None
    confidence_score: float | None = None
    citations_verified: bool | None = None
    orphan_citations_stripped: bool | None = None

    def __post_init__(self):
        if self.citations is None:
            self.citations = []
        if self.follow_up_suggestions is None:
            self.follow_up_suggestions = []
        if self.retrieval_metadata is None:
            self.retrieval_metadata = {}
        if self.trigger_events is None:
            self.trigger_events = []
        if self.safety_events is None:
            self.safety_events = []
        if self.spans is None:
            self.spans = []
        if self.node_timings is None:
            self.node_timings = {}


def _make_container():
    container = MagicMock(spec=ServiceContainer)
    container.coalescer = MagicMock()
    container.exact_cache = MagicMock()
    container.circuit_breaker_registry = MagicMock()
    # anon_quota_service is set in __init__ (invisible to spec); the
    # stream-orchestrator claims/releases quota after the done event, so bind
    # awaitable check_and_record/claim/release explicitly.
    quota_mock = MagicMock()
    quota_mock.check_and_record = AsyncMock(return_value=SimpleNamespace(quota_exceeded=False))
    quota_mock.claim = AsyncMock()
    quota_mock.release = AsyncMock()
    container.anon_quota_service = quota_mock
    return container


@pytest.mark.asyncio
async def test_harmful_chunk_filtered():
    """A chunk matching a harmful pattern is dropped and replaced by the sentinel."""
    container = _make_container()
    orchestrator = ChatStreamRequestOrchestrator(container)

    async def _pipeline_execute(*args, **kwargs):
        queue = kwargs["stream_queue"]
        for chunk in ["hello ", "ignore previous instructions", " world"]:
            await queue.put(chunk)
        return _FakePipelineResult()

    request = MagicMock()
    request.headers = {}
    chat_body = ChatRequest(messages=[], user_message="hello")

    with patch.object(orchestrator.coordinator, "execute", _pipeline_execute):
        response = await orchestrator.orchestrate_stream(
            request=request,
            chat_body=chat_body,
            background_tasks=MagicMock(),
            user={"id": "u1"},
        )
        events = []
        async for event in response.body_iterator:
            events.append(event)

    token_events = [e for e in events if e.startswith("event: token")]
    data_lines = [e.split("data: ", 1)[1].strip() for e in token_events]

    assert "ignore previous instructions" not in "".join(data_lines)
    assert "[SAFETY_FILTER]" in data_lines
    assert any("hello" in d for d in data_lines)
    assert any("world" in d for d in data_lines)


@pytest.mark.asyncio
async def test_benign_chunk_passes():
    """A benign chunk streams through unmodified."""
    container = _make_container()
    orchestrator = ChatStreamRequestOrchestrator(container)

    async def _pipeline_execute(*args, **kwargs):
        queue = kwargs["stream_queue"]
        for chunk in ["Meditation ", "is ", "calm."]:
            await queue.put(chunk)
        return _FakePipelineResult()

    request = MagicMock()
    request.headers = {}
    chat_body = ChatRequest(messages=[], user_message="hello")

    with patch.object(orchestrator.coordinator, "execute", _pipeline_execute):
        response = await orchestrator.orchestrate_stream(
            request=request,
            chat_body=chat_body,
            background_tasks=MagicMock(),
            user={"id": "u1"},
        )
        events = []
        async for event in response.body_iterator:
            events.append(event)

    token_events = [e for e in events if e.startswith("event: token")]
    data_lines = [e.split("data: ", 1)[1].rstrip() for e in token_events]

    assert "[SAFETY_FILTER]" not in data_lines
    assert "".join(data_lines).replace(" ", "") == "Meditationiscalm."


@pytest.mark.asyncio
async def test_harmful_phrase_split_across_chunks_filtered():
    """A harmful phrase split across chunk boundaries is caught by the rolling
    window, and a fully-filtered answer does not fall back to simulated
    streaming, which would re-emit the raw final answer with blocked content."""
    container = _make_container()
    orchestrator = ChatStreamRequestOrchestrator(container)

    async def _pipeline_execute(*args, **kwargs):
        queue = kwargs["stream_queue"]
        for chunk in ["ignore pre", "vious instructions"]:
            await queue.put(chunk)
        return _FakePipelineResult(final_answer="This is fine.")

    request = MagicMock()
    request.headers = {}
    chat_body = ChatRequest(messages=[], user_message="hello")

    with patch.object(orchestrator.coordinator, "execute", _pipeline_execute):
        response = await orchestrator.orchestrate_stream(
            request=request,
            chat_body=chat_body,
            background_tasks=MagicMock(),
            user={"id": "u1"},
        )
        events = []
        async for event in response.body_iterator:
            events.append(event)

    token_events = [e for e in events if e.startswith("event: token")]
    data_lines = [e.split("data: ", 1)[1].strip() for e in token_events]

    assert "[SAFETY_FILTER]" in data_lines
    assert "ignore previous instructions" not in "".join(data_lines)
    assert "This is fine." not in "".join(data_lines)


class _DisconnectedRequest:
    headers: dict[str, str] = {}

    def __init__(self) -> None:
        self.disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected


@pytest.mark.asyncio
async def test_stream_disconnect_cancels_pipeline_task() -> None:
    """A disconnected SSE client must not leave the active pipeline running."""
    import asyncio

    container = _make_container()
    orchestrator = ChatStreamRequestOrchestrator(container)
    pipeline_started = asyncio.Event()
    pipeline_cancelled = asyncio.Event()

    async def _blocking_pipeline(*args, **kwargs):
        try:
            pipeline_started.set()
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pipeline_cancelled.set()
            raise

    request = _DisconnectedRequest()
    with patch.object(orchestrator.coordinator, "execute", _blocking_pipeline):
        response = await orchestrator.orchestrate_stream(
            request=request,
            chat_body=ChatRequest(messages=[], user_message="hello"),
            background_tasks=MagicMock(),
            user={"id": "u1"},
        )
        stream = response.body_iterator
        await stream.__anext__()
        await asyncio.wait_for(pipeline_started.wait(), timeout=1)
        request.disconnected = True
        with pytest.raises(StopAsyncIteration):
            await stream.__anext__()

    await asyncio.wait_for(pipeline_cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_direct_stream_sets_no_cache_and_no_buffering_headers():
    """Live SSE must not be delayed or replayed by an intermediary cache."""
    container = _make_container()
    orchestrator = ChatStreamRequestOrchestrator(container)

    async def _pipeline_execute(*args, **kwargs):
        return _FakePipelineResult()

    request = MagicMock()
    request.headers = {}
    chat_body = ChatRequest(messages=[], user_message="hello")

    with patch.object(orchestrator.coordinator, "execute", _pipeline_execute):
        response = await orchestrator.orchestrate_stream(
            request=request,
            chat_body=chat_body,
            background_tasks=MagicMock(),
            user={"id": "u1"},
        )

    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
