"""P1-AI-2 tests — is_faithful=None acceptance requires citations_verified.

format_final_answer may legitimately accept an answer whose faithfulness
verdict is still pending (the verification lane skips fast-tier queries,
so `is_faithful is None` means "not yet judged", not "failed"). But a
cited-but-UNVERIFIED answer (citations_verified=False — e.g. citation
markers failed grounding, or verification was skipped with no citation
check) is now rejected instead of accepted.

Fakes only — no network, no real providers. Mirrors the state-dict style of
tests/test_audit_fixes.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.nodes import generation
from rag.nodes.generation import format_final_answer
from rag.prompts import FALLBACK_RESPONSE
from rag.states import GraphState

_LONG_ANSWER = (
    "Meditation is the practice of resting attention on the breath. "
    "When the mind settles, stillness arises on its own. This is the "
    "first teaching of the sacred wisdom tradition."
)


def _unverified_citation_check(cleaned_answer: str = "") -> AsyncMock:
    """Awaitable _verify_inline_citations stub: answer comes back with a
    failing citation verification (orphan marker stripped / grounding failed)."""
    m = AsyncMock()
    m.return_value = (cleaned_answer, False, 1)
    return m


def _state(**overrides) -> GraphState:
    base = dict(
        answer=_LONG_ANSWER,
        citations=["https://doc.example/teaching"],
        relevant_docs=[{"title": "Doc One", "source_url": "https://doc.example/teaching"}],
        is_faithful=None,
        verification={"passed": False, "method": "fast_tier_lettuce_detect"},
        confidence_score=8.0,
        intent="QUERY",
        query_tier="standard",
        retry_count=1,  # skip the retry branch — go straight to fallback on rejection
    )
    base.update(overrides)
    return GraphState(**base)


@pytest.mark.asyncio
async def test_verification_timeout_returns_fallback(monkeypatch):
    """Verification timed out (is_faithful never written) AND the citation
    check did not verify → FALLBACK_RESPONSE, not an unverified answer."""
    monkeypatch.setattr(
        generation, "_verify_inline_citations",
        _unverified_citation_check(),
    )
    state = _state(answer=_LONG_ANSWER + " [[CITE:1]]")

    result = await format_final_answer(state)

    assert result["final_answer"] == FALLBACK_RESPONSE
    assert result["_needs_retry"] is False
    assert result["verification"]["citations_verified"] is False


@pytest.mark.asyncio
async def test_verification_pass_returns_answer():
    """is_faithful=True + citations_verified=True → the answer is returned."""
    state = _state(
        is_faithful=True,
        verification={"passed": True},
        confidence_score=8.0,
    )

    result = await format_final_answer(state)

    assert result["final_answer"] != FALLBACK_RESPONSE
    assert "Meditation is the practice" in result["final_answer"]
    assert result["_needs_retry"] is False


@pytest.mark.asyncio
async def test_verification_skipped_but_cited_returns_answer(monkeypatch):
    """is_faithful=None (verifier skipped) + citations_verified=True → the
    legitimate fast path is preserved: a substantive cited answer is accepted.
    This is the P1-AI-2 case that must NOT regress."""
    metric_mock = MagicMock()
    import app.metrics as metrics

    monkeypatch.setattr(metrics, "ANSWER_ACCEPTED_UNVERIFIED", metric_mock)
    # No inline markers → _verify_inline_citations is not invoked and
    # citations_verified stays True (the honest default for a cited answer).
    state = _state()

    result = await format_final_answer(state)

    assert result["final_answer"] != FALLBACK_RESPONSE
    assert "Meditation is the practice" in result["final_answer"]
    assert result["_needs_retry"] is False
    assert result["citations_verified"] is True
    metric_mock.inc.assert_called_once()


@pytest.mark.asyncio
async def test_verification_skipped_and_unverified_returns_fallback(monkeypatch):
    """is_faithful=None + citations_verified=False → FALLBACK_RESPONSE.
    This is the hole P1-AI-2 closes: a cited-but-unverified answer is no
    longer accepted."""
    monkeypatch.setattr(
        generation, "_verify_inline_citations",
        _unverified_citation_check(),
    )
    state = _state(answer=_LONG_ANSWER + " [[CITE:1]]")

    result = await format_final_answer(state)

    assert result["final_answer"] == FALLBACK_RESPONSE
    assert result["_needs_retry"] is False
    assert result["verification"]["citations_verified"] is False


@pytest.mark.asyncio
async def test_verification_fail_returns_fallback():
    """is_faithful=False → FALLBACK_RESPONSE (existing behavior preserved)."""
    state = _state(is_faithful=False, verification={"passed": False})

    result = await format_final_answer(state)

    assert result["final_answer"] == FALLBACK_RESPONSE
    assert result["is_faithful"] is False


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
