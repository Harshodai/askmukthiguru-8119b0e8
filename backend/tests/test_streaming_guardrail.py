"""Tests for P1-AI-8 streaming safety filter in stream_orchestrator.py."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

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
