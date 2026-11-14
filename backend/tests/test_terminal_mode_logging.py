"""Tests for terminal-mode logging in FirstPersonPipeline.

Validates that when the context harness is active:
1. Context store retrieval failures log terminal abstention vs legacy fall-through.
2. Context evaluations yielding no direct answer log terminal abstention vs legacy fall-through.
3. Return values match the terminal mode contract (abstained result vs None for fall-through).
"""

from __future__ import annotations

import logging
import time
from unittest.mock import MagicMock

import pytest

from app.config import settings
from services.first_person_pipeline import FirstPersonPipeline


@pytest.fixture
def mock_pipeline():
    store = MagicMock()
    store.collection = "first_person_v10"
    ctx_store = MagicMock()
    pipeline = FirstPersonPipeline(
        store=store,
        redis_client=MagicMock(),
        serene_mind_engine=MagicMock(),
        context_store=ctx_store,
    )
    return pipeline, ctx_store


@pytest.mark.asyncio
async def test_context_retrieval_failure_logging_terminal_mode(mock_pipeline, monkeypatch, caplog):
    pipeline, ctx_store = mock_pipeline
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", True)
    ctx_store.retrieve.side_effect = RuntimeError("Qdrant connection dropped")

    with caplog.at_level(logging.INFO):
        res = await pipeline._serve_from_context_harness(
            query="what is suffering",
            query_dense_vector=[0.1] * 128,
            query_sparse_vector=None,
            teacher_id=None,
            max_clips=3,
            retrieval_query="what is suffering",
            language="en",
            cache_bypass=True,
            request_allow_state="",
            request_block_state="",
            fp_llm_tokens=[],
            _ans_box={},
            start_time=time.monotonic(),
        )

    assert (
        "Context store retrieval FAILED (RuntimeError: Qdrant connection dropped); "
        "terminal mode: abstaining, no legacy fall-through"
    ) in caplog.text
    assert res is not None
    assert res.status == "abstained"
    assert res.abstain_reason == "no_verified_clips"
    assert res.error == "context_retrieval_error:RuntimeError"


@pytest.mark.asyncio
async def test_context_retrieval_failure_logging_non_terminal_mode(mock_pipeline, monkeypatch, caplog):
    pipeline, ctx_store = mock_pipeline
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", False)
    ctx_store.retrieve.side_effect = RuntimeError("Qdrant connection dropped")

    with caplog.at_level(logging.INFO):
        res = await pipeline._serve_from_context_harness(
            query="what is suffering",
            query_dense_vector=[0.1] * 128,
            query_sparse_vector=None,
            teacher_id=None,
            max_clips=3,
            retrieval_query="what is suffering",
            language="en",
            cache_bypass=True,
            request_allow_state="",
            request_block_state="",
            fp_llm_tokens=[],
            _ans_box={},
            start_time=time.monotonic(),
        )

    assert (
        "Context store retrieval FAILED (RuntimeError: Qdrant connection dropped); "
        "falling back to legacy"
    ) in caplog.text
    assert res is None


@pytest.mark.asyncio
async def test_context_evaluation_no_direct_answer_terminal_mode(mock_pipeline, monkeypatch, caplog):
    pipeline, ctx_store = mock_pipeline
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", True)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    monkeypatch.setattr(pipeline, "_expand_context_candidates", lambda contexts, **kwargs: contexts)
    monkeypatch.setattr(pipeline, "_diversify_candidate_pool", lambda contexts: contexts)

    mock_ctx = MagicMock()
    mock_ctx.spans = []
    mock_ctx.hit_span_ids = ()
    mock_ctx.parent.ordered_source_span_ids = ()
    ctx_store.retrieve.return_value = [mock_ctx]

    mock_harness = MagicMock()
    mock_harness._policy.max_context_spans = 3
    mock_harness.decide.return_value = MagicMock(decision="DECLINE")
    pipeline._context_harness = mock_harness

    with caplog.at_level(logging.INFO):
        res = await pipeline._serve_from_context_harness(
            query="what is suffering",
            query_dense_vector=[0.1] * 128,
            query_sparse_vector=None,
            teacher_id=None,
            max_clips=3,
            retrieval_query="what is suffering",
            language="en",
            cache_bypass=True,
            request_allow_state="",
            request_block_state="",
            fp_llm_tokens=[],
            _ans_box={},
            start_time=time.monotonic(),
        )

    assert (
        "Context harness evaluated 1 contexts with no direct answer; "
        "terminal mode: abstaining, no legacy fall-through"
    ) in caplog.text
    assert res is not None
    assert res.status == "abstained"
    assert res.abstain_reason == "no_verified_clips"


@pytest.mark.asyncio
async def test_context_evaluation_no_direct_answer_non_terminal_mode(mock_pipeline, monkeypatch, caplog):
    pipeline, ctx_store = mock_pipeline
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", False)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    monkeypatch.setattr(pipeline, "_expand_context_candidates", lambda contexts, **kwargs: contexts)
    monkeypatch.setattr(pipeline, "_diversify_candidate_pool", lambda contexts: contexts)

    mock_ctx = MagicMock()
    mock_ctx.spans = []
    mock_ctx.hit_span_ids = ()
    mock_ctx.parent.ordered_source_span_ids = ()
    ctx_store.retrieve.return_value = [mock_ctx]

    mock_harness = MagicMock()
    mock_harness._policy.max_context_spans = 3
    mock_harness.decide.return_value = MagicMock(decision="DECLINE")
    pipeline._context_harness = mock_harness

    with caplog.at_level(logging.INFO):
        res = await pipeline._serve_from_context_harness(
            query="what is suffering",
            query_dense_vector=[0.1] * 128,
            query_sparse_vector=None,
            teacher_id=None,
            max_clips=3,
            retrieval_query="what is suffering",
            language="en",
            cache_bypass=True,
            request_allow_state="",
            request_block_state="",
            fp_llm_tokens=[],
            _ans_box={},
            start_time=time.monotonic(),
        )

    assert (
        "Context harness evaluated 1 contexts with no direct answer; "
        "falling back to legacy"
    ) in caplog.text
    assert res is None
