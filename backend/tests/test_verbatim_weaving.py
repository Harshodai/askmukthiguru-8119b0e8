"""Tests for LLM-powered verbatim smoothing, clip weaving, and latency bounding.

Validates:
1. verify_verbatim_spans preserves 100% verbatim quotes and rejects altered quotes.
2. _polish_and_weave_clips smoothly cleans trailing prepositions and weaved clips with hard timeout.
3. FirstPersonPipeline candidate bounding and concurrency invariants.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from rag.nodes.generation import (
    _clean_inline_citations,
    _polish_and_weave_clips,
    verify_verbatim_spans,
)
from services.first_person_pipeline import _HARNESS_JUDGE_CONCURRENCY, FirstPersonPipeline


def test_harness_judge_concurrency_is_four():
    """Concurrency is elevated to 4 to evaluate candidate contexts in a single parallel wave."""
    assert _HARNESS_JUDGE_CONCURRENCY == 4


def test_clean_inline_citations_removes_trailing_prepositions():
    """_clean_inline_citations cleanly strips dangling prepositions left by stripped URLs."""
    raw = (
        "You can find The Four Sacred Secrets by Sri Preethaji on Amazon at "
        "https://amzn.in/d/02dZXIDm."
    )
    cleaned = _clean_inline_citations(raw)
    assert "https://amzn.in" not in cleaned
    assert not cleaned.endswith(" at.")
    assert not cleaned.endswith(" at")
    assert "on Amazon" in cleaned


def test_verify_verbatim_spans_passes_for_exact_quote():
    """Quotes physically matching source docs pass verbatim verification."""
    source_docs = [
        {"text": "Sri Krishnaji teaches: When you are in the Beautiful State, life flows effortlessly."}
    ]
    original = "Life is peace. Sri Krishnaji says: > When you are in the Beautiful State, life flows effortlessly."
    polished = "Life is peace. Sri Krishnaji teaches: > When you are in the Beautiful State, life flows effortlessly."
    is_valid, text = verify_verbatim_spans(polished, source_docs, original)
    assert is_valid is True
    assert text == polished


def test_verify_verbatim_spans_fails_for_altered_quote():
    """Altered quotes fail verbatim verification and revert to the original text."""
    source_docs = [
        {"text": "Sri Krishnaji teaches: When you are in the Beautiful State, life flows effortlessly."}
    ]
    original = 'Sri Krishnaji says: "When you are in the Beautiful State, life flows effortlessly."'
    polished = 'Sri Krishnaji says: "When you are in the Beautiful State, life is totally easy and smooth."'
    is_valid, text = verify_verbatim_spans(polished, source_docs, original)
    assert is_valid is False
    assert text == original


@pytest.mark.asyncio
async def test_polish_and_weave_clips_preserves_quotes_and_cleans():
    """_polish_and_weave_clips weaves connective grammar while preserving verbatim quotes."""
    source_docs = [
        {"text": "Sri Preethaji explains: The mind in a state of suffering perceives separation."}
    ]
    original = (
        'Here is the wisdom: "The mind in a state of suffering perceives separation." '
        'You can read about it on Amazon.in at'
    )
    expected_polished = (
        'Here is the wisdom from the teachers:\n\n'
        '> "The mind in a state of suffering perceives separation."\n\n'
        'You can read more about this in the published teachings on Amazon.in.'
    )

    mock_llm = MagicMock()
    mock_llm.generate_fast = AsyncMock(return_value=expected_polished)

    result = await _polish_and_weave_clips(
        answer=original,
        source_docs=source_docs,
        question="What causes suffering?",
        provider=mock_llm,
        timeout_s=2.5,
    )
    assert "The mind in a state of suffering perceives separation." in result
    assert "Amazon.in" in result
    assert not result.endswith(" at")


@pytest.mark.asyncio
async def test_polish_and_weave_clips_timeout_falls_back():
    """_polish_and_weave_clips safely returns original draft if LLM call exceeds timeout."""
    source_docs = [{"text": "Meditation dissolves restless thoughts."}]
    original = "Sri Krishnaji teaches meditation dissolves restless thoughts."

    async def _slow_call(*args, **kwargs):
        await asyncio.sleep(0.5)
        return "Slow text"

    mock_llm = MagicMock()
    mock_llm.generate_fast = AsyncMock(side_effect=_slow_call)

    result = await _polish_and_weave_clips(
        answer=original,
        source_docs=source_docs,
        question="How to calm the mind?",
        provider=mock_llm,
        timeout_s=0.05,
    )
    assert result == original


def test_expand_context_candidates_is_bounded(monkeypatch):
    """_expand_context_candidates bounds total returned contexts to first_person_max_evaluated_contexts."""
    monkeypatch.setattr(settings, "first_person_memgraph_sizing_enabled", False)
    monkeypatch.setattr(settings, "first_person_enrichment_window_enabled", True)
    monkeypatch.setattr(settings, "first_person_graph_expansion_enabled", False)
    monkeypatch.setattr(settings, "first_person_okf_expansion_enabled", False)
    monkeypatch.setattr(settings, "first_person_teaching_unit_graph_enabled", False)

    mock_store = MagicMock()
    mock_store.enrich_to_parent_window.side_effect = lambda c: c

    pipeline = FirstPersonPipeline.__new__(FirstPersonPipeline)
    contexts = [MagicMock(parent=MagicMock(parent_unit_id=f"parent_{i}")) for i in range(10)]
    bounded = pipeline._expand_context_candidates(
        contexts,
        ctx_store=mock_store,
        query_dense_vector=[0.1] * 128,
        query_sparse_vector=None,
        retrieval_query="test",
        teacher_id="both",
        max_clips=10,
        max_spans=3,
    )
    max_eval = int(getattr(settings, "first_person_max_evaluated_contexts", 4) or 4)
    assert len(bounded) <= max_eval
