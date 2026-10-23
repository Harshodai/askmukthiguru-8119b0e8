"""A13 (agent half) — characterization tests for the four evidence gaps.

The row: "OpenRouter's aggregate ceiling is now per model (about the limit times
models in use; account limit unverified); `generate_stream` sends the whole answer
at the end (no early tokens); connection-pool startup check needs 51 connections,
Railway env value unverified; answerability gate on the 8B model checked on 32
trivia + 18 borderline questions only (AI-judged)".

Three of the four are verifiable without Railway or a human. The way to keep them
verifiable is a test that FAILS when the behaviour drifts — not a comment.

  1. the OpenRouter rate limiter is keyed PER MODEL, so one model's 429 cannot put
     every other model to sleep (that was the 2026-10-15/16 outage);
  2. the connection-pool startup check's "51" is DERIVED, and the validator fails
     loudly when a pool cannot cover the fan-out — so Railway's env value has one
     right shape, and changing the fan-out changes the requirement;
  3. the provider layer DOES emit incremental deltas, so the row's "no early
     tokens" claim is about a DOWNSTREAM buffer, not about `generate_stream`.

The fourth (the answerability gate over 32 + 18 AI-judged questions) needs human
labels and is deliberately NOT encoded: an AI-judged threshold test would launder
the very uncertainty the row is about.

Run: cd backend && .venv/bin/pytest tests/test_evidence_gaps_a13_2026_10_19.py -q
"""

from __future__ import annotations

import inspect

import pytest

from app.config import LLM_CALLS_PER_REQUEST, Settings, settings

# --- 1. per-model limiter key -------------------------------------------------


def test_rate_limit_key_is_per_model() -> None:
    """One model's 429 must not sleep the shared limiter for every other model.

    Live 2026-10-15: a single DeepSeek 429 made every call (fast gate, scorer)
    sleep 30-63 s and time out as 'indeterminate', because the limiter key was
    global. The key is now composed with the model id.
    """
    from services.openrouter_service import OpenRouterService

    a = OpenRouterService._rate_limit_key("deepseek/deepseek-chat")
    b = OpenRouterService._rate_limit_key("meta-llama/llama-3.1-8b-instruct")
    assert a != b, "two models share one limiter key: a 429 on one sleeps the other"
    assert "deepseek/deepseek-chat" in a, f"key {a!r} does not carry the model id"
    assert OpenRouterService._rate_limit_key(None) == OpenRouterService._RATE_LIMIT_KEY, (
        "the no-model fallback must be the bare key, not a model-suffixed one"
    )


# --- 2. pool fan-out is one derived number ------------------------------------


def test_pool_requirement_is_derived_and_enforced() -> None:
    """`need = (max_concurrent_chat + queue_concurrency) * LLM_CALLS_PER_REQUEST`.

    The row's "51 connections" is this expression with today's defaults. The
    startup validator must refuse a pool below it (fail loud, do not wedge under
    load), so Railway's env value has exactly one shape: >= this number.
    """
    queue = int(Settings.model_fields["queue_concurrency"].default)
    need = (Settings.model_fields["max_concurrent_chat"].default + queue) * LLM_CALLS_PER_REQUEST
    assert need == 51, (
        f"the derived connection fan-out is now {need}, not 51 — the A13 row and "
        "any Railway env value written from it are stale, update both"
    )
    assert settings.http_max_connections >= need
    assert settings.http_pool_max_connections >= need

    payload = settings.model_dump()
    payload["http_pool_max_connections"] = need - 1
    # Ensure the validator sees the same 'need' as the assertion above by
    # pinning the two concurrency fields to their declared defaults.  When
    # Docker overrides MAX_CONCURRENT_CHAT the env wins inside Settings(),
    # which changes the computed 'need' inside the validator and makes
    # need-1 still pass the check.
    payload["max_concurrent_chat"] = int(Settings.model_fields["max_concurrent_chat"].default)
    payload["queue_concurrency"] = int(Settings.model_fields["queue_concurrency"].default)

    with pytest.raises(Exception) as exc:  # noqa: B017 — pydantic ValidationError
        Settings(**payload)
    assert "http_pool_max_connections" in str(exc.value), (
        "an undersized pool must name the setting in the error, not fail silently"
    )


# --- 3. streaming shape -------------------------------------------------------


def test_generate_stream_has_an_incremental_path() -> None:
    """The provider layer yields deltas; the row's claim is about a later buffer."""
    from services.openrouter_service import OpenRouterService

    src = inspect.getsource(OpenRouterService.generate_stream)
    assert "aiter_lines" in src, "no line iteration: the stream cannot be incremental"
    assert '"delta"' in src or "'delta'" in src, "no OpenAI-style delta parsing"
    assert "yield " in src, "generate_stream never yields mid-answer"

    sig = inspect.signature(OpenRouterService.generate_stream)
    assert "kwargs" in sig.parameters, (
        "generate_stream must accept kwargs so the caller can pin the model"
    )
    # The resolved model must be the one handed to the limiter, otherwise the
    # per-model key is computed for a model other than the one being called.
    assert "_enforce_rate_limit(model=model)" in src, (
        "generate_stream does not pass its resolved model to _enforce_rate_limit; "
        "the per-model limiter key would be computed for the wrong model"
    )
    assert 'kwargs.get("model"' in src, (
        "the model must be resolvable from the call site, with the service default as fallback"
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
