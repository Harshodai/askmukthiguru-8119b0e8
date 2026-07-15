"""Boundary tests for the ChatEngine deep-module facade (C3).

Treats ChatEngine as a black box: only the public surface
(chat / chat_stream / chat_advanced / chat_advanced_stream) is exercised.
PipelineCoordinator and ChatStreamRequestOrchestrator are mocked at the
seam so these tests run without Docker, Supabase, Redis, or Ollama.

Per the deep-module-refactor RFC, row 1 of the Testing Strategy table.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.chat_engine import ChatChunk, ChatEngine, ChatResult
from app.config import settings
from app.pipeline.result import PipelineResult
from app.schemas import ChatRequest


# ---------------------------------------------------------------------------
# Shared seams
# ---------------------------------------------------------------------------


class _DirectCoalescer:
    """In-process coalescer that just runs the callback — no Redis."""

    async def get_or_run(self, key, callback):
        return await callback()


def _make_pipeline_result(final_answer: str = "Mocked answer") -> PipelineResult:
    return PipelineResult(
        final_answer=final_answer,
        intent="QUERY",
        trace_id="trace-mock",
        latency_ms=42,
        model_used="mock-model",
        model_provider="mock",
        route_decision="standard",
        query_tier="standard",
        cache_hit=False,
        faithfulness_score=0.9,
    )


def _new_engine() -> ChatEngine:
    container = MagicMock()
    return ChatEngine(container)


def _basic_request(message: str) -> ChatRequest:
    return ChatRequest(user_message=message, messages=[])


# ---------------------------------------------------------------------------
# 1. Batch path — ChatEngine.chat_advanced delegates to PipelineCoordinator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_engine_process_batch():
    """chat_advanced returns a ChatResult populated from the mocked coordinator."""
    engine = _new_engine()

    mock_coord = MagicMock()
    mock_coord.execute = AsyncMock(return_value=_make_pipeline_result("Batch hello"))
    engine._coordinator = mock_coord  # bypass lazy import

    with patch("app.coalescer.build_coalescer", return_value=_DirectCoalescer()):
        result = await engine.chat_advanced(
            _basic_request("What is the Beautiful State?"),
            user={"id": "u1", "tenant_id": "default"},
        )

    assert isinstance(result, ChatResult)
    assert result.final_answer == "Batch hello"
    assert result.trace_id == "trace-mock"
    assert result.model_used == "mock-model"
    mock_coord.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# 2. Stream path — chat_advanced_stream yields ChatChunk objects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_engine_process_stream():
    """chat_advanced_stream yields ChatChunk objects from the stream queue."""
    engine = _new_engine()

    async def _fake_execute(*, stream_queue, **_kw):
        await stream_queue.put({"text": "Hello ", "is_final": False})
        await stream_queue.put({"text": "world", "is_final": True})
        return _make_pipeline_result("Hello world")

    mock_stream_host = MagicMock()
    mock_stream_host.coordinator.execute = _fake_execute
    engine._stream_coordinator = mock_stream_host  # bypass lazy import

    chunks: list[ChatChunk] = []
    async for chunk in engine.chat_advanced_stream(
        _basic_request("Stream me a response"), user={"id": "u2"}
    ):
        chunks.append(chunk)

    assert len(chunks) >= 2, "stream must yield at least the two pushed chunks"
    assert all(isinstance(c, ChatChunk) for c in chunks)
    assert chunks[-1].is_final is True
    assert "Hello" in chunks[0].text


# ---------------------------------------------------------------------------
# 3. Empty message — HTTPException 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_engine_error_handling_empty_message():
    """An empty (whitespace-only) message raises HTTPException 400.

    Note: a literal empty string "" is rejected earlier by the ChatRequest
    Pydantic schema (min_length=1) and raises ValidationError, not HTTPException.
    The facade-level validation surface is exercised here with whitespace,
    which bypasses the schema and reaches ChatEngine._validate.
    """
    engine = _new_engine()

    with pytest.raises(HTTPException) as exc_info:
        await engine.chat("   ", user_id="u3")

    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 4. Oversized message — HTTPException 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_engine_error_handling_oversized_message():
    """A message exceeding settings.max_input_length raises HTTPException 400."""
    engine = _new_engine()

    too_long = "a" * (settings.max_input_length + 1)
    # Keep it within the schema's hard cap (10000) so it reaches _validate.
    assert len(too_long) <= 10000

    with pytest.raises(HTTPException) as exc_info:
        await engine.chat(too_long, user_id="u4")

    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 5. Telemetry — fire-and-forget _log_telemetry is scheduled after success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_engine_telemetry_fired():
    """After a successful batch chat, _log_telemetry is scheduled (fire-and-forget)."""
    engine = _new_engine()

    mock_coord = MagicMock()
    mock_coord.execute = AsyncMock(return_value=_make_pipeline_result("Telemetry check"))
    engine._coordinator = mock_coord

    telemetry_mock = AsyncMock()
    with patch("app.coalescer.build_coalescer", return_value=_DirectCoalescer()), \
         patch.object(ChatEngine, "_log_telemetry", telemetry_mock):
        await engine.chat_advanced(
            _basic_request("Did you log this?"), user={"id": "u5"}
        )
        # Let the fire-and-forget create_task run.
        for _ in range(10):
            await asyncio.sleep(0)

    telemetry_mock.assert_awaited_once()
    # First positional arg is the ChatResult; ensure it carries the answer.
    args, _ = telemetry_mock.call_args
    assert args[0].final_answer == "Telemetry check"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "--tb=short"]))