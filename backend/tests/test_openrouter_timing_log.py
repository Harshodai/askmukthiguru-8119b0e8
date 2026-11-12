"""Unit tests for OPENROUTER_CALL_TIMING usage.cost instrumentation (Task 2)."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from services.openrouter_service import OpenRouterService


@pytest.fixture(autouse=True)
def _allow_haiku_scorer(monkeypatch):
    # Hermetic: the policy allows this model only through the extra-allowed list, which a
    # developer's .env sets and a clean checkout does not.
    monkeypatch.setattr(settings, "openrouter_extra_allowed_models", "anthropic/claude-haiku-5.5")


@pytest.mark.asyncio
async def test_openrouter_call_timing_logs_cost(caplog):
    service = OpenRouterService()
    mock_response_data = {
        "id": "gen-123",
        "choices": [
            {
                "message": {"content": "Test response"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 5,
            "total_tokens": 20,
            "cost": 0.000123,
        },
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response_data
    mock_resp.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with (
        patch.object(service, "_get_http_client", return_value=mock_client),
        caplog.at_level(logging.INFO, logger="services.openrouter_service"),
    ):
        res = await service._call_api(
            messages=[{"role": "user", "content": "Hi"}],
            model="anthropic/claude-haiku-5.5",
            operation="verify",
        )

    assert res == "Test response"
    timing_logs = [r.message for r in caplog.records if "OPENROUTER_CALL_TIMING" in r.message]
    assert len(timing_logs) == 1
    log = timing_logs[0]
    assert "operation=verify" in log
    assert "cost=0.000123" in log


@pytest.mark.asyncio
async def test_openrouter_call_timing_logs_none_when_cost_omitted(caplog):
    service = OpenRouterService()
    mock_response_data = {
        "id": "gen-124",
        "choices": [
            {
                "message": {"content": "Test response"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 5,
            "total_tokens": 20,
        },
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response_data
    mock_resp.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with (
        patch.object(service, "_get_http_client", return_value=mock_client),
        caplog.at_level(logging.INFO, logger="services.openrouter_service"),
    ):
        res = await service._call_api(
            messages=[{"role": "user", "content": "Hi"}],
            model="anthropic/claude-haiku-5.5",
            operation="verify",
        )

    assert res == "Test response"
    timing_logs = [r.message for r in caplog.records if "OPENROUTER_CALL_TIMING" in r.message]
    assert len(timing_logs) == 1
    log = timing_logs[0]
    assert "cost=none" in log
