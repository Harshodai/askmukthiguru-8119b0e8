"""Unit tests for the off-topic handler (flag default OFF, mocks only, 0 LLM).

Covers: off-topic triggers, on-topic never triggers, flag-off byte-identical
legacy behavior (parity), flag-on short-circuit shape. Reuses conftest.py
fixtures (sys.path / env setup).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.off_topic_stage import (
    OffTopicStage,
    build_off_topic_response,
    is_off_topic,
    off_topic_handler_enabled,
)
from app.pipeline.stages.pipeline_builder import build_default_pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_ctx(question: str) -> PipelineContext:
    return PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg=question,
        preferred_lang="en",
        session_id="sess-off-topic",
        trace_id="trace-off-topic",
        start_time=time.time(),
        state={"user_msg_en": question},
    )


# ---------------------------------------------------------------------------
# 1. Off-topic queries trigger
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "What is the capital of France?",
        "what is the CAPITAL of france",
        "Give me stock tips for next week",
        "Which stocks should I invest in?",
        "Can you diagnose my chest pain?",
        "What disease do I have based on these symptoms?",
        "Should I buy bitcoin or mutual funds?",
        "Who will win the election?",
        "What is the cricket score?",
        "Write me Python code to debug my API error",
        "Give me legal advice for my property dispute",
        "Share a chicken biryani recipe",
    ],
)
def test_off_topic_triggers(question: str) -> None:
    assert is_off_topic(question) is True


# ---------------------------------------------------------------------------
# 2. On-topic queries never trigger
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "What is meditation?",
        "What is the Beautiful State?",
        "What is deeksha?",
        "What is the relationship between suffering and consciousness?",
        "How does Soul Sync breath bring calm?",
        "Tell me about Ekam and oneness",
        "How do I deal with anxiety and stress?",
        "What do the teachings say about forgiveness?",
        "hello",  # unrecognized -> fail-open, legacy path owns it
        "",  # empty -> fail-open
    ],
)
def test_on_topic_never_triggers(question: str) -> None:
    assert is_off_topic(question) is False


def test_on_topic_anchor_wins_over_off_topic_keyword() -> None:
    # Crisis/doctrine query that merely mentions a worldly word stays on-topic.
    assert is_off_topic("How does meditation help when I stress about the stock market?") is False
    assert is_off_topic("What is the difference between meditation and contemplation?") is False


# ---------------------------------------------------------------------------
# 3. Refusal copy: honest, brief, on-brand, no fabricated teachings
# ---------------------------------------------------------------------------


def test_refusal_copy_honest_and_redirects() -> None:
    copy = build_off_topic_response()
    assert "have not spoken about this" in copy
    assert "will not guess" in copy
    assert "Beautiful State" in copy and "deeksha" in copy
    assert len(copy) <= 800
    # No fabricated teachings: never quotes the teachers or states doctrine.
    for forbidden in ("Krishnaji says", "Preethaji says", "\u201c", "\u201d", '"'):
        assert forbidden not in copy


# ---------------------------------------------------------------------------
# 4. Flag-off parity: byte-identical legacy behavior
# ---------------------------------------------------------------------------


def test_flag_defaults_off_without_settings_field() -> None:
    from app.config import settings

    assert not hasattr(settings, "off_topic_handler_enabled")
    assert off_topic_handler_enabled() is False


def test_live_pipeline_contains_no_off_topic_stage() -> None:
    names = [stage.name for stage in build_default_pipeline()]
    assert "off_topic_short_circuit" not in names


@pytest.mark.asyncio
async def test_stage_passes_through_everything_when_flag_off() -> None:
    stage = OffTopicStage()
    for question in (
        "What is the capital of France?",
        "Give me stock tips",
        "What is meditation?",
    ):
        assert await stage.run(_build_ctx(question)) is None


# ---------------------------------------------------------------------------
# 5. Flag-on: short-circuit shape (monkeypatched flag, still no LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage_short_circuits_off_topic_when_flag_on(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    result = await OffTopicStage().run(_build_ctx("What is the capital of France?"))
    assert result is not None
    assert "have not spoken about this" in result.final_answer
    assert result.citations == []
    assert result.verification is not None and result.verification["passed"] is False
    assert result.verification["method"] == "off_topic_short_circuit"
    assert result.citations_verified is False
    assert result.route_decision == "off_topic_short_circuit"
    assert result.model_used is None


@pytest.mark.asyncio
async def test_stage_passes_on_topic_through_when_flag_on(monkeypatch) -> None:
    import app.pipeline.stages.off_topic_stage as mod

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    for question in (
        "What is meditation?",
        "What is the Beautiful State?",
        "What is deeksha?",
    ):
        assert await OffTopicStage().run(_build_ctx(question)) is None
