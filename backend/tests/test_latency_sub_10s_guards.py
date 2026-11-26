"""Regression tests for sub-10s latency SLA, fast HyDE, and retry time bounding."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.services.llm_queue import LLMPriority, QueuedLLMProvider
from rag.graph_strategies import route_after_formatting
from services.openrouter_service import OpenRouterService


def test_first_person_hyde_timeout_bounded():
    """Verify first_person_hyde_timeout_s is strictly capped at 2.5s for sub-10s SLA."""
    assert settings.first_person_hyde_timeout_s <= 2.5


def test_openrouter_generation_model_defaults_to_fast_70b():
    """Verify default generation model is high-throughput llama-3.3-70b-instruct."""
    from app.config import Settings
    assert Settings.model_fields["openrouter_generation_model"].default == "meta-llama/llama-3.3-70b-instruct"


@pytest.mark.asyncio
async def test_openrouter_generate_hyde_uses_fast_model_when_flag_enabled(monkeypatch):
    """HyDE must route to _generate_fast when rag_rewrite_query_fast_model is True."""
    monkeypatch.setattr(settings, "rag_rewrite_query_fast_model", True)
    service = OpenRouterService()
    mock_fast = AsyncMock(return_value="hypothetical wisdom passage")
    monkeypatch.setattr(service, "_generate_fast", mock_fast)

    res = await service.generate_hypothetical_answer("What is suffering?")
    assert res == "hypothetical wisdom passage"
    assert mock_fast.called
    assert mock_fast.call_args[1].get("operation") == "generate_hyde"


@pytest.mark.asyncio
async def test_llm_queue_routes_hyde_to_classify_priority():
    """QueuedLLMProvider.generate_hyde must use LLMPriority.CLASSIFY for minimal queue latency."""
    queue = MagicMock()
    queue.execute = AsyncMock(return_value="hyde text")
    provider = MagicMock()
    queued_provider = QueuedLLMProvider(provider, queue)

    await queued_provider.generate_hyde("What is inner state?")
    assert queue.execute.called
    priority = queue.execute.call_args[0][0]
    assert priority == LLMPriority.CLASSIFY


def test_route_after_formatting_skips_retry_when_elapsed_epoch_exceeds_budget():
    """When turn_start is epoch timestamp (time.time()) and >= 6.0s elapsed, retry must be skipped."""
    # Simulate start_time 7 seconds ago
    start_time = time.time() - 7.0
    state = {
        "_needs_retry": True,
        "retry_count": 0,
        "start_time": start_time,
    }
    decision = route_after_formatting(state)
    assert decision == "end"


def test_route_after_formatting_allows_retry_when_elapsed_within_budget():
    """When turn_start is epoch timestamp and within budget (< 6.0s), retry is permitted."""
    start_time = time.time() - 2.0
    state = {
        "_needs_retry": True,
        "retry_count": 0,
        "start_time": start_time,
    }
    decision = route_after_formatting(state)
    assert decision == "retry_generate"
