"""
LLM call tracing — OpenTelemetry GenAI semantic-convention spans.

Why this exists: `app/observability.py` installs `LangChainInstrumentor()`, which
emits GenAI spans with prompts/completions -- but every real LLM call in this
codebase goes through raw `httpx` in `OpenRouterService`/`SarvamCloudService`,
never through LangChain. So the instrumentation that would capture prompt and
completion text runs against a code path we don't use, and the actual calls are
invisible to Jaeger. This module closes that gap at the service layer, where
model/tokens/cost/finish_reason are already computed.

Spans follow https://opentelemetry.io/docs/specs/semconv/gen-ai/ so that a
Langfuse OTLP/HTTP exporter (design phase 2, see
docs/architecture/llm-observability-design.md) parses them natively with zero
re-instrumentation.

FAIL-OPEN BY CONSTRUCTION: every entry point swallows its own errors and yields
None. Observability must never take down inference -- a broken tracer should
cost visibility, not availability.

Content capture (prompt/completion text) is OFF by default: seeker questions are
personal. Enable deliberately with LLM_TRACE_CONTENT=true.
"""

from __future__ import annotations

import functools
import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

_CONTENT_DISABLED_VALUES = {"0", "false", "no", "off", ""}
_DEFAULT_CONTENT_MAX_CHARS = 2000


def _content_enabled() -> bool:
    """Prompt/completion capture is opt-in — personal content, not a default."""
    return os.getenv("LLM_TRACE_CONTENT", "false").strip().lower() not in _CONTENT_DISABLED_VALUES


def _content_max_chars() -> int:
    raw = os.getenv("LLM_TRACE_CONTENT_MAX_CHARS", str(_DEFAULT_CONTENT_MAX_CHARS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_CONTENT_MAX_CHARS
    # A non-positive cap would mean "capture nothing" via a confusing route;
    # _content_enabled() is the switch for that.
    return value if value > 0 else _DEFAULT_CONTENT_MAX_CHARS


def _truncate(text: str) -> str:
    limit = _content_max_chars()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…[truncated {len(text) - limit} chars]"


def _flatten_prompt(prompt: Any) -> str:
    """Render a prompt (str, or OpenAI-style message list) as plain text."""
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, (list, tuple)):
        parts = []
        for msg in prompt:
            if isinstance(msg, dict):
                role = str(msg.get("role", "?"))
                content = msg.get("content", "")
                parts.append(f"{role}: {content}")
            else:
                parts.append(str(msg))
        return "\n".join(parts)
    return str(prompt)


@contextmanager
def llm_span(
    *,
    operation: str,
    model: str,
    provider: str,
    prompt: Any = None,
) -> Iterator[Optional[Any]]:
    """
    Open a GenAI span around one LLM call.

    Yields the span, or None when tracing is unavailable/disabled — callers must
    tolerate None (that is the fail-open contract, not an edge case).
    """
    try:
        from opentelemetry import trace
    except ImportError:
        yield None
        return

    try:
        tracer = trace.get_tracer("mukthiguru.llm")
        # GenAI convention: "{operation} {model}" (e.g. "chat gemini-2.5-flash").
        with tracer.start_as_current_span(f"{operation} {model}") as span:
            try:
                span.set_attribute("gen_ai.system", provider)
                span.set_attribute("gen_ai.request.model", model)
                span.set_attribute("gen_ai.operation.name", operation)
                if prompt is not None and _content_enabled():
                    span.set_attribute("gen_ai.prompt", _truncate(_flatten_prompt(prompt)))
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("llm_span attribute set failed: %s", exc)
            yield span
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("llm_span unavailable, continuing untraced: %s", exc)
        yield None


def record_llm_result(
    span: Optional[Any],
    *,
    prompt: Any = None,
    completion: Any = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    cached_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
    finish_reason: Optional[str] = None,
    response_model: Optional[str] = None,
) -> None:
    """Attach LLM call results to a span. No-op when span is None."""
    if span is None:
        return
    try:
        if tokens_in is not None:
            span.set_attribute("gen_ai.usage.input_tokens", int(tokens_in))
        if tokens_out is not None:
            span.set_attribute("gen_ai.usage.output_tokens", int(tokens_out))
        if cached_tokens is not None:
            span.set_attribute("gen_ai.usage.cached_input_tokens", int(cached_tokens))
        if cost_usd is not None:
            # Not a GenAI-convention key; Langfuse reads this one for cost rollup.
            span.set_attribute("gen_ai.usage.cost", float(cost_usd))
        if finish_reason is not None:
            span.set_attribute("gen_ai.response.finish_reasons", [str(finish_reason)])
        if response_model is not None:
            span.set_attribute("gen_ai.response.model", str(response_model))
        if _content_enabled():
            if prompt is not None:
                span.set_attribute("gen_ai.prompt", _truncate(_flatten_prompt(prompt)))
            if completion is not None:
                span.set_attribute("gen_ai.completion", _truncate(str(completion)))
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("record_llm_result failed: %s", exc)


def current_llm_span() -> Optional[Any]:
    """
    The span opened by `traced_llm_call`, or None.

    Exists so an instrumented function can attach results without threading a
    span object through its own body — the model/token/cost values are computed
    deep inside `_call_api`, far from where the span is opened, and re-indenting
    a ~130-line method under a `with` block to pass them down would be a large
    diff for no behavioural gain. OTel keeps the active span in a contextvar,
    so this reads it back at the point the values exist.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        # An unset/no-op span has an all-zero span id; treat it as absent so
        # callers get the same None contract as when tracing is off entirely.
        if span is None or not span.get_span_context().span_id:
            return None
        return span
    except Exception:  # pragma: no cover - defensive
        return None


def set_llm_request(span: Optional[Any], *, model: str, operation: str) -> None:
    """
    Record request attributes once they are resolved.

    `traced_llm_call` cannot set these itself: the model is chosen inside the
    decorated function (registry lookup, per-operation routing), not passed in.
    """
    if span is None:
        return
    try:
        span.set_attribute("gen_ai.request.model", str(model))
        span.set_attribute("gen_ai.operation.name", str(operation))
        span.update_name(f"{operation} {model}")
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("set_llm_request failed: %s", exc)


def traced_llm_call(provider: str):
    """
    Decorator opening a GenAI span around one async LLM call.

    Pairs with `current_llm_span()` + `set_llm_request()` + `record_llm_result()`
    inside the decorated body. Fail-open: any tracing error leaves the wrapped
    call untouched.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                from opentelemetry import trace

                tracer = trace.get_tracer("mukthiguru.llm")
            except Exception:  # pragma: no cover - defensive
                return await func(*args, **kwargs)

            try:
                cm = tracer.start_as_current_span(f"llm {provider}")
            except Exception:  # pragma: no cover - defensive
                return await func(*args, **kwargs)

            with cm as span:
                try:
                    span.set_attribute("gen_ai.system", provider)
                except Exception:  # pragma: no cover - defensive
                    pass
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def record_llm_error(span: Optional[Any], exc: BaseException) -> None:
    """Mark a span as failed. No-op when span is None."""
    if span is None:
        return
    try:
        from opentelemetry.trace import Status, StatusCode

        span.set_attribute("error.type", type(exc).__name__)
        span.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
    except Exception as inner:  # pragma: no cover - defensive
        logger.debug("record_llm_error failed: %s", inner)


if __name__ == "__main__":
    # Self-check: the fail-open contract holds with no OTel provider configured,
    # and content capture respects its env switch.
    os.environ["LLM_TRACE_CONTENT"] = "true"
    assert _content_enabled() is True
    os.environ["LLM_TRACE_CONTENT"] = "false"
    assert _content_enabled() is False

    os.environ["LLM_TRACE_CONTENT"] = "true"
    os.environ["LLM_TRACE_CONTENT_MAX_CHARS"] = "10"
    assert _truncate("x" * 50).startswith("x" * 10)
    assert "truncated" in _truncate("x" * 50)
    assert _truncate("short") == "short"

    flat = _flatten_prompt([{"role": "user", "content": "hi"}, {"role": "system", "content": "be kind"}])
    assert flat == "user: hi\nsystem: be kind", flat
    assert _flatten_prompt("plain") == "plain"

    # Fail-open: must yield (possibly None) and never raise, then no-op cleanly.
    with llm_span(operation="chat", model="m", provider="p", prompt="hello") as span:
        record_llm_result(span, completion="hi", tokens_in=1, tokens_out=2, cost_usd=0.01)
    record_llm_result(None, completion="ignored")
    record_llm_error(None, ValueError("ignored"))
    set_llm_request(None, model="m", operation="chat")

    # Decorator must be transparent: return value preserved, exceptions still
    # propagate, and it must work with no OTel provider configured.
    import asyncio

    @traced_llm_call("openrouter")
    async def _ok(x):
        set_llm_request(current_llm_span(), model="m", operation="chat")
        record_llm_result(current_llm_span(), completion="c", tokens_in=1)
        return x * 2

    @traced_llm_call("openrouter")
    async def _boom():
        record_llm_error(current_llm_span(), RuntimeError("x"))
        raise RuntimeError("propagated")

    assert asyncio.run(_ok(21)) == 42
    try:
        asyncio.run(_boom())
        raise AssertionError("exception should have propagated")
    except RuntimeError as exc:
        assert str(exc) == "propagated", exc

    print("llm_tracing self-check OK")
