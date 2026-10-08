"""Unit tests for circuit breaker governance and crisis pass-through invariant."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.pipeline.stages.guardrail_stage import CircuitBreakerStage
from services.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitPolicy,
)


def test_circuit_policy_enum():
    """Verify CircuitPolicy definitions for governance."""
    assert CircuitPolicy.FAIL_CLOSED.value == "fail_closed"
    assert CircuitPolicy.FAIL_OPEN.value == "fail_open"

    cfg = CircuitBreakerConfig(provider="test_provider", policy=CircuitPolicy.FAIL_CLOSED)
    assert cfg.policy == CircuitPolicy.FAIL_CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_allows_crisis_through_when_circuit_open():
    """CRITICAL SAFETY INVARIANT: When LLM circuit breaker is OPEN, crisis queries

    must NOT receive generic connection errors; they must pass through to DistressStage
    so human helplines (Tele-MANAS, KIRAN) are emitted.
    """
    stage = CircuitBreakerStage()

    mock_coordinator = MagicMock()
    mock_coordinator._is_circuit_open.return_value = True

    # Crisis context
    ctx_crisis = SimpleNamespace(
        coordinator=mock_coordinator,
        user_msg="I feel completely hopeless and I want to end my life.",
        state={"user_msg_en": "I feel completely hopeless and I want to end my life."},
        last_stage_status=None,
    )

    result_crisis = await stage.run(ctx_crisis)
    # Must return None so pipeline continues to DistressStage!
    assert result_crisis is None
    assert ctx_crisis.last_stage_status is None


@pytest.mark.asyncio
async def test_circuit_breaker_short_circuits_benign_query_when_open():
    """Benign queries MUST be short-circuited with graceful connection error when circuit is open."""
    stage = CircuitBreakerStage()

    mock_coordinator = MagicMock()
    mock_coordinator._is_circuit_open.return_value = True
    from app.pipeline.pipeline_coordinator import PipelineCoordinator

    coord_helper = PipelineCoordinator.__new__(PipelineCoordinator)
    mock_circuit_result = coord_helper._circuit_open_result(False, 0.0)
    mock_coordinator._circuit_open_result.return_value = mock_circuit_result

    ctx_benign = SimpleNamespace(
        coordinator=mock_coordinator,
        user_msg="What is the nature of the mind?",
        state={"user_msg_en": "What is the nature of the mind?"},
        last_stage_status=None,
        is_benchmark=False,
        start_time=0.0,
        trace_id="test-trace",
        is_indic=False,
    )

    result_benign = await stage.run(ctx_benign)
    assert result_benign is not None
    assert ctx_benign.last_stage_status == "error"
