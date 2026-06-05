"""
Unit 15 — Distributed Tracing: RAG Node Span Decorators

Provides lightweight OTEL span utilities for individual LangGraph RAG nodes.
These are additive — if OTEL is not installed, all decorators are no-ops.

Design:
  - ``rag_span()``: async context manager that creates a named OTEL span
  - ``trace_rag_node()``: decorator for async RAG node functions
  - Span attributes follow OpenTelemetry semantic conventions where applicable

Usage in nodes.py::

    from app.tracing import trace_rag_node, rag_span

    @trace_rag_node("retrieve")
    async def retrieve(state: GraphState) -> dict:
        ...

    # Or inline:
    async with rag_span("embed_query", query=state["query"]) as span:
        ...
"""

from __future__ import annotations

import contextlib
import functools
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _get_tracer():
    """Return the active OTEL tracer, or a no-op sentinel if not available."""
    try:
        from opentelemetry import trace
        return trace.get_tracer("mukthiguru.rag")
    except ImportError:
        return None


@contextlib.asynccontextmanager
async def rag_span(
    name: str,
    *,
    tenant_id: Optional[str] = None,
    model: Optional[str] = None,
    **extra_attrs: Any,
):
    """Async context manager: create a named OTEL span for a RAG operation.

    Gracefully degrades to a no-op if OpenTelemetry is not installed or
    the tracer provider is not configured.

    Args:
        name: Span name, e.g. "rag.retrieve", "rag.generate".
        tenant_id: If provided, set as ``rag.tenant_id`` attribute.
        model: If provided, set as ``llm.model`` attribute.
        **extra_attrs: Additional span attributes (values must be str/int/float/bool).

    Usage::

        async with rag_span("rag.retrieve", tenant_id="acme", limit=10) as span:
            results = qdrant.search(...)
            if span:
                span.set_attribute("rag.results_count", len(results))
    """
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return

    try:
        from opentelemetry import trace
        with tracer.start_as_current_span(name) as span:
            try:
                if tenant_id:
                    span.set_attribute("rag.tenant_id", tenant_id)
                if model:
                    span.set_attribute("llm.model", model)
                for k, v in extra_attrs.items():
                    if isinstance(v, (str, int, float, bool)):
                        span.set_attribute(f"rag.{k}", v)
                yield span
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                raise
    except Exception as exc:
        # Span creation itself failed — don't break the RAG pipeline
        logger.debug(f"tracing: span creation for '{name}' failed: {exc}")
        yield None


def trace_rag_node(node_name: str):
    """Decorator: wrap an async RAG node function in an OTEL span.

    Automatically sets:
      - ``rag.node``: the node_name
      - ``rag.state_keys``: comma-separated keys in the state dict
      - Sets span status to ERROR on uncaught exception

    Usage::

        @trace_rag_node("retrieve")
        async def retrieve(state: GraphState) -> dict:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract state from the first positional argument (LangGraph convention)
            state = args[0] if args else {}
            state_keys = ",".join(sorted(state.keys())) if isinstance(state, dict) else ""

            tracer = _get_tracer()
            if tracer is None:
                return await func(*args, **kwargs)

            try:
                from opentelemetry import trace
                with tracer.start_as_current_span(f"rag.{node_name}") as span:
                    span.set_attribute("rag.node", node_name)
                    if state_keys:
                        span.set_attribute("rag.state_keys", state_keys[:200])
                    try:
                        result = await func(*args, **kwargs)
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(trace.StatusCode.ERROR, str(exc))
                        raise
            except Exception as exc:
                if "span" not in str(exc):  # Re-raise non-span errors
                    raise
                # Span setup failed — run the node without tracing
                logger.debug(f"tracing: span setup for node '{node_name}' failed: {exc}")
                return await func(*args, **kwargs)

        return wrapper
    return decorator
