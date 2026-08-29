"""
Unit and regression tests for RAG tracing exception safety.

Verifies:
1. Exceptions raised by functions decorated with @trace_rag_node are never
   swallowed, retried, or re-executed, even when exception strings contain
   substrings like "span".
2. Async context manager rag_span follows proper context manager protocol,
   recording exceptions to the active span and re-raising them cleanly without
   causing `RuntimeError("generator didn't stop after athrow()")`.
3. Tracing setup failures gracefully degrade to running functions once without tracing.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app import tracing
from app.tracing import rag_span, trace_rag_node


class CustomSpanError(Exception):
    """Custom domain exception whose name and message contain 'span'."""


class InvalidSpanLengthError(ValueError):
    """Custom ValueError simulating span validation failures."""


@pytest.mark.asyncio
async def test_trace_rag_node_propagates_span_substring_exception_without_reexecution():
    """Verify that exceptions containing 'span' propagate as exact type/message
    and the wrapped function runs exactly once (no retry/re-execution loop)."""
    call_count = 0

    @trace_rag_node("retrieve_docs")
    async def failing_node(state: dict) -> dict:
        nonlocal call_count
        call_count += 1
        raise InvalidSpanLengthError("Invalid span length in vector search")

    with pytest.raises(InvalidSpanLengthError, match="Invalid span length in vector search"):
        await failing_node({"query": "meditation"})

    assert call_count == 1


@pytest.mark.asyncio
async def test_trace_rag_node_propagates_custom_exception():
    """Verify custom exception propagation without modification."""
    call_count = 0

    @trace_rag_node("generate_node")
    async def node_with_custom_error(state: dict) -> dict:
        nonlocal call_count
        call_count += 1
        raise CustomSpanError("critical span context failure")

    with pytest.raises(CustomSpanError, match="critical span context failure"):
        await node_with_custom_error({})

    assert call_count == 1


@pytest.mark.asyncio
async def test_trace_rag_node_span_setup_failure_runs_function_once(monkeypatch):
    """If OTEL span setup fails, the function should run once untraced."""
    call_count = 0

    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.side_effect = RuntimeError("span allocation failed")
    monkeypatch.setattr(tracing, "_get_tracer", lambda: mock_tracer)

    @trace_rag_node("resilient_node")
    async def resilient_node(state: dict) -> dict:
        nonlocal call_count
        call_count += 1
        return {"status": "ok", "result": 42}

    result = await resilient_node({"key": "value"})
    assert result == {"status": "ok", "result": 42}
    assert call_count == 1


@pytest.mark.asyncio
async def test_trace_rag_node_span_setup_failure_propagates_function_error(monkeypatch):
    """If OTEL span setup fails AND the function raises an exception, the function
    must execute only once and the exception must propagate directly."""
    call_count = 0

    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.side_effect = RuntimeError("span setup error")
    monkeypatch.setattr(tracing, "_get_tracer", lambda: mock_tracer)

    @trace_rag_node("failing_resilient_node")
    async def failing_node(state: dict) -> dict:
        nonlocal call_count
        call_count += 1
        raise ValueError("Invalid span parameter in node")

    with pytest.raises(ValueError, match="Invalid span parameter in node"):
        await failing_node({})

    assert call_count == 1


@pytest.mark.asyncio
async def test_trace_rag_node_when_tracer_is_none(monkeypatch):
    """When OTEL is not available (_get_tracer returns None), function executes normally once."""
    call_count = 0
    monkeypatch.setattr(tracing, "_get_tracer", lambda: None)

    @trace_rag_node("no_tracer_node")
    async def no_tracer_node(state: dict) -> dict:
        nonlocal call_count
        call_count += 1
        if state.get("fail"):
            raise CustomSpanError("error when span tracer is none")
        return {"data": "success"}

    # Success case
    res = await no_tracer_node({"fail": False})
    assert res == {"data": "success"}
    assert call_count == 1

    # Failure case
    with pytest.raises(CustomSpanError, match="error when span tracer is none"):
        await no_tracer_node({"fail": True})
    assert call_count == 2


@pytest.mark.asyncio
async def test_rag_span_custom_exception_propagates_unchanged():
    """Verify that exceptions raised inside `async with rag_span(...)` propagate
    unchanged without triggering `RuntimeError: generator didn't stop after athrow()`."""
    with pytest.raises(CustomSpanError, match="span pipeline execution error"):
        async with rag_span("test_operation", tenant_id="test_tenant") as span:
            raise CustomSpanError("span pipeline execution error")


@pytest.mark.asyncio
async def test_rag_span_value_error_with_span_keyword():
    """Verify standard ValueError containing 'span' propagates cleanly."""
    with pytest.raises(ValueError, match="Invalid span length"):
        async with rag_span("test_span_validation", model="gpt-4o") as span:
            raise ValueError("Invalid span length")


@pytest.mark.asyncio
async def test_rag_span_when_tracer_is_none(monkeypatch):
    """When tracer is None, rag_span yields None and propagates exceptions cleanly."""
    monkeypatch.setattr(tracing, "_get_tracer", lambda: None)

    # Normal block
    async with rag_span("test_no_tracer") as span:
        assert span is None

    # Exception inside block
    with pytest.raises(KeyError, match="span_key"):
        async with rag_span("test_no_tracer") as span:
            raise KeyError("span_key")


@pytest.mark.asyncio
async def test_rag_span_when_span_creation_fails(monkeypatch):
    """When span creation raises an exception, rag_span yields None and degrades gracefully."""
    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.side_effect = RuntimeError("Span creation boom")
    monkeypatch.setattr(tracing, "_get_tracer", lambda: mock_tracer)

    # Normal block
    async with rag_span("test_creation_fail") as span:
        assert span is None

    # Exception inside block propagates
    with pytest.raises(CustomSpanError, match="error inside degraded span block"):
        async with rag_span("test_creation_fail") as span:
            raise CustomSpanError("error inside degraded span block")


@pytest.mark.asyncio
async def test_rag_span_records_exception_and_error_status(monkeypatch):
    """Verify that exceptions inside rag_span call record_exception and set_status on the span."""
    mock_span = MagicMock()
    mock_span_ctx = MagicMock()
    mock_span_ctx.__enter__.return_value = mock_span

    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value = mock_span_ctx
    monkeypatch.setattr(tracing, "_get_tracer", lambda: mock_tracer)

    exc = CustomSpanError("span database error")
    with pytest.raises(CustomSpanError):
        async with rag_span("db_query", tenant_id="tenant_1") as span:
            raise exc

    mock_span.record_exception.assert_called_once_with(exc)
    assert mock_span.set_status.called
    assert mock_span_ctx.__exit__.called


@pytest.mark.asyncio
async def test_rag_span_sets_attributes_on_success(monkeypatch):
    """Verify attributes are set on OTEL span during successful execution."""
    mock_span = MagicMock()
    mock_span_ctx = MagicMock()
    mock_span_ctx.__enter__.return_value = mock_span

    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value = mock_span_ctx
    monkeypatch.setattr(tracing, "_get_tracer", lambda: mock_tracer)

    async with rag_span("test_success", tenant_id="t1", model="m1", extra_int=100) as span:
        assert span is mock_span

    mock_span.set_attribute.assert_any_call("rag.tenant_id", "t1")
    mock_span.set_attribute.assert_any_call("llm.model", "m1")
    mock_span.set_attribute.assert_any_call("rag.extra_int", 100)
    mock_span_ctx.__exit__.assert_called_once()
