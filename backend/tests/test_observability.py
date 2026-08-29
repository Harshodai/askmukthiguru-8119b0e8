import pytest
from fastapi import FastAPI

from app import observability
from app.tracing import trace_rag_node


def test_observability_respects_disabled_env(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "false")
    monkeypatch.setattr(observability, "_INITIALIZED", False)

    assert observability.init_observability(FastAPI()) is False


def test_observability_is_idempotent(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setattr(observability, "_INITIALIZED", True)

    assert observability.init_observability(FastAPI()) is True


class _BoomError(ValueError):
    """Distinct exception type, message deliberately contains 'span'."""


def test_trace_rag_node_propagates_original_exception_once():
    """Regression for #13/#14: a real exception must propagate as its exact
    type/message, and the wrapped function must run exactly once even when
    the exception message contains the literal word 'span'."""
    call_count = 0

    @trace_rag_node("boom_node")
    async def boom(state):
        nonlocal call_count
        call_count += 1
        raise _BoomError("this span setup blew up")

    with pytest.raises(_BoomError, match="this span setup blew up"):
        import asyncio

        asyncio.run(boom({}))

    assert call_count == 1
