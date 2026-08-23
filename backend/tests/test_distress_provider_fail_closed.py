import asyncio

from unittest.mock import AsyncMock


def test_openrouter_distress_provider_failure_is_not_intent_fallback():
    from services.openrouter_service import OpenRouterService

    service = OpenRouterService.__new__(OpenRouterService)
    service._generate_fast = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    service.classify_intent = AsyncMock(side_effect=AssertionError("intent fallback must not run"))

    result = asyncio.run(service.classify_distress_structured("What is the beautiful state?"))

    assert result["is_distress"] is False
    assert result["confidence"] == 0.0
    assert "deterministic safety checks" in result["reason"]
    service.classify_intent.assert_not_awaited()


def test_circuit_open_provider_failure_is_not_a_safety_block():
    from app.pipeline.pipeline_coordinator import PipelineCoordinator

    coordinator = PipelineCoordinator.__new__(PipelineCoordinator)
    result = coordinator._circuit_open_result(False, 0.0)

    assert result.intent == "ERROR"
    assert result.route_decision == "error"
    assert result.blocked is False
    assert result.block_reason is None
