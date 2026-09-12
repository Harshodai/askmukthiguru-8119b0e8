"""Token usage must reach a metric, or per-query cost is unmeasurable.

`guru_llm_tokens_total` existed in app/metrics.py but no provider ever
incremented it, which is why the audit's cost-per-query section could not be
answered from telemetry. The counter is incremented where the provider's own
usage numbers arrive.
"""

import inspect

from app.metrics import LLM_TOKENS
from services import openrouter_service


def _count(model: str) -> float:
    return LLM_TOKENS.labels(model=model)._value.get()


def test_counter_accepts_model_label():
    before = _count("test/model")
    LLM_TOKENS.labels(model="test/model").inc(42)
    assert _count("test/model") == before + 42


def test_openrouter_increments_token_counter():
    src = inspect.getsource(openrouter_service.OpenRouterService._track_token_usage)
    assert "LLM_TOKENS.labels(model=model).inc(" in src
    assert "tokens_in" in src and "tokens_out" in src


def test_negative_usage_cannot_decrement_a_counter():
    """Prometheus counters raise on a negative increment."""
    src = inspect.getsource(openrouter_service.OpenRouterService._track_token_usage)
    assert "max(0, tokens_in)" in src and "max(0, tokens_out)" in src
